"""FortyGuard Temperature API client.

Implements the submit-then-poll async pattern (§7.4 of the handbook) with:
- polite exponential backoff polling (3s -> 6s -> 12s, capped)
- aggressive disk caching keyed by (endpoint, payload) so credits are
  never spent twice on the same query (§7.7 best practices)
- clean error surfaces: every result carries its activity_id for audit
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any

import httpx

from . import config

BASE_URL = "https://api.fortyguard.com"
CACHE_DIR = Path(config.get("HEATOPS_CACHE_DIR", ".fg_cache"))
# Bounded polling with backoff: 3s -> 6s -> 12s, then steady 12s.
# Docs' own example allows ~10 minutes total; we cap around 8 minutes.
POLL_SCHEDULE = [3, 6] + [12] * 38  # ~7.7 min total
TERMINAL_OK = {"succeeded", "completed"}
TERMINAL_BAD = {"failed", "error"}


class FortyGuardError(RuntimeError):
    def __init__(self, message: str, activity_id: str | None = None):
        super().__init__(message)
        self.activity_id = activity_id


class FortyGuardClient:
    def __init__(self, api_key: str | None = None, cache: bool = True):
        self.api_key = api_key or config.get("FORTYGUARD_API_KEY")
        if not self.api_key:
            raise FortyGuardError(
                "No API key. Set FORTYGUARD_API_KEY in your .env file."
            )
        self.cache = cache
        CACHE_DIR.mkdir(exist_ok=True)
        self._http = httpx.Client(
            base_url=BASE_URL,
            headers={"api-key": self.api_key, "Content-Type": "application/json"},
            timeout=60,
        )

    # ---------- low-level ----------

    def _cache_key(self, endpoint: str, payload: dict) -> Path:
        digest = hashlib.sha256(
            json.dumps({"e": endpoint, "p": payload}, sort_keys=True).encode()
        ).hexdigest()[:24]
        return CACHE_DIR / f"{digest}.json"

    # Error meanings per official docs (docs-api.fortyguard.com/docs/quickstart)
    _HTTP_ERRORS = {
        400: "Invalid request or validation error",
        422: "Invalid request or validation error",
        401: "Missing or invalid API key",
        403: "Insufficient plan access or authorization",
        429: "Rate limit exceeded — back off and retry later",
        500: "Server-side processing error",
    }

    def _submit(self, endpoint: str, payload: dict) -> str:
        r = self._http.post(endpoint, json=payload)
        if r.status_code in self._HTTP_ERRORS:
            raise FortyGuardError(
                f"POST {endpoint} -> {r.status_code}: "
                f"{self._HTTP_ERRORS[r.status_code]}. Body: {r.text[:300]}"
            )
        r.raise_for_status()
        body = r.json()
        # Official shape: {"data": {"activity_id": ...}}
        activity_id = body.get("data", {}).get("activity_id") or body.get("activity_id")
        if not activity_id:
            raise FortyGuardError(f"No activity_id in response: {json.dumps(body)[:300]}")
        return activity_id

    def _poll(self, activity_id: str) -> dict:
        for delay in POLL_SCHEDULE:
            r = self._http.get(f"/v1/status/{activity_id}")
            # Per docs: 404 can occur temporarily right after submission — keep polling.
            if r.status_code == 404:
                time.sleep(delay)
                continue
            if r.status_code == 429:
                time.sleep(max(delay, 15))
                continue
            r.raise_for_status()
            body = r.json()
            data = body.get("data", body)
            status = str(data.get("status", "")).lower()
            if status in TERMINAL_OK:
                return body
            if status in TERMINAL_BAD:
                raise FortyGuardError(
                    f"Task {activity_id} ended with status={status} "
                    f"(no credits consumed on failure).",
                    activity_id,
                )
            # "Processing" (or anything non-terminal) -> bounded polling
            time.sleep(delay)
        raise FortyGuardError(f"Task {activity_id} timed out while polling.", activity_id)

    def call(self, endpoint: str, payload: dict) -> dict:
        """Submit -> poll -> return {'activity_id', 'result'}; cached on disk."""
        key = self._cache_key(endpoint, payload)
        if self.cache and key.exists():
            cached = json.loads(key.read_text())
            cached["from_cache"] = True
            return cached

        activity_id = self._submit(endpoint, payload)
        body = self._poll(activity_id)
        # Per docs, the status endpoint includes the result payload on completion,
        # inside the "data" envelope. Keep whichever of data.result / data exists.
        data = body.get("data", body)
        result = {
            "activity_id": activity_id,
            "endpoint": endpoint,
            "result": data.get("result", data),
            "from_cache": False,
        }
        key.write_text(json.dumps(result))
        return result

    # ---------- high-level endpoints ----------

    @staticmethod
    def polygon(coords: list[list[float]]) -> dict:
        """coords: [[lon, lat], ...] — first and last pair must match."""
        if coords[0] != coords[-1]:
            coords = coords + [coords[0]]
        return {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {},
                "geometry": {"type": "Polygon", "coordinates": [coords]},
            }],
        }

    def create_heatmap(
        self,
        coords: list[list[float]],
        start_date: str,
        start_time: str = "14:00",
        filter_type: int = 1,
        granularity: int = 100,
        **extra: Any,
    ) -> dict:
        payload = {
            "polygon_aoi": self.polygon(coords),
            "date_time": {
                "start_date": start_date,
                "start_time": start_time,
                "filter_type": filter_type,
                **extra.pop("date_time_extra", {}),
            },
            "granularity": granularity,
            **extra,
        }
        return self.call("/v1/heatmap", payload)

    def env_params(self, lat: float, lon: float, date: str, time_: str = "14:00") -> dict:
        payload = {
            "latitude": lat,
            "longitude": lon,
            "temperature": True,
            "date_time": {"start_date": date, "start_time": time_, "filter_type": 1},
        }
        return self.call("/v1/env_params", payload)

    def credit_usage(self) -> dict:
        return self.call("/v1/system/fetch-api-key-usage", {})
