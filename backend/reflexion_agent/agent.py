import argparse
import json
import os
import platform
import socket
import dotenv
import logging
import uuid

from pathlib import Path
from typing import Callable
from pydantic import SecretStr

from openhands.sdk.context.skills import load_project_skills
from openhands.sdk import AgentContext, LLM, Agent, Tool, Conversation, Message, TextContent
from openhands.sdk.conversation.exceptions import ConversationRunError
from openhands.sdk.event.conversation_error import ConversationErrorEvent
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.task_tracker import TaskTrackerTool
from openhands.tools.terminal import TerminalTool
from openhands.sdk.workspace import LocalWorkspace

from reflexion_agent import evaluate_trajectory, generate_reflection, ReflexionMemory
from config import BASE_URL, API_KEY, AGENT_MODEL

dotenv.load_dotenv()


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")


# Reflexion defaults from .env; per-request override via runtime(use_reflexion=...)
ENABLE_REFLEXION = _env_bool("ENABLE_REFLEXION", "false")
MAX_REFLEXION_ATTEMPTS = int(os.getenv("MAX_REFLEXION_ATTEMPTS", "3") or "3")
MAX_ITERATIONS_PER_TRIAL = int(os.getenv("REFLEXION_MAX_ITERATIONS_PER_TRIAL", "30") or "30")

# Score threshold: if the judge returns a numeric score at or above this value,
# the loop exits early even when evaluation.success is False.  This prevents
# high-quality partial results (e.g. score=0.85) from being needlessly retried.
# Tune via REFLEXION_SCORE_THRESHOLD in .env; valid range is 0.0–1.0.
def _parse_score_threshold() -> float:
    raw = os.getenv("REFLEXION_SCORE_THRESHOLD", "0.75")
    try:
        value = float(raw)
    except ValueError:
        logger.warning(
            "REFLEXION_SCORE_THRESHOLD='%s' is not a valid float; falling back to 0.75",
            raw,
        )
        return 0.75
    if not (0.0 <= value <= 1.0):
        logger.warning(
            "REFLEXION_SCORE_THRESHOLD=%.4f is outside [0.0, 1.0]; clamping to valid range",
            value,
        )
        return max(0.0, min(1.0, value))
    return value

logger = logging.getLogger(__name__)

# Resolved once at import time so the value is available module-wide.
REFLEXION_SCORE_THRESHOLD = _parse_score_threshold()

base_url = BASE_URL
api_key = API_KEY
model = AGENT_MODEL


def _detect_platform():
    m = platform.machine().lower()
    return "linux/arm64" if "arm" in m or "aarch64" in m else "linux/amd64"


def _find_port(start=8010):
    port = start
    while True:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("localhost", port)) != 0:
                return port
        port += 1
        

def _make_llm_call(llm_client):
    """Create a simple callable that wraps the OpenHands LLM client.

    The Reflexion modules expect a function with signature:
        (system_prompt: str, user_prompt: str) -> str

    LLM.completion() in v1.15 takes list[Message] (not raw dicts) and
    returns LLMResponse. This adapter handles both conversions so the
    Reflexion modules stay decoupled from the OpenHands SDK internals.
    """
    def call(system_prompt: str, user_prompt: str) -> str:
        messages = [
            Message(role="system", content=[TextContent(text=system_prompt)]),
            Message(role="user", content=[TextContent(text=user_prompt)]),
        ]
        response = llm_client.completion(messages)
        # response.message.content is a list of TextContent / ThinkingBlock items;
        # join all parts that carry a text field.
        return " ".join(
            c.text for c in response.message.content if hasattr(c, "text")
        )
    return call


def _create_agent(llm, agent_context):
    """Build a fresh Agent with the standard tool set.

    Called once for the non-reflexion path and once *per attempt* inside the
    reflexion loop so that each attempt starts with a clean Agent (no
    residual internal state from a prior run).
    """
    return Agent(
        llm=llm,
        tools=[
            Tool(name="terminal"),
            Tool(name="file_editor"),
            Tool(name="task_tracker"),
        ],
        agent_context=agent_context,
    )


def runtime(
    repo_dir: str,
    instruction: str,
    mount_dir: str = None,
    event_callback: Callable | None = None,
    use_reflexion: bool | None = None,
):
    if mount_dir:
        abs_mount = str(Path(mount_dir).resolve())
        volumes = [f"{abs_mount}:/workspace:rw"]
    else:
        volumes = []

    callbacks = [event_callback] if event_callback else []

    llm = LLM(model=model, api_key=SecretStr(api_key), base_url=base_url, service_id="agent")
    skills = load_project_skills(work_dir=repo_dir)
    logger.info(
        "project_skills_count=%d work_dir=%s",
        len(skills),
        repo_dir or "(empty)",
    )
    agent_context = AgentContext(skills=skills)
    use_rx = ENABLE_REFLEXION if use_reflexion is None else use_reflexion
    logger.info(
        "model=%s, base_url=%s, mounted_dir=%s, use_reflexion=%s",
        model,
        base_url,
        mount_dir,
        use_rx,
    )
    working_dir = abs_mount if mount_dir else repo_dir or "."
    with LocalWorkspace(working_dir=working_dir) as workspace:
        if use_rx:
            _run_with_reflexion(llm, agent_context, instruction, workspace, callbacks=callbacks)
        else:
            agent = _create_agent(llm, agent_context)
            _run_without_reflexion(agent, instruction, workspace, callbacks=callbacks)


def _extract_trajectory_text(obj) -> str:
    """Extract plain text from whatever the SDK puts in a content field.

    Handles: str, a single TextContent-like object (.text), a list of them,
    and arbitrary objects (fallback to empty string rather than crashing).
    This is a local mirror of server.py's _extract_text so agent.py has no
    import dependency on server.py.
    """
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    if hasattr(obj, "text") and isinstance(getattr(obj, "text"), str):
        return obj.text
    if isinstance(obj, (list, tuple)):
        parts = []
        for item in obj:
            if hasattr(item, "text") and isinstance(getattr(item, "text"), str):
                parts.append(item.text)
            elif isinstance(item, str):
                parts.append(item)
        return " ".join(parts)
    return ""


def _serialize_trajectory(events) -> str:
    """Convert OpenHands event objects into a clean, labeled text transcript.

    Replaces the raw Python repr dump — str(list(events)) — with a
    human-readable log that the LLM judge can evaluate reliably.

    Design principles
    -----------------
    - Pure function: events in → string out.  Both the evaluator and the
      reflector receive this same string; neither module needs to change.
    - Defensive: every attribute access uses getattr so an unexpected SDK
      event type never crashes the loop — it just increments the 'other'
      counter and is skipped silently.
    - Dual-attribute checks: the SDK has evolved (e.g. 'action' → 'tool_call',
      'result' → 'observation'), so we check both names for each event type.

    Event type detection (duck typing, no SDK class imports needed)
    ---------------------------------------------------------------
    MessageEvent   → has a non-None 'role' attribute
    ActionEvent    → has 'tool_call' or 'action' (older SDK) attribute
    ObservationEvent → has 'observation' or 'result' (older SDK) attribute
    Error events   → has 'error' or 'message' attribute
    """
    lines = []
    turn = 0
    counts = {"message": 0, "action": 0, "observation": 0, "error": 0, "other": 0}

    for event in events:

        # ── MessageEvent ──────────────────────────────────────────────
        role = getattr(event, "role", None)
        if role is not None:
            text = _extract_trajectory_text(getattr(event, "extended_content", None))
            if not text:
                text = getattr(event, "reasoning_content", None) or ""
            if not text:
                text = _extract_trajectory_text(getattr(event, "content", None))
            if text:
                lines.append(f"[{str(role).upper()}] {text.strip()}")
            counts["message"] += 1
            continue

        # ── ActionEvent (tool call) ───────────────────────────────────
        tool_call = getattr(event, "tool_call", None)
        action_attr = getattr(event, "action", None)  # older SDK fallback

        if tool_call is not None or action_attr is not None:
            turn += 1
            tool_name = (
                getattr(event, "tool_name", None)
                or getattr(event, "tool", None)
                or "unknown"
            )
            lines.append(f"[Turn {turn}] [ACTION] {tool_name}")

            # Parse structured args from the tool_call (current SDK)
            if tool_call is not None:
                fn = getattr(tool_call, "function", None)
                args_str = (getattr(fn, "arguments", None) or "") if fn else ""
                try:
                    args_dict = json.loads(args_str) if args_str else {}
                except (json.JSONDecodeError, TypeError):
                    args_dict = {}
                if args_dict:
                    args_display = ", ".join(
                        f"{k}={repr(str(v))[:80]}" for k, v in args_dict.items()
                    )
                    lines.append(f"  Arguments: {args_display}")
                elif args_str:
                    lines.append(f"  Arguments: {args_str[:300]}")
            else:
                # Older SDK: action is an object like BashAction(command='ls -la')
                lines.append(f"  Arguments: {str(action_attr)[:300]}")

            # Capture any reasoning the agent attached to this action
            thought = _extract_trajectory_text(getattr(event, "thought", None))
            if not thought:
                thought = getattr(event, "reasoning_content", None) or ""
            if thought:
                lines.append(f"  [Agent reasoning] {thought.strip()[:400]}")

            counts["action"] += 1
            continue

        # ── ObservationEvent (tool result) ────────────────────────────
        observation = getattr(event, "observation", None)
        result_attr = getattr(event, "result", None)  # older SDK fallback

        if observation is not None or result_attr is not None:
            tool_name = getattr(event, "tool_name", None) or ""

            if observation is not None:
                raw = (
                    getattr(observation, "content", None)
                    or getattr(observation, "text", None)
                )
                content = _extract_trajectory_text(raw) or str(observation)
            else:
                content = _extract_trajectory_text(result_attr) or str(result_attr)

            content = content.strip()
            # Truncate long outputs (e.g. full file contents) to stay readable
            if len(content) > 800:
                content = content[:800] + f"\n  ... [{len(content) - 800} chars truncated]"

            prefix = f"[OBSERVATION] {tool_name}: " if tool_name else "[OBSERVATION] "
            lines.append(f"{prefix}{content}")
            counts["observation"] += 1
            continue

        # ── Error events ──────────────────────────────────────────────
        error_msg = getattr(event, "error", None) or getattr(event, "message", None)
        if error_msg:
            lines.append(f"[ERROR] {str(error_msg)[:400]}")
            counts["error"] += 1
            continue

        counts["other"] += 1

    total = sum(counts.values())
    logger.info(
        "[trajectory] Serialized %d events — message=%d action=%d observation=%d error=%d other=%d",
        total,
        counts["message"],
        counts["action"],
        counts["observation"],
        counts["error"],
        counts["other"],
    )

    if not lines:
        logger.warning(
            "[trajectory] No serializable events found after processing %d raw events — "
            "returning placeholder",
            total,
        )
        return "[trajectory: no events captured]"

    return "\n".join(lines)


def _run_without_reflexion(agent, instruction, workspace, callbacks=None):
    """Single attempt, optionally streaming events via callbacks."""
    conversation = Conversation(agent=agent, workspace=workspace, callbacks=callbacks or [])
    conversation.send_message(instruction)
    conversation.run()

    conversation.send_message("According to the history of this task, summarize the preferences of the user, or key memories, and save them in AGENT.md and MEMORY.md.")
    conversation.run()


def _format_numbered_reflections(reflections: list[str]) -> str:
    """Format in-session reflections as numbered trial blocks for prompt injection.

    This is the minimal reflexion pattern from the paper: ordered, per-session
    reflections prepended to the next attempt's prompt.  Each reflection is
    labeled with its trial number so the agent can see how its strategy evolved.
    """
    if not reflections:
        return ""
    numbered = "\n\n".join(
        f"--- Trial {i + 1} ---\n{r}" for i, r in enumerate(reflections)
    )
    return (
        "The following are reflections from your previous attempts in this session. "
        "Use these lessons to avoid repeating the same mistakes:\n\n"
        + numbered
    )


def _run_with_reflexion(llm, agent_context, instruction, workspace, callbacks=None):
    """Reflexion loop: attempt -> evaluate -> reflect -> retry with memory.

    A **fresh** Agent is created for every attempt so that no internal state
    from a prior run (cached tool results, conversation memory, mutable SDK
    fields) can leak into the next attempt and pollute its behaviour.

    Reflections are tracked both:
    - In-session via an ordered list[str] (injected as numbered trials into the
      next attempt prompt — this is the core reflexion mechanism).
    - Persistently via ReflexionMemory (for cross-session retrieval; the memory
      path is read from REFLEXION_MEMORY_PATH or falls back to the package default).
    """
    memory_path = os.getenv("REFLEXION_MEMORY_PATH", "").strip() or None
    if memory_path:
        logger.info("[reflexion] Using REFLEXION_MEMORY_PATH=%s", memory_path)
    else:
        logger.info("[reflexion] REFLEXION_MEMORY_PATH not set — using package default")
    memory = ReflexionMemory(memory_path) if memory_path else ReflexionMemory()

    llm_call = _make_llm_call(llm)
    task_id = str(uuid.uuid4())[:8]

    # In-session ordered reflections — the primary prompt-injection mechanism.
    session_reflections: list[str] = []

    # Also pull any *cross-session* reflections from persistent memory.
    cross_session_context = memory.format_for_prompt(instruction)
    if cross_session_context:
        logger.info(
            "[reflexion] Found cross-session reflections from memory (task=%s)",
            task_id,
        )

    for attempt in range(1, MAX_REFLEXION_ATTEMPTS + 1):
        logger.info("Reflexion attempt %d/%d for task %s", attempt, MAX_REFLEXION_ATTEMPTS, task_id)

        # Fresh agent per attempt — prevents hidden state from leaking across retries.
        agent = _create_agent(llm, agent_context)
        logger.info(
            "[reflexion] Created fresh Agent for attempt %d (task=%s)",
            attempt, task_id,
        )

        # Build the full prompt: numbered in-session reflections (primary)
        # + optional cross-session reflections + original instruction.
        preamble_parts = []
        session_block = _format_numbered_reflections(session_reflections)
        if session_block:
            preamble_parts.append(session_block)
        if cross_session_context:
            preamble_parts.append(cross_session_context)

        if preamble_parts:
            full_instruction = (
                "\n\n---\n\n".join(preamble_parts)
                + "\n\n---\n\nNow, perform the following task:\n"
                + instruction
            )
            logger.debug(
                "[reflexion] Prompt preamble: %d in-session reflections, cross-session=%s (task=%s)",
                len(session_reflections), bool(cross_session_context), task_id,
            )
        else:
            full_instruction = instruction

        # Per-step callback: logs every SDK event with a running step counter.
        step_counter = {"n": 0}
        def _step_logger(event, _attempt=attempt, _task_id=task_id):
            step_counter["n"] += 1
            event_type = type(event).__name__
            summary = ""
            if hasattr(event, "tool_call") and event.tool_call is not None:
                tool = getattr(event, "tool_name", None) or "unknown"
                summary = f" tool={tool}"
            elif hasattr(event, "observation"):
                summary = f" observation_len={len(str(getattr(event, 'observation', '')))}"
            elif hasattr(event, "error"):
                summary = f" error={getattr(event, 'error', '')[:120]}"
            elif hasattr(event, "code") and hasattr(event, "detail"):
                summary = f" code={event.code} detail={str(event.detail)[:120]}"
            logger.info(
                "[step %d/%d] trial=%d event=%s%s (task=%s)",
                step_counter["n"], MAX_ITERATIONS_PER_TRIAL,
                _attempt, event_type, summary, _task_id,
            )

        all_callbacks = list(callbacks or []) + [_step_logger]

        conversation = Conversation(
            agent=agent,
            workspace=workspace,
            callbacks=all_callbacks,
            max_iteration_per_run=MAX_ITERATIONS_PER_TRIAL,
        )
        logger.info(
            "[reflexion] Trial %d: max_iteration_per_run=%d (task=%s)",
            attempt, MAX_ITERATIONS_PER_TRIAL, task_id,
        )
        conversation.send_message(full_instruction)
        conversation.run()
        logger.info(
            "[reflexion] Trial %d finished: %d steps used of %d max (task=%s)",
            attempt, step_counter["n"], MAX_ITERATIONS_PER_TRIAL, task_id,
        )

        # Capture the trajectory as a clean, labeled text transcript.
        trajectory = _serialize_trajectory(conversation.state.events)

        # Evaluate the trajectory
        evaluation = evaluate_trajectory(
            task=instruction,
            trajectory=trajectory,
            llm_call=llm_call,
        )
        logger.info(
            "Attempt %d result: success=%s score=%.2f threshold=%.2f task=%s",
            attempt, evaluation.success, evaluation.score, REFLEXION_SCORE_THRESHOLD, task_id,
        )

        # Dual-signal stop condition:
        # 1. Binary flag — judge explicitly marked the task as successful.
        # 2. Score escape hatch — numeric score meets or exceeds our threshold,
        #    even if the binary flag says False (e.g. score=0.85 but success=False).
        score_above_threshold = evaluation.score >= REFLEXION_SCORE_THRESHOLD
        if evaluation.success:
            logger.info(
                "[reflexion gate] Stopping — judge marked success=True "
                "(attempt=%d score=%.2f task=%s)",
                attempt, evaluation.score, task_id,
            )
            break
        if score_above_threshold:
            logger.info(
                "[reflexion gate] Stopping — score %.2f >= threshold %.2f "
                "despite success=False (attempt=%d task=%s)",
                evaluation.score, REFLEXION_SCORE_THRESHOLD, attempt, task_id,
            )
            break

        # If this was the last attempt, log but still generate and store the
        # reflection (useful for cross-session memory even if we won't retry).
        if attempt == MAX_REFLEXION_ATTEMPTS:
            logger.info("Max attempts reached for task %s", task_id)

        # Generate a verbal reflection on the failure.
        # Only the critique (evaluation.summary) is passed — the reflector does
        # not see the numeric score or binary flag (Fix 6).
        reflection = generate_reflection(
            task=instruction,
            trajectory=trajectory,
            critique=evaluation.summary,
            llm_call=llm_call,
        )
        logger.info(
            "[reflexion] Reflection for attempt %d (%d chars): %.200s",
            attempt, len(reflection), reflection,
        )

        # Track in-session for numbered prompt injection on the next attempt.
        session_reflections.append(reflection)

        # Also persist to cross-session memory for future tasks.
        memory.store(
            task_id=f"{task_id}-attempt-{attempt}",
            task_description=instruction,
            reflection=reflection,
            score=evaluation.score,
        )


def main():
    parser = argparse.ArgumentParser(description="Run OpenHands agent in Docker")
    parser.add_argument("-i", "--instruction", required=True, help="Task instruction for the agent")
    parser.add_argument("-m", "--mount_dir", default="", help="Paths to mount under workspace")
    args = parser.parse_args()
    runtime(repo_dir=args.mount_dir, instruction=args.instruction, mount_dir=args.mount_dir)


if __name__ == "__main__":
    main()