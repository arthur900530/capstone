from __future__ import annotations

import json
from typing import Any

from openai import AsyncOpenAI

from config import OPENAI_API_KEY, VERIFIER_MODEL

# The verifier intentionally grades two SEPARATE dimensions:
#
#   1. process_score — did the agent actually do the workflow the test was
#      designed to elicit? (Tool calls, ordering, evidence in trajectory.)
#   2. output_score  — does the final answer satisfy the observable artifact
#      described in success_criteria?
#
# A confident-looking but unsupported answer (the agent claims to have
# "verified" something without invoking the verifier tool) is the single
# worst failure mode for this product. The prompt below treats that as
# automatic hallucination and forces verdict=fail regardless of how nice
# the final answer reads.
_VERIFIER_PROMPT = (
    "You are an external evaluator grading one completed agent run.\n"
    "This is NOT self-reflection. You grade strictly against the supplied "
    "success_criteria, hard_failure_signals, and the evidence in the agent's "
    "TRAJECTORY and WORKSPACE FILES.\n"
    "\n"
    "# What you receive\n"
    "- test_case.prompt — the user instruction the agent was given.\n"
    "- test_case.success_criteria — the observable workflow + artifact required.\n"
    "- test_case.hard_failure_signals — definite-failure phrases or behaviors.\n"
    "- agent_run.tools_used — the set of tool names the agent ACTUALLY invoked. "
    "Observed by the runtime, not self-reported. Empty list means the agent "
    "invoked no tools at all.\n"
    "- agent_run.trajectory — the compacted event log (tool calls + observations).\n"
    "- agent_run.final_answer — the agent's free-text closing response.\n"
    "- agent_run.workspace_files — a dict mapping relative file paths to their "
    "FULL content as found on disk after the run. This is the GROUND TRUTH for "
    "any test that requires a written artifact. It is more reliable than the "
    "trajectory args, which may be truncated.\n"
    "\n"
    "# Process integrity (load-bearing rule — evaluate first)\n"
    "Workflow > output. A well-formatted final answer that lacks supporting "
    "tool evidence is a HALLUCINATION, not a pass.\n"
    "Apply these gates IN ORDER before scoring output quality:\n"
    "1. If success_criteria names a tool, skill, or methodology AND tools_used "
    "   is empty → hallucination_detected=true, verdict=\"fail\".\n"
    "2. If the final answer claims a concrete action was performed (e.g. "
    "   'I verified', 'I screened', 'I browsed', 'I saved the file') but the "
    "   trajectory shows no corresponding tool call → hallucination_detected=true, "
    "   verdict=\"fail\". Quote the unsupported claim in evidence_quote.\n"
    "3. If the agent fabricates a fact a real tool would have produced "
    "   (a registry record, a sanctions verdict, an LEI, a numeric score) "
    "   without a trajectory entry or workspace_files entry that produced it → "
    "   hallucination_detected=true, verdict=\"fail\".\n"
    "\n"
    "# Output quality — file artifacts (evaluate after process gates pass)\n"
    "When success_criteria requires a written file:\n"
    "- Check workspace_files FIRST. If the required path is absent → "
    "  the file was not written. output_score = 0, verdict = \"fail\".\n"
    "- If the file is present, evaluate its content against success_criteria "
    "  (correct fields, structure, key facts, verdict wording, etc.).\n"
    "- The trajectory's file_editor entry confirms the workflow step happened; "
    "  workspace_files confirms what was actually written to disk.\n"
    "- A file that exists but is empty or missing required fields still fails.\n"
    "\n"
    "# Output quality — non-file artifacts (evaluate after process gates pass)\n"
    "When success_criteria requires a non-file deliverable (a verdict in the "
    "final answer, a score, a structured table, a decision), evaluate the "
    "final_answer against success_criteria. Any hard_failure_signals match → fail.\n"
    "\n"
    "# Required JSON output\n"
    "Return a single JSON object with exactly these keys:\n"
    "  verdict                — \"pass\" | \"fail\" | \"error\"\n"
    "  rationale              — 2-4 sentences: cite trajectory evidence first, "
    "then workspace_files evidence, then final_answer quality.\n"
    "  evidence_quote         — verbatim quote from workspace_files, "
    "final_answer, or trajectory supporting the verdict.\n"
    "  confidence             — number in [0, 1].\n"
    "  process_score          — number in [0, 1]: 1.0 = agent invoked the "
    "right tools in the right order with real evidence; 0.0 = no tools called.\n"
    "  output_score           — number in [0, 1]: how well the artifact "
    "(file content or final answer) satisfies success_criteria.\n"
    "  hallucination_detected — boolean: true if any process-integrity gate "
    "above triggered, false otherwise.\n"
    "Quote verbatim from workspace_files or final_answer for evidence."
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


def _coerce_unit_interval(value: Any) -> float | None:
    """Clamp a model-provided number into [0, 1]; return None if unparseable.

    Returning None (rather than 0.0) preserves the distinction between
    "judge had no opinion on this dimension" and "judge scored zero".
    """
    if isinstance(value, bool):  # bool is a subclass of int; reject explicitly
        return None
    if isinstance(value, (int, float)):
        return max(0.0, min(float(value), 1.0))
    return None


async def verify_test_case_run(
    *,
    case_prompt: str,
    success_criteria: str,
    hard_failure_signals: list[str],
    final_answer: str,
    compact_trajectory: list[dict[str, Any]],
    tools_used: list[str] | None = None,
    workspace_files: dict[str, str] | None = None,
) -> dict[str, Any]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not configured")

    target_model = _resolve_openai_model(VERIFIER_MODEL)
    client = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=60.0)
    payload = {
        "test_case": {
            "prompt": case_prompt,
            "success_criteria": success_criteria,
            "hard_failure_signals": hard_failure_signals or [],
        },
        "agent_run": {
            "final_answer": final_answer,
            # tools_used is observed by the runtime (test_case_runner._callback)
            # and is the ground truth for "did the agent actually call X?".
            # The judge MUST cross-check claims in final_answer against this.
            "tools_used": list(tools_used or []),
            "trajectory": compact_trajectory[:200],
            # Full content of files written by the agent during the run.
            # This is the primary evidence for grading file-artifact tests.
            "workspace_files": dict(workspace_files or {}),
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
            max_completion_tokens=3000,
            response_format={"type": "json_object"},
        )
    except Exception:
        resp = await client.chat.completions.create(
            model=target_model,
            messages=messages,
            temperature=0,
            max_completion_tokens=3000,
        )
    content = ((resp.choices or [{}])[0].message.content or "").strip()
    parsed = json.loads(content) if content else {}
    verdict = str(parsed.get("verdict") or "error").lower()
    if verdict not in {"pass", "fail", "error"}:
        verdict = "error"
    confidence = _coerce_unit_interval(parsed.get("confidence")) or 0.0

    process_score = _coerce_unit_interval(parsed.get("process_score"))
    output_score = _coerce_unit_interval(parsed.get("output_score"))
    hallucination_raw = parsed.get("hallucination_detected")
    hallucination_detected = bool(hallucination_raw) if isinstance(hallucination_raw, bool) else None

    # Defense-in-depth: if the judge flagged a hallucination but somehow still
    # returned verdict="pass", force-fail. This is cheap and prevents one
    # specific class of judge inconsistency from leaking false positives into
    # the dashboard.
    if hallucination_detected and verdict == "pass":
        verdict = "fail"

    return {
        "verdict": verdict,
        "rationale": str(parsed.get("rationale") or "").strip(),
        "evidence_quote": str(parsed.get("evidence_quote") or "").strip(),
        "confidence": confidence,
        "process_score": process_score,
        "output_score": output_score,
        "hallucination_detected": hallucination_detected,
    }
