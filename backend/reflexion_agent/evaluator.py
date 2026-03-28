"""
Evaluator module for the Reflexion pipeline.

Uses an LLM-as-judge pattern: sends the agent's execution trajectory
to the language model and asks it to assess success/failure and
identify the first failing step.
"""

import json
import logging
from dataclasses import dataclass, asdict
from typing import Optional

logger = logging.getLogger(__name__)

# ── Prompt template for the LLM judge ────────────────────────────────
# The LLM receives the original task instruction, the agent's full
# trajectory (conversation log / actions / outputs), and is asked to
# return a structured JSON verdict.

EVALUATOR_SYSTEM_PROMPT = """\
You are an expert evaluator assessing whether an AI coding agent \
successfully completed a software engineering task.

You will receive:
1. The TASK the agent was asked to perform.
2. The TRAJECTORY — the full log of the agent's actions and outputs.

Evaluate the trajectory and respond with ONLY a JSON object (no markdown, \
no commentary) in this exact schema:

{
  "success": true or false,
  "score": 0.0 to 1.0,
  "failing_step": "description of first failing step, or null if success",
  "summary": "one-sentence explanation of your verdict"
}

Scoring guide:
- 1.0 = task fully and correctly completed
- 0.5–0.9 = partially completed (some steps correct)
- 0.0–0.4 = mostly or entirely failed
"""

EVALUATOR_USER_TEMPLATE = """\
TASK:
{task}

TRAJECTORY:
{trajectory}
"""


@dataclass
class EvaluationResult:
    """Structured output from evaluate_trajectory()."""
    success: bool
    score: float
    failing_step: Optional[str]
    summary: str

    def to_dict(self) -> dict:
        return asdict(self)


def _parse_llm_verdict(raw_text: str) -> EvaluationResult:
    """Parse the LLM's JSON response into an EvaluationResult.

    Falls back to a failure result if parsing fails so the pipeline
    never crashes on malformed LLM output.
    """
    try:
        # Strip markdown fences if the LLM wraps its response
        cleaned = raw_text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1]
            cleaned = cleaned.rsplit("```", 1)[0]

        data = json.loads(cleaned)
        return EvaluationResult(
            success=bool(data.get("success", False)),
            score=float(data.get("score", 0.0)),
            failing_step=data.get("failing_step"),
            summary=str(data.get("summary", "")),
        )
    except (json.JSONDecodeError, KeyError, ValueError, TypeError) as exc:
        logger.warning("Failed to parse LLM evaluation response: %s", exc)
        return EvaluationResult(
            success=False,
            score=0.0,
            failing_step=None,
            summary=f"Evaluation parse error: {exc}",
        )


def evaluate_trajectory(
    task: str,
    trajectory: str,
    llm_call: callable,
) -> EvaluationResult:
    """Evaluate an agent's execution trajectory using an LLM judge.

    Parameters
    ----------
    task : str
        The original task instruction given to the agent.
    trajectory : str
        The full execution log (conversation history, actions, outputs).
    llm_call : callable
        A function that accepts (system_prompt: str, user_prompt: str)
        and returns the LLM's text response.  This keeps the evaluator
        decoupled from any specific LLM client library.

    Returns
    -------
    EvaluationResult
        Structured verdict with success flag, score, failing step, and
        human-readable summary.
    """
    user_prompt = EVALUATOR_USER_TEMPLATE.format(
        task=task,
        trajectory=trajectory,
    )

    logger.info("Evaluating trajectory (%d chars) for task: %.80s...", len(trajectory), task)
    raw_response = llm_call(EVALUATOR_SYSTEM_PROMPT, user_prompt)
    result = _parse_llm_verdict(raw_response)
    logger.info("Evaluation result: success=%s score=%.2f", result.success, result.score)
    return result
