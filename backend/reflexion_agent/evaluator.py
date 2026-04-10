"""
Evaluator module for the Reflexion pipeline.

Uses an LLM-as-judge pattern: sends the agent's execution trajectory
to the language model and asks it to assess success/failure and
identify the first failing step.

Output format (Fix 2)
---------------------
The judge is asked to reply with four plain labeled lines instead of JSON.
Line-oriented output is far more forgiving: extra prose, markdown fences,
or minor punctuation variations in *other* lines do not break the parser
for the fields it *did* emit correctly.  Each field is extracted with its
own regex so a single missing or malformed line only affects that field —
it never collapses the entire response to success=False / score=0.0.

Conservative parse defaults
---------------------------
- SUCCESS  → False  (safe: assume failure if we cannot read the verdict)
- SCORE    → 0.5   (neutral: do not punish the agent for a judge format error)
- FAILING_STEP → None
- SUMMARY  → placeholder string
"""

import re
import logging
from dataclasses import dataclass, asdict
from typing import Optional

logger = logging.getLogger(__name__)

# ── Prompt template for the LLM judge ────────────────────────────────
# Plain labeled lines are much easier for the model to emit consistently
# than strict JSON, and each field can be parsed independently, so a
# formatting slip in one line does not destroy the others.

EVALUATOR_SYSTEM_PROMPT = """\
You are an expert evaluator assessing whether an AI coding agent \
successfully completed a given task. Infer the task from the trajectory.

You will receive:
1. The TRAJECTORY — the full log of the agent's actions and outputs.
2. The TASK the agent was asked to perform.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EVALUATION DIMENSIONS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Judge the agent on these five dimensions. You do NOT have ground-truth \
answers — evaluate process quality and deliverable presence, not perfection.

1. DELIVERABLE PRESENCE
   Did the agent produce the requested output (code, file, answer, change)?
   A deliverable exists even if it has minor flaws.

2. FUNCTIONAL CORRECTNESS
   Does the output work for its stated purpose? Syntax errors, crash-on-run, \
or completely wrong logic count as broken. Minor style or formatting issues \
do NOT count as broken.

3. PROCESS SOUNDNESS
   Did the agent use its tools effectively? Did it recover from errors rather \
than repeat the same failing action? An agent that tries reasonable strategies \
and adapts is sound even if the result is imperfect.

4. SCOPE COMPLETENESS
   Were all explicitly required parts of the task addressed? A task that asks \
for three things but the agent only did two is incomplete. However, if the \
agent addressed the core requirement and skipped only minor or implied steps, \
treat it as substantially complete.

5. TOOL USAGE
   Were the right tools used for each step? Inefficient but correct tool use \
is acceptable. Only flag tool usage as a failing step if it caused the task \
to fail.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SCORING GUIDE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
0.9–1.0  All required deliverables present and functional; clean execution.
0.7–0.8  Core deliverable present and working; minor gaps in completeness \
or style.
0.5–0.6  Primary deliverable exists but has significant gaps or partial \
breakage that does not fully block use.
0.3–0.4  Substantial effort shown but the primary deliverable is broken or \
missing key parts.
0.0–0.2  No meaningful progress; the agent failed to address the task or \
produced output that cannot be used.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SUCCESS DECISION RULES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Set SUCCESS: true when the agent's output is adequate for the task, \
meaning a person could use or build on it with little or no rework. \
This includes cases where:
  - Output formatting is perfect AND the content is correct.
  - Non-critical or implied steps were skipped.
  - The agent produced a slightly different but valid approach.
  - Minor unused imports, style warnings, or linter nits are present.

Set SUCCESS: false ONLY when a primary outcome is broken or absent:
  - The requested file, function, or change was never created.
  - Code has a syntax error or crashes immediately on execution.
  - The agent gave up, looped without progress, or hit an unrecoverable error.
  - A required step was explicitly listed in the task and completely omitted.

It is valid to set SUCCESS: false with a SCORE of 0.7 or higher when the \
deliverable nearly passes but has a single critical flaw. In that case, \
explain the specific flaw in SUMMARY.

Additionally, please be critical and never assume that the agent did well. 
Be the devil's advocate so that this evaluation is as accurate as possible. 
Being accurate is more important than being nice - it allows our agent to \ 
potentially learn from its mistakes instead of allowing those mistakes to \
propagate downstream. 

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
OUTPUT FORMAT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Reply with EXACTLY these four labeled lines and nothing else \
(no markdown, no extra commentary):

SUCCESS: true or false
SCORE: a number between 0.0 and 1.0
FAILING_STEP: the first step that failed, or none if the task succeeded
SUMMARY: one sentence explaining your verdict
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


# ── Per-field regex patterns ──────────────────────────────────────────
# Each pattern is intentionally lenient about surrounding whitespace and
# capitalisation so minor deviations (e.g. "Success:" or "SUCCESS :") still
# match.  The capture group grabs everything to the end of that line.

_RE_SUCCESS = re.compile(r"SUCCESS\s*:\s*(true|false)", re.IGNORECASE)
_RE_SCORE   = re.compile(r"SCORE\s*:\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)
_RE_FAILING = re.compile(r"FAILING_STEP\s*:\s*(.+)", re.IGNORECASE)
_RE_SUMMARY = re.compile(r"SUMMARY\s*:\s*(.+)", re.IGNORECASE)


def _parse_llm_verdict(raw_text: str) -> EvaluationResult:
    """Parse the LLM's labeled-line response into an EvaluationResult.

    Each field is extracted independently with a regex.  Missing or
    malformed fields fall back to conservative defaults and are logged
    individually so testers can pinpoint exactly which field caused a
    mismatch without having to decode the full raw response.

    Parse defaults
    --------------
    SUCCESS      → False  (conservative: assume failure if unreadable)
    SCORE        → 0.5   (neutral: do not bias toward re-try on format error)
    FAILING_STEP → None
    SUMMARY      → placeholder string
    """
    text = raw_text.strip()

    # ── SUCCESS ──────────────────────────────────────────────────────
    m_success = _RE_SUCCESS.search(text)
    if m_success:
        success = m_success.group(1).lower() == "true"
        logger.debug("[evaluator parse] SUCCESS=%s (from response)", success)
    else:
        success = False
        logger.warning(
            "[evaluator parse] SUCCESS field missing or unreadable — defaulting to False. "
            "Raw response snippet: %.200s",
            text,
        )

    # ── SCORE ────────────────────────────────────────────────────────
    m_score = _RE_SCORE.search(text)
    if m_score:
        try:
            score = float(m_score.group(1))
            # Guard against the model writing a number outside the expected range.
            if not (0.0 <= score <= 1.0):
                logger.warning(
                    "[evaluator parse] SCORE %.4f is outside [0.0, 1.0] — clamping",
                    score,
                )
                score = max(0.0, min(1.0, score))
            logger.debug("[evaluator parse] SCORE=%.2f (from response)", score)
        except ValueError:
            score = 0.5
            logger.warning(
                "[evaluator parse] SCORE value '%s' could not be converted to float "
                "— defaulting to 0.5 (neutral)",
                m_score.group(1),
            )
    else:
        score = 0.5
        logger.warning(
            "[evaluator parse] SCORE field missing or unreadable — defaulting to 0.5 (neutral). "
            "Raw response snippet: %.200s",
            text,
        )

    # ── FAILING_STEP ─────────────────────────────────────────────────
    m_failing = _RE_FAILING.search(text)
    if m_failing:
        raw_failing = m_failing.group(1).strip()
        # The model sometimes writes "none" or "n/a" when no step failed.
        failing_step = None if raw_failing.lower() in ("none", "n/a", "null", "") else raw_failing
        logger.debug("[evaluator parse] FAILING_STEP=%r (from response)", failing_step)
    else:
        failing_step = None
        logger.debug("[evaluator parse] FAILING_STEP field not found — defaulting to None")

    # ── SUMMARY ──────────────────────────────────────────────────────
    m_summary = _RE_SUMMARY.search(text)
    if m_summary:
        summary = m_summary.group(1).strip()
        logger.debug("[evaluator parse] SUMMARY found (from response)")
    else:
        summary = "[evaluator: SUMMARY field could not be parsed from response]"
        logger.warning(
            "[evaluator parse] SUMMARY field missing or unreadable — using placeholder. "
            "Raw response snippet: %.200s",
            text,
        )

    return EvaluationResult(
        success=success,
        score=score,
        failing_step=failing_step,
        summary=summary,
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

    logger.info(
        "[evaluator] Sending trajectory (%d chars) to judge for task: %.80s...",
        len(trajectory), task,
    )
    raw_response = llm_call(EVALUATOR_SYSTEM_PROMPT, user_prompt)
    logger.debug("[evaluator] Raw judge response: %.500s", raw_response)

    result = _parse_llm_verdict(raw_response)
    logger.info(
        "[evaluator] Parsed result: success=%s score=%.2f failing_step=%r",
        result.success, result.score, result.failing_step,
    )
    return result
