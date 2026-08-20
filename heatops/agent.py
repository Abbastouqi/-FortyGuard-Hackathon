"""HeatOps Agent — plan, call, decide.

A tool-use loop: the LLM receives a plain-language brief, plans which
FortyGuard endpoints to call, executes them via ToolRunner, and produces a
ranked, source-cited action plan. Every claim in the final answer must cite
the activity_id of the API call that produced it — that's what makes the
output auditable.

Two LLM backends:
- If HEATOPS_LLM_BASE_URL is set, an OpenAI-compatible endpoint is used
  (e.g. a self-hosted vLLM/LiteLLM gateway). Native tool calling is not
  assumed: tools are described in the system prompt and the model emits a
  JSON tool request in text, which the loop parses and executes.
- Otherwise, the Anthropic API with native tool use (ANTHROPIC_API_KEY).
"""

from __future__ import annotations

import json
import re
from datetime import date

import httpx

from . import config
from .fg_client import FortyGuardClient
from .tools import TOOLS, ToolRunner

LLM_BASE_URL = config.get("HEATOPS_LLM_BASE_URL").rstrip("/")
LLM_API_KEY = config.get("HEATOPS_LLM_API_KEY")
LLM_VERIFY_TLS = config.get("HEATOPS_LLM_VERIFY_TLS", "true").lower() != "false"
MODEL = config.get(
    "HEATOPS_MODEL", "qwen3.6-35b-a3b" if LLM_BASE_URL else "claude-sonnet-4-6"
)
MAX_STEPS = 12

SYSTEM = f"""You are HeatOps, an urban-heat analysis agent for city planners,
logistics managers, and facility operators. Today is {date.today().isoformat()}.

You have tools backed by FortyGuard's Temperature API (hyperlocal ~2 m
resolution air temperature over the United States, 2021-01-01 to now +12h).

Method:
1. Restate the user's goal and write a short numbered plan BEFORE calling tools.
2. Prefer few, well-chosen calls: validate on one location/timestamp first,
   then batch. Heatmap polygons must stay under ~130 km². U.S. locations only.
3. Use rank_sites for local math instead of estimating in your head.
4. Finish with an ACTION PLAN: a ranked list of concrete recommendations.
   Cite the activity_id of the API call behind every quantitative claim,
   like: "Stop 14 averaged 41.3°C at 14:00 [act: abc123]".
5. If the brief is outside coverage (non-U.S., pre-2021, >12h future),
   say so and propose the closest valid analysis instead of guessing.
Be concise. Never fabricate temperatures — every number must come from a tool.
"""

# ---------------------------------------------------------------------------
# Prompt-based tool protocol for OpenAI-compatible backends without native
# tool calling. The model asks for ONE tool per turn via a fenced JSON block.
# ---------------------------------------------------------------------------

_TOOL_PROTOCOL = """
## Tools

You cannot call tools natively. To use a tool, end your message with EXACTLY
one fenced JSON block in this format (and nothing after it):

```json
{"tool": "<tool_name>", "input": {<arguments matching the tool's schema>}}
```

One tool call per message. The next user message will contain the tool's
result as JSON. When you have everything you need, write your final answer
WITHOUT any such JSON block.

Available tools:

"""


def _tools_prompt() -> str:
    lines = [_TOOL_PROTOCOL]
    for t in TOOLS:
        lines.append(f"### {t['name']}")
        lines.append(t["description"])
        lines.append("Input schema: " + json.dumps(t["input_schema"]))
        lines.append("")
    return "\n".join(lines)


_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_TOOL_CALL_RES = [
    re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL),
    re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL),
]


def _parse_tool_call(text: str) -> tuple[str, dict] | None:
    """Find a {"tool": ..., "input": ...} request in the model's text."""
    for pattern in _TOOL_CALL_RES:
        for match in pattern.finditer(text):
            try:
                obj = json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and "tool" in obj:
                return str(obj["tool"]), dict(obj.get("input") or {})
    return None


def _strip_tool_blocks(text: str) -> str:
    for pattern in _TOOL_CALL_RES:
        text = pattern.sub("", text)
    return text.strip()


class HeatOpsAgent:
    def __init__(self, fg_client: FortyGuardClient | None = None):
        self.runner = ToolRunner(fg_client or FortyGuardClient())
        if LLM_BASE_URL:
            self.llm = None
            self.http = httpx.Client(
                base_url=LLM_BASE_URL,
                headers={"Authorization": f"Bearer {LLM_API_KEY}"},
                verify=LLM_VERIFY_TLS,
                timeout=300,
            )
        else:
            import anthropic

            self.llm = anthropic.Anthropic(
                api_key=config.get("ANTHROPIC_API_KEY") or None
            )
            self.http = None

    def run(self, brief: str, on_event=print, on_token=None) -> str:
        if LLM_BASE_URL:
            return self._run_openai_compat(brief, on_event, on_token)
        return self._run_anthropic(brief, on_event)

    # -- OpenAI-compatible backend (prompt-based tool calling) --------------

    @staticmethod
    def _visible(raw: str) -> str:
        """Strip completed and unterminated <think> blocks."""
        text = _THINK_RE.sub("", raw)
        if "<think>" in text:
            text = text.split("<think>")[0]
        return text.strip()

    def _chat(self, messages: list[dict], on_token=None) -> tuple[str, str]:
        """Stream a completion (keeps slow gateways from idling out the
        connection); returns (visible_text, finish_reason)."""
        raw, finish = "", "stop"
        with self.http.stream(
            "POST",
            "/chat/completions",
            json={
                "model": MODEL,
                "messages": messages,
                "max_tokens": 12000,
                "stream": True,
            },
        ) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choice = (chunk.get("choices") or [{}])[0]
                raw += choice.get("delta", {}).get("content") or ""
                finish = choice.get("finish_reason") or finish
                if on_token:
                    visible = self._visible(raw)
                    if visible:
                        on_token(visible)
        return self._visible(raw), finish

    def _run_openai_compat(self, brief: str, on_event=print, on_token=None) -> str:
        messages = [
            {"role": "system", "content": SYSTEM + _tools_prompt()},
            {"role": "user", "content": brief},
        ]
        for step in range(MAX_STEPS):
            content, finish = self._chat(messages, on_token)
            messages.append({"role": "assistant", "content": content})

            call = _parse_tool_call(content)
            prose = _strip_tool_blocks(content)
            if prose:
                on_event(f"[agent] {prose}")

            if call is None:
                if finish == "length":  # cut off mid-generation — nudge on
                    on_event("[agent] (reply was cut off — continuing)")
                    messages.append({
                        "role": "user",
                        "content": (
                            "Your reply was cut off. Continue concisely: emit "
                            "the JSON tool block if you need data, otherwise "
                            "give your final answer now."
                        ),
                    })
                    continue
                return prose or content  # final answer

            name, args = call
            on_event(f"[tool ] {name}({str(args)[:120]}...)")
            output = self.runner.run(name, args)
            messages.append({
                "role": "user",
                "content": f"Tool result for {name}:\n{output[:50_000]}",
            })

        return "Stopped: exceeded max agent steps. Partial audit trail available."

    # -- Anthropic backend (native tool use) ---------------------------------

    def _run_anthropic(self, brief: str, on_event=print) -> str:
        messages = [{"role": "user", "content": brief}]
        for step in range(MAX_STEPS):
            resp = self.llm.messages.create(
                model=MODEL,
                max_tokens=4000,
                system=SYSTEM,
                tools=TOOLS,
                messages=messages,
            )
            messages.append({"role": "assistant", "content": resp.content})

            tool_uses = [b for b in resp.content if b.type == "tool_use"]
            for block in resp.content:
                if block.type == "text" and block.text.strip():
                    on_event(f"[agent] {block.text.strip()}")

            if not tool_uses:  # final answer
                return "\n".join(
                    b.text for b in resp.content if b.type == "text"
                )

            results = []
            for tu in tool_uses:
                on_event(f"[tool ] {tu.name}({str(tu.input)[:120]}...)")
                output = self.runner.run(tu.name, dict(tu.input))
                results.append({
                    "type": "tool_result",
                    "tool_use_id": tu.id,
                    "content": output[:50_000],
                })
            messages.append({"role": "user", "content": results})

        return "Stopped: exceeded max agent steps. Partial audit trail available."

    @property
    def audit_trail(self):
        return self.runner.audit_trail
