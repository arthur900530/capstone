from __future__ import annotations

import json
import os
from typing import Any

from openai import AsyncOpenAI

from config import SKILL_SELECTION_MODEL, TEST_CASE_DEFAULT_MAX_LATENCY_MS, TEST_CASE_MIN_LATENCY_MS

_GENERATOR_PROMPT = (
    "You generate high-quality edge-case tests for an AI employee.\n"
    "Return strict JSON only: an array of objects with keys:\n"
    "title (string), prompt (string), success_criteria (string),\n"
    "hard_failure_signals (array of strings), max_latency_ms (optional integer, minimum 120000).\n"
    "Focus on difficult, realistic corner cases: ambiguity, conflicting requirements,\n"
    "adversarial asks, missing data, off-domain asks, and boundary-of-capability situations.\n"
    "Do not wrap output in markdown."
)


def _resolve_openai_model(model: str) -> str:
    raw = (model or "").strip()
    if not raw:
        return "gpt-4o-mini"
    while "/" in raw:
        provider, _, bare = raw.partition("/")
        if provider.lower() != "openai":
            return "gpt-4o-mini"
        raw = bare
    return raw or "gpt-4o-mini"


def _normalize_case(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    title = str(raw.get("title") or "").strip()
    prompt = str(raw.get("prompt") or "").strip()
    success_criteria = str(raw.get("success_criteria") or "").strip()
    if not title or not prompt or not success_criteria:
        return None

    hard_failure_signals = raw.get("hard_failure_signals")
    if not isinstance(hard_failure_signals, list):
        hard_failure_signals = []
    hard_failure_signals = [str(item).strip() for item in hard_failure_signals if str(item).strip()]

    max_latency_ms = raw.get("max_latency_ms")
    if not isinstance(max_latency_ms, int) or max_latency_ms <= 0:
        max_latency_ms = TEST_CASE_DEFAULT_MAX_LATENCY_MS
    # H-B fix: LLMs tend to hallucinate very short latency caps (e.g. 5000ms).
    # Enforce a hard floor so no test can timeout before the agent even starts.
    max_latency_ms = max(max_latency_ms, TEST_CASE_MIN_LATENCY_MS)

    return {
        "title": title,
        "prompt": prompt,
        "success_criteria": success_criteria,
        "hard_failure_signals": hard_failure_signals,
        "max_latency_ms": max_latency_ms,
    }


async def generate_test_cases(
    *,
    employee_description: str,
    employee_task: str,
    skills: list[dict[str, str]],
    plugins: list[dict[str, str]],
    count: int = 5,
) -> tuple[list[dict[str, Any]], str]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    client = AsyncOpenAI(api_key=api_key, timeout=45.0)
    target_model = _resolve_openai_model(SKILL_SELECTION_MODEL)
    payload = {
        "count": max(1, min(int(count), 20)),
        "employee": {
            "description": employee_description or "",
            "task": employee_task or "",
        },
        "skills": skills,
        "plugins": plugins,
    }

    resp = await client.chat.completions.create(
        model=target_model,
        messages=[
            {"role": "system", "content": _GENERATOR_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=True)},
        ],
        temperature=0.7,
        max_tokens=2200,
        response_format={"type": "json_object"},
    )
    content = ((resp.choices or [{}])[0].message.content or "").strip()
    if not content:
        raise RuntimeError("Generator returned an empty response")

    parsed = json.loads(content)
    # json_object mode always returns a dict; try common key names first,
    # then fall back to the first list value found in the response.
    raw_cases = None
    if isinstance(parsed, list):
        raw_cases = parsed
    elif isinstance(parsed, dict):
        for key in ("cases", "test_cases", "tests", "items", "results", "data"):
            if isinstance(parsed.get(key), list):
                raw_cases = parsed[key]
                break
        if raw_cases is None:
            # last-resort: grab the first list value regardless of key name
            for value in parsed.values():
                if isinstance(value, list):
                    raw_cases = value
                    break
    if not isinstance(raw_cases, list):
        raise RuntimeError(
            f"Generator returned an unexpected JSON shape. "
            f"Expected a list of test cases but got: {json.dumps(parsed)[:300]}"
        )

    normalized = []
    for raw in raw_cases[: max(1, min(int(count), 20))]:
        item = _normalize_case(raw)
        if item:
            normalized.append(item)

    if not normalized:
        raise RuntimeError("Generator returned no valid test cases")
    return normalized, target_model
