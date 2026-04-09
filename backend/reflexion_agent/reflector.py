"""
Reflector module for the Reflexion pipeline.

Generates a verbal self-reflection when the agent fails a task.
The reflection is a concise, actionable insight the agent can use
on subsequent attempts — this is the core mechanism of the
Reflexion paper (Shinn et al., 2023).

Fix 6: The reflector now receives only the **critique string** from
the evaluator rather than the full EvaluationResult object.  This
keeps parsing concerns inside the evaluator and gives the reflector
exactly the information it needs: what went wrong, in plain language.

Current strategy: REFLEXION (synthesized insight only).
LAST_ATTEMPT and LAST_ATTEMPT_AND_REFLEXION can be added later
via the `include_raw_trajectory` flag.
"""

import logging

logger = logging.getLogger(__name__)

# ── Prompt template for self-reflection ───────────────────────────────
# The reflector sees: the task, the trajectory, and the evaluator's
# critique sentence.  It does NOT see the raw score or success flag —
# those are gating decisions, not reflection inputs.

REFLECTOR_SYSTEM_PROMPT = """\
You are an expert at analyzing failed attempts by an AI coding agent. \
Your job is to produce a short, actionable self-reflection that will \
help the agent avoid the same mistakes on its next attempt.

You will receive:
1. The TASK the agent was asked to perform.
2. The TRAJECTORY — the agent's actions and outputs.
3. The CRITIQUE — the evaluator's summary of what went wrong.

Write a reflection in 3–5 sentences that covers:
- What the agent did wrong or missed.
- Why it likely went wrong (root cause, not just symptom).
- A concrete, alternative strategy for the next attempt.
- Any tool-usage or process improvements to try.

Respond with ONLY the reflection text — no JSON, no headers, no markdown.
"""

REFLECTOR_USER_TEMPLATE = """\
TASK:
{task}

TRAJECTORY:
{trajectory}

CRITIQUE:
{critique}
"""


def generate_reflection(
    task: str,
    trajectory: str,
    critique: str,
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
    critique : str
        The evaluator's one-sentence summary of what went wrong.
        This is the *only* evaluator output the reflector sees —
        it does not receive the numeric score or binary success flag.
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
        critique=critique,
    )

    logger.info(
        "[reflector] Generating reflection for task: %.80s... | critique: %.120s",
        task, critique,
    )
    reflection = llm_call(REFLECTOR_SYSTEM_PROMPT, user_prompt)
    reflection = reflection.strip()
    logger.info(
        "[reflector] Reflection generated (%d chars) for task: %.80s...",
        len(reflection), task,
    )

    if include_raw_trajectory:
        header = "=== PREVIOUS ATTEMPT (raw transcript) ===\n"
        separator = "\n\n=== REFLECTION (lessons learned) ===\n"
        return header + trajectory + separator + reflection

    return reflection
