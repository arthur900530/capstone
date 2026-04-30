from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from config import OPENAI_API_KEY, VERIFIER_MODEL

_VERIFIER_PROMPT_BASE = (
    "You are an external evaluator grading one completed agent run.\n"
    "This is not self-reflection: grade only against explicit success criteria and failure signals.\n"
    "Return strict JSON with keys: verdict, rationale, evidence_quote, confidence.\n"
    'verdict must be one of: "pass", "fail", "error".\n'
    "confidence must be a number from 0 to 1.\n"
    "Be concise and quote verbatim text from the final answer for evidence when possible."
)

_VERIFIER_PROMPT_WITH_WORKFLOW = _VERIFIER_PROMPT_BASE + (
    "\n\nIf the test_case includes an expected_workflow, ALSO grade per-step "
    "adherence and include an additional key 'workflow_alignment' in your "
    "JSON response with this exact shape:\n"
    '  {"steps": [{"path": [<int>, ...], "satisfied": <bool>, "evidence": <str>}, ...]}\n'
    "Each entry's 'path' is the index path into expected_workflow.root_steps "
    "and then .children recursively (e.g. [0] is the first root step, [1, 0] "
    "is the first child of the second root step). You MUST grade every leaf "
    "step (a step with empty 'children'). Adherence is BINARY: 'satisfied' is "
    "true if the agent_run.trajectory shows the step was completed, otherwise "
    "false. 'evidence' should be a short fragment from the trajectory or "
    "final answer that supports your decision. Do NOT return a 'coverage' or "
    "any aggregate score; the consumer derives those from the step list."
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


def _sanitize_alignment(parsed: Any) -> dict | None:
    """Coerce the LLM ``workflow_alignment`` payload into a safe shape.

    Drops malformed step entries silently rather than failing the whole run.
    Returns ``None`` when there's nothing usable.
    """

    if not isinstance(parsed, dict):
        return None
    raw_steps = parsed.get("steps")
    if not isinstance(raw_steps, list):
        return None
    cleaned: list[dict[str, Any]] = []
    for entry in raw_steps:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        if not isinstance(path, list) or not all(isinstance(i, int) for i in path):
            continue
        satisfied = entry.get("satisfied")
        cleaned.append(
            {
                "path": list(path),
                "satisfied": bool(satisfied) if satisfied is not None else False,
                "evidence": str(entry.get("evidence") or "")[:500],
            }
        )
    if not cleaned:
        return None
    return {"steps": cleaned}


async def verify_test_case_run(
    *,
    case_prompt: str,
    success_criteria: str,
    hard_failure_signals: list[str],
    final_answer: str,
    compact_trajectory: list[dict[str, Any]],
    expected_workflow: dict | None = None,
) -> dict[str, Any]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    target_model = _resolve_openai_model(VERIFIER_MODEL)
    client = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=45.0)

    test_case_payload: dict[str, Any] = {
        "prompt": case_prompt,
        "success_criteria": success_criteria,
        "hard_failure_signals": hard_failure_signals or [],
    }
    if expected_workflow:
        test_case_payload["expected_workflow"] = expected_workflow

    payload = {
        "test_case": test_case_payload,
        "agent_run": {
            "final_answer": final_answer,
            "trajectory": compact_trajectory[:200],
        },
    }
    system_prompt = (
        _VERIFIER_PROMPT_WITH_WORKFLOW if expected_workflow else _VERIFIER_PROMPT_BASE
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=True)},
    ]
    # Try structured JSON mode first; fall back to plain completion for models
    # that don't support response_format (newer OpenAI models, fine-tuned models).
    try:
        resp = await client.chat.completions.create(
            model=target_model,
            messages=messages,
            temperature=1.0,
            max_completion_tokens=900 if expected_workflow else 700,
            response_format={"type": "json_object"},
        )
    except Exception:
        resp = await client.chat.completions.create(
            model=target_model,
            messages=messages,
            temperature=1.0,
            max_completion_tokens=900 if expected_workflow else 700,
        )
    content = ((resp.choices or [{}])[0].message.content or "").strip()
    parsed = json.loads(content) if content else {}
    verdict = str(parsed.get("verdict") or "error").lower()
    if verdict not in {"pass", "fail", "error"}:
        verdict = "error"
    confidence_raw = parsed.get("confidence")
    confidence = float(confidence_raw) if isinstance(confidence_raw, (int, float)) else 0.0
    confidence = max(0.0, min(confidence, 1.0))
    workflow_alignment = (
        _sanitize_alignment(parsed.get("workflow_alignment")) if expected_workflow else None
    )
    return {
        "verdict": verdict,
        "rationale": str(parsed.get("rationale") or "").strip(),
        "evidence_quote": str(parsed.get("evidence_quote") or "").strip(),
        "confidence": confidence,
        "workflow_alignment": workflow_alignment,
    }
