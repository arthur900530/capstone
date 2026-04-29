from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from config import OPENAI_API_KEY, VERIFIER_MODEL

_VERIFIER_PROMPT = (
    "You are an external evaluator grading one completed agent run.\n"
    "This is not self-reflection: grade only against explicit success criteria and failure signals.\n"
    "Return strict JSON with keys: verdict, rationale, evidence_quote, confidence.\n"
    'verdict must be one of: "pass", "fail", "error".\n'
    "confidence must be a number from 0 to 1.\n"
    "Be concise and quote verbatim text from the final answer for evidence when possible."
)


def _resolve_openai_model(model: str) -> str:
    raw = (model or "").strip()
    if not raw:
        raise RuntimeError(
            "Auto-test generation and verification require an OpenAI model. "
            "VERIFIER_MODEL is empty. Set VERIFIER_MODEL to an openai/... value "
            "(e.g. openai/gpt-4o-mini)."
        )
    while "/" in raw:
        provider, _, bare = raw.partition("/")
        if provider.lower() != "openai":
            raise RuntimeError(
                "Auto-test generation and verification require an OpenAI model. "
                f"'{model}' is not an OpenAI model. "
                "Set VERIFIER_MODEL to an openai/... value (e.g. openai/gpt-4o-mini)."
            )
        raw = bare
    return raw or "gpt-4o-mini"


async def verify_test_case_run(
    *,
    case_prompt: str,
    success_criteria: str,
    hard_failure_signals: list[str],
    final_answer: str,
    compact_trajectory: list[dict[str, Any]],
) -> dict[str, Any]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    target_model = _resolve_openai_model(VERIFIER_MODEL)
    client = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=45.0)
    payload = {
        "test_case": {
            "prompt": case_prompt,
            "success_criteria": success_criteria,
            "hard_failure_signals": hard_failure_signals or [],
        },
        "agent_run": {
            "final_answer": final_answer,
            "trajectory": compact_trajectory[:200],
        },
    }
    messages = [
        {"role": "system", "content": _VERIFIER_PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=True)},
    ]
    # Try structured JSON mode first; fall back to plain completion for models
    # that don't support response_format (newer OpenAI models, fine-tuned models).
    try:
        resp = await client.chat.completions.create(
            model=target_model,
            messages=messages,
            temperature=0,
            max_completion_tokens=700,
            response_format={"type": "json_object"},
        )
    except Exception:
        resp = await client.chat.completions.create(
            model=target_model,
            messages=messages,
            temperature=0,
            max_completion_tokens=700,
        )
    content = ((resp.choices or [{}])[0].message.content or "").strip()
    parsed = json.loads(content) if content else {}
    verdict = str(parsed.get("verdict") or "error").lower()
    if verdict not in {"pass", "fail", "error"}:
        verdict = "error"
    confidence_raw = parsed.get("confidence")
    confidence = float(confidence_raw) if isinstance(confidence_raw, (int, float)) else 0.0
    confidence = max(0.0, min(confidence, 1.0))
    return {
        "verdict": verdict,
        "rationale": str(parsed.get("rationale") or "").strip(),
        "evidence_quote": str(parsed.get("evidence_quote") or "").strip(),
        "confidence": confidence,
    }
