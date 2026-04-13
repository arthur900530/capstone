"""
Reflexion pipeline tests — Layers 1 & 2.

Layer 1: Unit tests for pure functions (no LLM, no Docker, no network).
Layer 2: Integration tests with mock LLM calls that exercise the decision
         logic of multiple components working together.

Run with:
    cd capstone_frontend/backend

    # Quick — just pass/fail:
    pytest reflexion_agent/tests/test_reflexion_fixes.py -v

    # Verbose — see all logging from the tests AND the production code:
    pytest reflexion_agent/tests/test_reflexion_fixes.py -v -s --log-cli-level=DEBUG
"""

import logging
import os
import pytest

# Set up a test-scoped logger so our verbose messages are clearly labeled
# in the pytest output.  Production code uses its own loggers; these are
# *additional* messages that narrate the test flow for the reader.
log = logging.getLogger("test_reflexion_fixes")

# ═══════════════════════════════════════════════════════════════════════
# 1A — _parse_llm_verdict  (evaluator.py, Fix 2)
#
# The parser uses per-field regexes to extract SUCCESS, SCORE,
# FAILING_STEP, and SUMMARY from the LLM's labeled-line response.
# Each field falls back to a safe default when missing / malformed.
# ═══════════════════════════════════════════════════════════════════════
from reflexion_agent.evaluator import _parse_llm_verdict


class TestParseLlmVerdict:
    """Test group 1A: evaluator's labeled-line parser."""

    def test_happy_path_all_fields_present(self):
        """All four fields present and well-formed → parsed correctly."""
        raw = (
            "SUCCESS: true\n"
            "SCORE: 0.92\n"
            "FAILING_STEP: none\n"
            "SUMMARY: The agent completed the task successfully."
        )
        result = _parse_llm_verdict(raw)

        assert result.success is True
        assert result.score == pytest.approx(0.92)
        assert result.failing_step is None  # "none" → Python None
        assert result.summary == "The agent completed the task successfully."

    def test_missing_score_defaults_to_neutral(self):
        """Missing SCORE → defaults to 0.5, NOT 0.0 (core bug fix)."""
        raw = (
            "SUCCESS: false\n"
            "FAILING_STEP: Step 3 — file not created\n"
            "SUMMARY: Agent did not produce output file."
        )
        result = _parse_llm_verdict(raw)

        assert result.success is False
        # The critical assertion: before the fix, a missing SCORE
        # defaulted to 0.0 which biased the loop toward retrying.
        assert result.score == pytest.approx(0.5)
        assert result.failing_step == "Step 3 — file not created"

    def test_missing_success_defaults_to_false(self):
        """Missing SUCCESS field → safe default False."""
        raw = (
            "SCORE: 0.8\n"
            "FAILING_STEP: none\n"
            "SUMMARY: Looks good overall."
        )
        result = _parse_llm_verdict(raw)

        assert result.success is False

    def test_missing_summary_uses_placeholder(self):
        """Missing SUMMARY → recognizable placeholder string."""
        raw = (
            "SUCCESS: true\n"
            "SCORE: 0.9\n"
            "FAILING_STEP: none\n"
        )
        result = _parse_llm_verdict(raw)

        assert "[evaluator: SUMMARY field could not be parsed from response]" in result.summary

    def test_completely_garbled_response(self):
        """No labeled lines at all → conservative defaults everywhere."""
        raw = "I think the agent did a pretty good job overall."
        result = _parse_llm_verdict(raw)

        assert result.success is False
        assert result.score == pytest.approx(0.5)
        assert result.failing_step is None
        assert "[evaluator:" in result.summary  # placeholder

    def test_markdown_fenced_response(self):
        """Fields wrapped in triple backticks still parse (regex searches full text)."""
        raw = (
            "```\n"
            "SUCCESS: true\n"
            "SCORE: 0.88\n"
            "FAILING_STEP: none\n"
            "SUMMARY: Task completed inside fenced block.\n"
            "```"
        )
        result = _parse_llm_verdict(raw)

        assert result.success is True
        assert result.score == pytest.approx(0.88)
        assert result.failing_step is None
        assert "fenced block" in result.summary

    def test_case_insensitivity(self):
        """Mixed-case field names still parse (regex uses re.IGNORECASE)."""
        raw = (
            "success: True\n"
            "Score: 0.7\n"
            "Failing_Step: none\n"
            "Summary: Mixed case works."
        )
        result = _parse_llm_verdict(raw)

        assert result.success is True
        assert result.score == pytest.approx(0.7)

    def test_score_out_of_range_high_clamped(self):
        """SCORE above 1.0 → clamped to 1.0."""
        raw = (
            "SUCCESS: true\n"
            "SCORE: 1.5\n"
            "FAILING_STEP: none\n"
            "SUMMARY: Over-scored."
        )
        result = _parse_llm_verdict(raw)

        assert result.score == pytest.approx(1.0)

    def test_score_negative_not_matched(self):
        """Negative SCORE → regex doesn't match (no minus in pattern) → neutral 0.5.

        The SCORE regex only captures non-negative numbers: [0-9]*\\.?[0-9]+
        A leading minus sign means the regex never fires, so the parser
        treats the field as "missing" and falls back to 0.5 (neutral).
        """
        raw = (
            "SUCCESS: false\n"
            "SCORE: -0.3\n"
            "FAILING_STEP: Step 1\n"
            "SUMMARY: Under-scored."
        )
        result = _parse_llm_verdict(raw)

        assert result.score == pytest.approx(0.5)

    def test_failing_step_none_string(self):
        """FAILING_STEP: "none" (string) → normalized to Python None."""
        raw = (
            "SUCCESS: true\n"
            "SCORE: 0.95\n"
            "FAILING_STEP: none\n"
            "SUMMARY: All good."
        )
        result = _parse_llm_verdict(raw)

        assert result.failing_step is None

    def test_failing_step_na_string(self):
        """FAILING_STEP: "N/A" → normalized to Python None."""
        raw = (
            "SUCCESS: true\n"
            "SCORE: 0.9\n"
            "FAILING_STEP: N/A\n"
            "SUMMARY: Everything passed."
        )
        result = _parse_llm_verdict(raw)

        assert result.failing_step is None

    def test_extra_prose_around_fields(self):
        """Fields embedded in conversational prose still extracted by regex."""
        raw = (
            "Here is my evaluation:\n"
            "SUCCESS: true\n"
            "I gave a SCORE: 0.9\n"
            "FAILING_STEP: none\n"
            "SUMMARY: Worked well despite surrounding prose."
        )
        result = _parse_llm_verdict(raw)

        assert result.success is True
        assert result.score == pytest.approx(0.9)
        assert result.failing_step is None
        assert "prose" in result.summary


# ═══════════════════════════════════════════════════════════════════════
# 1B — _parse_score_threshold  (agent.py, Fix 1)
#
# Reads REFLEXION_SCORE_THRESHOLD from the environment and returns
# a float in [0.0, 1.0], falling back to 0.75 on bad input.
# We use monkeypatch to set/unset env vars without side effects.
# ═══════════════════════════════════════════════════════════════════════
from reflexion_agent.agent import _parse_score_threshold


class TestParseScoreThreshold:
    """Test group 1B: env-var based threshold parser."""

    def test_default_when_unset(self, monkeypatch):
        """No env var → returns the default 0.75."""
        monkeypatch.delenv("REFLEXION_SCORE_THRESHOLD", raising=False)
        assert _parse_score_threshold() == pytest.approx(0.75)

    def test_valid_float(self, monkeypatch):
        """Valid float string → parsed correctly."""
        monkeypatch.setenv("REFLEXION_SCORE_THRESHOLD", "0.6")
        assert _parse_score_threshold() == pytest.approx(0.6)

    def test_non_numeric_string_falls_back(self, monkeypatch):
        """Non-numeric string → fallback to 0.75."""
        monkeypatch.setenv("REFLEXION_SCORE_THRESHOLD", "high")
        assert _parse_score_threshold() == pytest.approx(0.75)

    def test_above_range_clamped(self, monkeypatch):
        """Value > 1.0 → clamped to 1.0."""
        monkeypatch.setenv("REFLEXION_SCORE_THRESHOLD", "1.5")
        assert _parse_score_threshold() == pytest.approx(1.0)

    def test_below_range_clamped(self, monkeypatch):
        """Value < 0.0 → clamped to 0.0."""
        monkeypatch.setenv("REFLEXION_SCORE_THRESHOLD", "-0.2")
        assert _parse_score_threshold() == pytest.approx(0.0)

    def test_boundary_zero(self, monkeypatch):
        """Exactly 0.0 → accepted as-is."""
        monkeypatch.setenv("REFLEXION_SCORE_THRESHOLD", "0.0")
        assert _parse_score_threshold() == pytest.approx(0.0)

    def test_boundary_one(self, monkeypatch):
        """Exactly 1.0 → accepted as-is."""
        monkeypatch.setenv("REFLEXION_SCORE_THRESHOLD", "1.0")
        assert _parse_score_threshold() == pytest.approx(1.0)


# ═══════════════════════════════════════════════════════════════════════
# 1C — _serialize_trajectory  (agent.py, Fix 3)
#
# Converts OpenHands event objects into a human-readable transcript
# using duck typing (getattr checks).  We provide lightweight mock
# classes so we never import the SDK.
# ═══════════════════════════════════════════════════════════════════════
from reflexion_agent.agent import _serialize_trajectory


class MockMessage:
    """Mimics a MessageEvent (has a 'role' attribute)."""
    def __init__(self, role, content):
        self.role = role
        self.content = content
        self.extended_content = None
        self.reasoning_content = None


class MockAction:
    """Mimics an ActionEvent (has 'tool_call' or 'action')."""
    def __init__(self, tool_name, action_str):
        self.tool_call = None        # use older SDK path
        self.action = action_str
        self.tool_name = tool_name
        self.thought = None
        self.reasoning_content = None


class MockObservation:
    """Mimics an ObservationEvent (has 'observation' or 'result')."""
    def __init__(self, tool_name, result_text):
        self.observation = None
        self.result = result_text
        self.tool_name = tool_name


class TestSerializeTrajectory:
    """Test group 1C: trajectory serializer."""

    def test_mixed_events(self):
        """A message, action, and observation are serialized with correct labels."""
        events = [
            MockMessage("user", "Write code"),
            MockAction("terminal", "ls -la"),
            MockObservation("terminal", "file1.py"),
        ]
        output = _serialize_trajectory(events)

        assert "[USER]" in output
        assert "[Turn 1] [ACTION] terminal" in output
        assert "[OBSERVATION]" in output

    def test_empty_event_list(self):
        """No events → placeholder string."""
        output = _serialize_trajectory([])
        assert output == "[trajectory: no events captured]"

    def test_long_observation_truncated(self):
        """Observation over 800 chars → truncated with a note."""
        long_text = "x" * 2000
        events = [MockObservation("terminal", long_text)]
        output = _serialize_trajectory(events)

        assert "chars truncated" in output

    def test_unknown_event_type_does_not_crash(self):
        """An unrecognized event type is skipped silently without crashing."""
        events = [
            MockMessage("user", "Hello"),
            object(),  # unknown event — no role, action, observation, or error
            MockAction("terminal", "pwd"),
        ]
        output = _serialize_trajectory(events)

        # The known events still produce output
        assert "[USER]" in output
        assert "[ACTION]" in output


# ═══════════════════════════════════════════════════════════════════════
# 1D — _format_numbered_reflections  (agent.py, Fix 7)
#
# Formats an ordered list of reflections into a numbered prompt
# preamble (e.g. "--- Trial 1 ---") for injection into the next
# attempt.
# ═══════════════════════════════════════════════════════════════════════
from reflexion_agent.agent import _format_numbered_reflections


class TestFormatNumberedReflections:
    """Test group 1D: numbered reflection formatter."""

    def test_empty_list_returns_empty_string(self):
        """No reflections → empty string (nothing to inject)."""
        assert _format_numbered_reflections([]) == ""

    def test_single_reflection(self):
        """One reflection → contains 'Trial 1' and the reflection text."""
        output = _format_numbered_reflections(["Try creating the file first."])
        assert "--- Trial 1 ---" in output
        assert "Try creating the file first." in output

    def test_multiple_reflections_in_order(self):
        """Three reflections → Trial 1, 2, 3 all present in order."""
        reflections = [
            "First attempt: missed file creation.",
            "Second attempt: wrong directory.",
            "Third attempt: syntax error in output.",
        ]
        output = _format_numbered_reflections(reflections)

        # All trial headers present
        assert "--- Trial 1 ---" in output
        assert "--- Trial 2 ---" in output
        assert "--- Trial 3 ---" in output

        # Verify ordering: Trial 1 appears before Trial 2, etc.
        pos1 = output.index("--- Trial 1 ---")
        pos2 = output.index("--- Trial 2 ---")
        pos3 = output.index("--- Trial 3 ---")
        assert pos1 < pos2 < pos3

    def test_preamble_text(self):
        """Output starts with the instructional preamble sentence."""
        output = _format_numbered_reflections(["Any reflection."])
        assert output.startswith(
            "The following are reflections from your previous attempts"
        )


# ═══════════════════════════════════════════════════════════════════════
# 1E — generate_reflection  (reflector.py, Fix 6)
#
# The reflector now accepts a plain critique string instead of an
# EvaluationResult object.  We use a mock llm_call to verify:
#   (a) the function runs without error
#   (b) include_raw_trajectory mode prepends trajectory with headers
# ═══════════════════════════════════════════════════════════════════════
from reflexion_agent.reflector import generate_reflection


class TestGenerateReflection:
    """Test group 1E: reflector signature & output modes."""

    def test_accepts_critique_string(self):
        """Passes a plain critique string — no EvaluationResult needed (Fix 6)."""
        # The mock llm_call ignores prompts and returns a fixed string.
        mock_llm = lambda system, user: "Try creating the file first."

        result = generate_reflection(
            task="Create hello.py",
            trajectory="[USER] Create hello.py\n[Turn 1] [ACTION] terminal\n  Arguments: ls",
            critique="The agent missed the file creation step",
            llm_call=mock_llm,
        )

        assert result == "Try creating the file first."

    def test_include_raw_trajectory(self):
        """With include_raw_trajectory=True, output contains both trajectory and reflection headers."""
        mock_llm = lambda system, user: "Use the file_editor tool next time."
        trajectory = "[USER] Create hello.py\n[Turn 1] [ACTION] terminal"

        result = generate_reflection(
            task="Create hello.py",
            trajectory=trajectory,
            critique="File was never created",
            llm_call=mock_llm,
            include_raw_trajectory=True,
        )

        assert "=== PREVIOUS ATTEMPT" in result
        assert "=== REFLECTION" in result
        # The raw trajectory text should appear before the reflection header
        assert result.index("=== PREVIOUS ATTEMPT") < result.index("=== REFLECTION")
        # The original trajectory content is embedded
        assert "[Turn 1] [ACTION] terminal" in result
        # The reflection text is also present
        assert "Use the file_editor tool next time." in result


# ╔═══════════════════════════════════════════════════════════════════════╗
# ║                                                                       ║
# ║  LAYER 2 — Integration Tests with Mock LLM                           ║
# ║                                                                       ║
# ║  These tests exercise the decision logic of the reflexion loop by     ║
# ║  calling the real evaluator, reflector, and formatter functions in    ║
# ║  sequence — but with mock LLM responses instead of real API calls.   ║
# ║                                                                       ║
# ║  No Docker, no network, no API keys.  Each test simulates a          ║
# ║  scenario the loop would encounter and verifies the components       ║
# ║  produce the correct signal for the next decision.                   ║
# ║                                                                       ║
# ╚═══════════════════════════════════════════════════════════════════════╝

from reflexion_agent.evaluator import evaluate_trajectory


# ── Shared helpers for Layer 2 ────────────────────────────────────────
# These create mock LLM callables that return canned responses.
# Each mock also logs what it received so you can see the data flow.

def _make_evaluator_mock(response_text: str):
    """Return a mock llm_call that always returns ``response_text``.

    Also logs the system and user prompts it receives so you can see
    exactly what the evaluator sends to the "judge".
    """
    def mock_llm(system_prompt: str, user_prompt: str) -> str:
        log.info(
            "[mock evaluator LLM] Received call.\n"
            "  system_prompt length : %d chars\n"
            "  user_prompt length   : %d chars\n"
            "  user_prompt preview  : %.200s...",
            len(system_prompt), len(user_prompt), user_prompt,
        )
        log.info(
            "[mock evaluator LLM] Returning canned response:\n%s", response_text,
        )
        return response_text
    return mock_llm


def _make_reflector_mock(reflection_text: str):
    """Return a mock llm_call for the reflector that captures its inputs.

    Stores the (system_prompt, user_prompt) it receives in a list so
    the test can inspect them after the call.
    """
    captured_calls: list[tuple[str, str]] = []

    def mock_llm(system_prompt: str, user_prompt: str) -> str:
        log.info(
            "[mock reflector LLM] Received call.\n"
            "  system_prompt length : %d chars\n"
            "  user_prompt length   : %d chars\n"
            "  user_prompt preview  : %.300s...",
            len(system_prompt), len(user_prompt), user_prompt,
        )
        captured_calls.append((system_prompt, user_prompt))
        log.info(
            "[mock reflector LLM] Returning canned reflection:\n  %s",
            reflection_text,
        )
        return reflection_text

    # Attach the capture list as an attribute so the test can read it.
    mock_llm.captured_calls = captured_calls
    return mock_llm


# ═══════════════════════════════════════════════════════════════════════
# 2A — Score gate stops the loop early  (Fix 1)
#
# When the evaluator returns success=False but score >= threshold,
# the reflexion loop should EXIT (the "score escape hatch").
# We simulate this by calling evaluate_trajectory with a mock that
# returns SCORE: 0.80, then checking whether the gate would fire.
# ═══════════════════════════════════════════════════════════════════════


class TestScoreGateStopsLoop:
    """Test group 2A: high score causes early exit despite success=False."""

    THRESHOLD = 0.75  # default from _parse_score_threshold()

    def test_high_score_triggers_exit(self):
        """score=0.80 >= threshold=0.75 → loop should exit early."""
        log.info("=" * 60)
        log.info("[2A] BEGIN: testing score gate with score=0.80, threshold=%.2f", self.THRESHOLD)

        # Step 1: Build a mock evaluator that returns a high score but success=False
        mock_response = (
            "SUCCESS: false\n"
            "SCORE: 0.80\n"
            "FAILING_STEP: none\n"
            "SUMMARY: Almost there"
        )
        mock_llm = _make_evaluator_mock(mock_response)
        log.info("[2A] Mock evaluator will return: success=False, score=0.80")

        # Step 2: Call evaluate_trajectory — this runs the full evaluator
        # pipeline (format prompt → call LLM → parse response)
        task = "Write hello.py"
        trajectory = "[USER] Write hello.py\n[Turn 1] [ACTION] terminal\n  Arguments: echo 'print(\"hello\")' > hello.py"
        log.info("[2A] Calling evaluate_trajectory(task='%s', trajectory=%d chars)", task, len(trajectory))

        result = evaluate_trajectory(task=task, trajectory=trajectory, llm_call=mock_llm)

        log.info(
            "[2A] Got EvaluationResult: success=%s, score=%.2f, failing_step=%r, summary='%s'",
            result.success, result.score, result.failing_step, result.summary,
        )

        # Step 3: Verify the parsed fields
        assert result.success is False, "Judge said success=False, parser should preserve that"
        assert result.score == pytest.approx(0.80), "Score should be exactly 0.80"

        # Step 4: Simulate the gate check from _run_with_reflexion
        score_above_threshold = result.score >= self.THRESHOLD
        log.info(
            "[2A] Gate check: score %.2f >= threshold %.2f → %s",
            result.score, self.THRESHOLD, score_above_threshold,
        )
        assert score_above_threshold is True, (
            f"Score {result.score} should be >= threshold {self.THRESHOLD} — loop should EXIT"
        )
        log.info("[2A] PASS — the score gate would stop the loop ✓")


# ═══════════════════════════════════════════════════════════════════════
# 2B — Low score does NOT stop the loop  (Fix 1, negative case)
#
# When the score is below the threshold AND success=False, the loop
# must continue to the reflection phase.
# ═══════════════════════════════════════════════════════════════════════


class TestLowScoreContinuesLoop:
    """Test group 2B: low score means the loop keeps retrying."""

    THRESHOLD = 0.75

    def test_low_score_does_not_exit(self):
        """score=0.40 < threshold=0.75 → loop should continue to reflection."""
        log.info("=" * 60)
        log.info("[2B] BEGIN: testing low score path with score=0.40, threshold=%.2f", self.THRESHOLD)

        mock_response = (
            "SUCCESS: false\n"
            "SCORE: 0.40\n"
            "FAILING_STEP: Step 2 — file was empty\n"
            "SUMMARY: The file was created but contained no code."
        )
        mock_llm = _make_evaluator_mock(mock_response)

        task = "Write hello.py that prints Hello World"
        trajectory = "[USER] Write hello.py\n[Turn 1] [ACTION] terminal\n  Arguments: touch hello.py"
        log.info("[2B] Calling evaluate_trajectory(task='%s')", task)

        result = evaluate_trajectory(task=task, trajectory=trajectory, llm_call=mock_llm)

        log.info(
            "[2B] Got EvaluationResult: success=%s, score=%.2f, failing_step=%r, summary='%s'",
            result.success, result.score, result.failing_step, result.summary,
        )

        assert result.success is False
        assert result.score == pytest.approx(0.40)

        # Gate check — should NOT fire
        score_above_threshold = result.score >= self.THRESHOLD
        log.info(
            "[2B] Gate check: score %.2f >= threshold %.2f → %s",
            result.score, self.THRESHOLD, score_above_threshold,
        )
        assert score_above_threshold is False, (
            f"Score {result.score} is below threshold {self.THRESHOLD} — loop must CONTINUE"
        )

        # In the real loop, the next step would be reflection generation.
        log.info("[2B] PASS — the loop would continue to the reflection phase ✓")


# ═══════════════════════════════════════════════════════════════════════
# 2C — Parse failure does NOT produce score=0.0  (Fix 2, integration)
#
# When the judge returns complete garbage (no labeled fields at all),
# the parser must default to score=0.5 (neutral), NOT 0.0.
# Before the fix, score=0.0 made every garbled response look like a
# total failure, which always triggered a retry.
# ═══════════════════════════════════════════════════════════════════════


class TestParseFailureNeutralScore:
    """Test group 2C: garbled judge output → neutral score, not zero."""

    def test_garbage_response_gives_neutral_score(self):
        """Garbage LLM output → score=0.5 via evaluate_trajectory (full pipeline)."""
        log.info("=" * 60)
        log.info("[2C] BEGIN: testing garbled judge response through full pipeline")

        garbage_text = "This is garbage output with no fields"
        mock_llm = _make_evaluator_mock(garbage_text)
        log.info("[2C] Mock evaluator will return raw garbage: '%s'", garbage_text)

        task = "Create a React component"
        trajectory = "[USER] Create a React component\n[Turn 1] [ACTION] file_editor"
        log.info("[2C] Calling evaluate_trajectory(task='%s')", task)

        result = evaluate_trajectory(task=task, trajectory=trajectory, llm_call=mock_llm)

        log.info(
            "[2C] Got EvaluationResult: success=%s, score=%.2f, failing_step=%r, summary='%s'",
            result.success, result.score, result.failing_step, result.summary,
        )

        # The critical assertion from Fix 2: neutral default, not zero.
        assert result.score == pytest.approx(0.5), (
            f"Garbled response should produce score=0.5 (neutral), got {result.score}. "
            "If this is 0.0, Fix 2 (neutral default) has regressed!"
        )
        assert result.success is False, "Conservative default for missing SUCCESS is False"
        assert result.failing_step is None, "No FAILING_STEP field in garbage → None"

        log.info(
            "[2C] PASS — garbled response produced score=%.1f (neutral), not 0.0 ✓",
            result.score,
        )


# ═══════════════════════════════════════════════════════════════════════
# 2D — Reflector receives critique string, NOT EvaluationResult (Fix 6)
#
# The reflector's prompt should contain "CRITIQUE:" followed by the
# evaluator's summary sentence.  It must NOT contain the raw score
# or binary flag — those are gating decisions, not reflection inputs.
#
# We use a capturing mock to inspect the exact prompt the reflector
# passes to its LLM call.
# ═══════════════════════════════════════════════════════════════════════


class TestReflectorReceivesCritique:
    """Test group 2D: reflector gets critique string, not raw EvaluationResult."""

    def test_prompt_contains_critique_not_score(self):
        """generate_reflection prompt has CRITIQUE: <summary> and no score/success fields."""
        log.info("=" * 60)
        log.info("[2D] BEGIN: verifying reflector prompt contents (Fix 6)")

        # Step 1: Get an EvaluationResult from the evaluator (using mock)
        eval_mock_response = (
            "SUCCESS: false\n"
            "SCORE: 0.45\n"
            "FAILING_STEP: Step 3 — no output file\n"
            "SUMMARY: The agent ran commands but never created the requested file."
        )
        eval_mock = _make_evaluator_mock(eval_mock_response)

        task = "Write a Python script that prints Hello"
        trajectory = "[USER] Write a Python script\n[Turn 1] [ACTION] terminal\n  Arguments: ls"
        log.info("[2D] Step 1 — getting EvaluationResult from evaluate_trajectory")

        evaluation = evaluate_trajectory(task=task, trajectory=trajectory, llm_call=eval_mock)
        log.info(
            "[2D] Evaluator returned: success=%s, score=%.2f, summary='%s'",
            evaluation.success, evaluation.score, evaluation.summary,
        )

        # Step 2: Call generate_reflection, passing evaluation.summary as the critique.
        # The capturing mock records what prompts the reflector sends.
        reflector_mock = _make_reflector_mock("Next time, create the file before running it.")
        log.info("[2D] Step 2 — calling generate_reflection with critique='%s'", evaluation.summary)

        reflection = generate_reflection(
            task=task,
            trajectory=trajectory,
            critique=evaluation.summary,
            llm_call=reflector_mock,
        )
        log.info("[2D] Reflection returned: '%s'", reflection)

        # Step 3: Inspect the captured user prompt
        assert len(reflector_mock.captured_calls) == 1, "Reflector should have been called exactly once"
        _, user_prompt = reflector_mock.captured_calls[0]

        log.info("[2D] Step 3 — inspecting captured user prompt (%d chars):", len(user_prompt))
        log.info("[2D] --- BEGIN user_prompt ---\n%s", user_prompt)
        log.info("[2D] --- END user_prompt ---")

        # Positive check: the prompt must contain the CRITIQUE header and the summary text
        assert "CRITIQUE:" in user_prompt, "Reflector prompt must include the CRITIQUE: header"
        assert evaluation.summary in user_prompt, (
            f"Reflector prompt must include the evaluator's summary: '{evaluation.summary}'"
        )
        log.info("[2D] ✓ user_prompt contains 'CRITIQUE:' and the summary text")

        # Negative checks: the prompt must NOT contain raw numeric/boolean evaluation
        # fields.  The reflector should reason about *what went wrong* (the critique
        # sentence), not about score numbers or boolean flags.
        #
        # We use targeted regexes that look for patterns like "score: 0.45" or
        # "success: false" — if these appear, the raw EvaluationResult was
        # leaked into the prompt (violating Fix 6).
        import re
        has_score_field = re.search(r"\bscore\s*:\s*[0-9]", user_prompt, re.IGNORECASE)
        has_success_field = re.search(r"\bsuccess\s*:\s*(true|false)", user_prompt, re.IGNORECASE)

        log.info("[2D] Checking for leaked evaluation fields:")
        log.info("[2D]   'score: <number>' pattern found? %s", bool(has_score_field))
        log.info("[2D]   'success: true/false' pattern found? %s", bool(has_success_field))

        assert not has_score_field, (
            "Reflector prompt must NOT contain 'score: <number>' — "
            "the reflector should not see raw scores (Fix 6)"
        )
        assert not has_success_field, (
            "Reflector prompt must NOT contain 'success: true/false' — "
            "the reflector should not see the binary flag (Fix 6)"
        )
        log.info("[2D] PASS — reflector received only the critique string, no raw eval fields ✓")


# ═══════════════════════════════════════════════════════════════════════
# 2E — Numbered reflections build up correctly  (Fix 7, integration)
#
# Simulates 3 failed attempts in a loop.  Each iteration:
#   1. Generate a mock reflection (via generate_reflection)
#   2. Append it to session_reflections
#   3. Format with _format_numbered_reflections
#   4. Verify the trial headers accumulate correctly
#
# This mirrors what _run_with_reflexion does but without the SDK.
# ═══════════════════════════════════════════════════════════════════════


class TestNumberedReflectionsBuildUp:
    """Test group 2E: reflections accumulate as numbered trials across attempts."""

    def test_three_attempt_accumulation(self):
        """Simulate 3 failed attempts; reflections build up as Trial 1, 2, 3."""
        log.info("=" * 60)
        log.info("[2E] BEGIN: simulating 3-attempt reflexion loop with reflection accumulation")

        task = "Create a Python web server"
        trajectory = "[USER] Create a web server\n[Turn 1] [ACTION] terminal\n  Arguments: python -m http.server"

        # The reflections each mock "attempt" will produce
        per_attempt_reflections = [
            "Attempt 1 failed because the server was started but no file was created.",
            "Attempt 2 failed because the file existed but had a syntax error.",
            "Attempt 3 failed because the port was already in use.",
        ]

        # In the real loop, this list persists across attempts
        session_reflections: list[str] = []

        for attempt_num in range(1, 4):
            log.info("-" * 40)
            log.info("[2E] === Attempt %d of 3 ===", attempt_num)

            # Step 1: Generate a reflection for this attempt (using mock)
            expected_reflection = per_attempt_reflections[attempt_num - 1]
            reflector_mock = _make_reflector_mock(expected_reflection)

            critique = f"Simulated failure critique for attempt {attempt_num}"
            log.info("[2E] Generating reflection with critique: '%s'", critique)

            reflection = generate_reflection(
                task=task,
                trajectory=trajectory,
                critique=critique,
                llm_call=reflector_mock,
            )
            log.info("[2E] Got reflection (%d chars): '%s'", len(reflection), reflection)

            assert reflection == expected_reflection, (
                f"Attempt {attempt_num}: expected '{expected_reflection}', got '{reflection}'"
            )

            # Step 2: Append to session list (mirrors agent.py line 488)
            session_reflections.append(reflection)
            log.info(
                "[2E] session_reflections now has %d entries: %s",
                len(session_reflections),
                [r[:40] + "..." for r in session_reflections],
            )

            # Step 3: Format the accumulated reflections
            formatted = _format_numbered_reflections(session_reflections)
            log.info(
                "[2E] Formatted reflections (%d chars):\n%s",
                len(formatted), formatted,
            )

            # Step 4: Verify the correct trial headers are present
            for trial_idx in range(1, attempt_num + 1):
                header = f"--- Trial {trial_idx} ---"
                assert header in formatted, (
                    f"After attempt {attempt_num}, expected '{header}' in formatted output"
                )
                log.info("[2E] ✓ Found '%s' in formatted output", header)

            # Verify trial headers that should NOT exist yet
            next_trial_header = f"--- Trial {attempt_num + 1} ---"
            assert next_trial_header not in formatted, (
                f"After attempt {attempt_num}, '{next_trial_header}' should NOT exist yet"
            )
            log.info("[2E] ✓ Confirmed '%s' does NOT exist yet (correct)", next_trial_header)

        # Final verification: after all 3 attempts, check ordering
        log.info("-" * 40)
        log.info("[2E] === Final ordering check ===")
        final_formatted = _format_numbered_reflections(session_reflections)

        pos1 = final_formatted.index("--- Trial 1 ---")
        pos2 = final_formatted.index("--- Trial 2 ---")
        pos3 = final_formatted.index("--- Trial 3 ---")
        log.info(
            "[2E] Trial header positions: Trial1@%d, Trial2@%d, Trial3@%d",
            pos1, pos2, pos3,
        )
        assert pos1 < pos2 < pos3, "Trial headers must appear in ascending order"

        # Verify the preamble is present (this is what the agent sees)
        assert final_formatted.startswith(
            "The following are reflections from your previous attempts"
        ), "Formatted output should start with the instructional preamble"

        # Verify each reflection's content is embedded under the right trial
        for i, expected_text in enumerate(per_attempt_reflections):
            assert expected_text in final_formatted, (
                f"Reflection text for attempt {i+1} should appear in the formatted output"
            )
            log.info("[2E] ✓ Attempt %d reflection text found in final output", i + 1)

        log.info("[2E] PASS — reflections accumulate correctly across 3 attempts ✓")
