"""Tool schema + dispatcher: the bridge between the LLM and FortyGuard.

Each tool the agent can call maps 1:1 to a FortyGuard capability or a local
analysis helper. Every FortyGuard result is logged to an audit trail so the
final answer can cite activity_ids.
"""

from __future__ import annotations

import json
import statistics
from typing import Any

from .fg_client import FortyGuardClient, FortyGuardError

TOOLS = [
    {
        "name": "create_heatmap",
        "description": (
            "Generate a hyperlocal air-temperature heatmap over a polygon AOI "
            "inside the United States. Coordinates are [longitude, latitude]. "
            "Dates 2021-01-01 to now (+12h forecast). filter_type: 1=single hour, "
            "3=entire day, 5=single month. Polygon must be under ~130 km². "
            "Returns tile-level temperature stats and an activity_id."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "coords": {
                    "type": "array",
                    "items": {"type": "array", "items": {"type": "number"}},
                    "description": "Polygon ring as [[lon,lat],...]; will be auto-closed.",
                },
                "start_date": {"type": "string", "description": "YYYY-MM-DD"},
                "start_time": {"type": "string", "description": "HH:MM, e.g. 14:00 peak heat"},
                "filter_type": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
                "granularity": {"type": "integer", "enum": [60, 80, 100]},
            },
            "required": ["coords", "start_date"],
        },
    },
    {
        "name": "get_env_params",
        "description": (
            "Fetch heat index, AQI, solar irradiance and related environmental "
            "parameters at a single U.S. point for a given date/time."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "lat": {"type": "number"},
                "lon": {"type": "number"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "time": {"type": "string", "description": "HH:MM"},
            },
            "required": ["lat", "lon", "date"],
        },
    },
    {
        "name": "rank_sites",
        "description": (
            "Local analysis (no credits). Given a list of sites, each with a name "
            "and one or more temperature readings, rank them hottest-first and "
            "compute mean/max per site. Use after collecting readings."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "sites": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "readings": {"type": "array", "items": {"type": "number"}},
                            "meta": {"type": "object"},
                        },
                        "required": ["name", "readings"],
                    },
                }
            },
            "required": ["sites"],
        },
    },
    {
        "name": "check_credits",
        "description": "Check remaining FortyGuard API credit balance before expensive batches.",
        "input_schema": {"type": "object", "properties": {}},
    },
]


def _summarize_heatmap(res: dict) -> dict:
    """Compress a raw heatmap result (thousands of tile polygons, ~1.4 MB)
    into stats the model can actually reason over."""
    result = res.get("result") or {}
    stats = (result.get("stats_data") or {}).get("temperature_stats")
    feats = (result.get("map_data") or {}).get("features") or []

    tiles = []
    for f in feats:
        props = f.get("properties") or {}
        try:
            ring = f["geometry"]["coordinates"][0]
            lat = round(sum(p[1] for p in ring) / len(ring), 5)
            lon = round(sum(p[0] for p in ring) / len(ring), 5)
        except (KeyError, IndexError, TypeError, ZeroDivisionError):
            lat = lon = None
        avg = props.get("average_temperature")
        if avg is None:
            continue
        tiles.append({
            "tile_id": props.get("tile_id"),
            "avg_temp": avg,
            "max_temp": props.get("max_temperature"),
            "centroid_lat_lon": [lat, lon],
        })

    tiles.sort(key=lambda t: t["avg_temp"], reverse=True)
    return {
        "activity_id": res.get("activity_id"),
        "from_cache": res.get("from_cache", False),
        "tile_count": len(tiles),
        "temperature_stats_celsius": stats,
        "hottest_tiles": tiles[:5],
        "coolest_tiles": tiles[-3:][::-1] if tiles else [],
        "note": "Tile-level GeoJSON omitted for brevity; stats cover all tiles.",
    }


class ToolRunner:
    def __init__(self, client: FortyGuardClient):
        self.client = client
        self.audit_trail: list[dict[str, Any]] = []

    def _log(self, tool: str, args: dict, result: dict) -> None:
        self.audit_trail.append({
            "tool": tool,
            "args": args,
            "activity_id": result.get("activity_id"),
            "from_cache": result.get("from_cache", False),
        })

    def run(self, name: str, args: dict) -> str:
        try:
            if name == "create_heatmap":
                res = self.client.create_heatmap(**args)
                self._log(name, args, res)
                return json.dumps(_summarize_heatmap(res))
            if name == "get_env_params":
                lat = args.get("lat", args.get("latitude"))
                lon = args.get("lon", args.get("longitude"))
                res = self.client.env_params(
                    lat, lon, args["date"], args.get("time", "14:00")
                )
                self._log(name, args, res)
                return json.dumps(res)
            if name == "rank_sites":
                ranked = sorted(
                    (
                        {
                            "name": s["name"],
                            "mean": round(statistics.fmean(s["readings"]), 2),
                            "max": max(s["readings"]),
                            "meta": s.get("meta", {}),
                        }
                        for s in args["sites"]
                    ),
                    key=lambda x: x["mean"],
                    reverse=True,
                )
                return json.dumps({"ranked": ranked})
            if name == "check_credits":
                res = self.client.credit_usage()
                self._log(name, {}, res)
                return json.dumps(res)
            return json.dumps({"error": f"unknown tool {name}"})
        except FortyGuardError as e:
            return json.dumps({"error": str(e), "activity_id": e.activity_id})
        except Exception as e:  # surface everything to the model, never crash the loop
            return json.dumps({"error": f"{type(e).__name__}: {e}"})
