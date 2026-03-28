"""
Reflector module for the Reflexion pipeline.

Generates a verbal self-reflection when the agent fails a task.
The reflection is a concise, actionable insight the agent can use
on subsequent attempts — this is the core mechanism of the
Reflexion paper (Shinn et al., 2023).

Current strategy: REFLEXION (synthesized insight only).
LAST_ATTEMPT and LAST_ATTEMPT_AND_REFLEXION can be added later
via the `include_raw_trajectory` flag.
"""

import logging
from typing import Optional

from .evaluator import EvaluationResult

logger = logging.getLogger(__name__)

# ── Prompt template for self-reflection ───────────────────────────────
# Adapted from the pattern in the original Reflexion repo
# (programming_runs/generators/generator_utils.py → generic_generate_self_reflection)

REFLECTOR_SYSTEM_PROMPT = """\
You are an expert at analyzing failed attempts by an AI coding agent. \
Your job is to produce a short, actionable self-reflection that will \
help the agent avoid the same mistakes on its next attempt.

You will receive:
1. The TASK the agent was asked to perform.
2. The TRAJECTORY — the agent's actions and outputs.
3. The EVALUATION — a summary of what went wrong.

Write a reflection in 3–5 sentences that:
- States what the agent did wrong or missed.
- Explains *why* it likely went wrong.
- Suggests a concrete strategy for doing better next time.

Respond with ONLY the reflection text — no JSON, no headers, no markdown.
"""

REFLECTOR_USER_TEMPLATE = """\
TASK:
{task}

TRAJECTORY:
{trajectory}

EVALUATION:
success: {success}
score: {score}
failing_step: {failing_step}
summary: {eval_summary}
"""


def generate_reflection(
    task: str,
    trajectory: str,
    evaluation: EvaluationResult,
    llm_call: callable,
    include_raw_trajectory: bool = False,
) -> str:
    """Generate a verbal self-reflection on a failed task attempt.

    Parameters
    ----------
    task : str
        The original task instruction.
    trajectory : str
        The full execution log from the agent's attempt.
    evaluation : EvaluationResult
        The structured evaluation of the attempt (from evaluator.py).
    llm_call : callable
        Function accepting (system_prompt, user_prompt) -> str.
    include_raw_trajectory : bool, optional
        If True, prepends the raw trajectory to the reflection output.
        This enables the LAST_ATTEMPT_AND_REFLEXION strategy.
        Default is False (pure REFLEXION strategy).

    Returns
    -------
    str
        The verbal reflection text.  When include_raw_trajectory is True,
        the raw trajectory is prepended with a header separator.
    """
    user_prompt = REFLECTOR_USER_TEMPLATE.format(
        task=task,
        trajectory=trajectory,
        success=evaluation.success,
        score=evaluation.score,
        failing_step=evaluation.failing_step or "N/A",
        eval_summary=evaluation.summary,
    )

    logger.info("Generating reflection for task: %.80s...", task)
    reflection = llm_call(REFLECTOR_SYSTEM_PROMPT, user_prompt)
    reflection = reflection.strip()
    logger.info("Reflection generated (%d chars)", len(reflection))

    if include_raw_trajectory:
        header = "=== PREVIOUS ATTEMPT (raw transcript) ===\n"
        separator = "\n\n=== REFLECTION (lessons learned) ===\n"
        return header + trajectory + separator + reflection

    return reflection
