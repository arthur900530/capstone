"""Shared helpers for translating OpenHands SDK agent events into UI-friendly
shapes.

Three consumers use this module:

1. ``server.py`` — converts events into SSE rows for the live chat trajectory.
2. ``test_case_runner.py`` — captures a compact event list per auto-test run
   for the LLM verifier, and serializes a human-readable transcript for the
   "View trajectory" drawer.
3. ``reflexion_agent/agent.py`` — serializes trajectories for the reflexion
   evaluator / reflector.

The SDK event imports are guarded: when running without the real agent
(REAL_AGENT_ENABLED=False) the SDK isn't installed, so ``compact_event``
falls back to a model_dump-based extraction that never raises.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Guarded SDK imports — same pattern as server.py.
# When the SDK isn't present we still want compact_event() to work
# (it'll just produce less type-aware output).
try:
    from openhands.sdk.event import (  # type: ignore
        ActionEvent,
        ObservationEvent,
        MessageEvent,
        AgentErrorEvent,
    )
    from openhands.sdk.event.conversation_error import (  # type: ignore
        ConversationErrorEvent,
    )

    _SDK_AVAILABLE = True
except ImportError:
    ActionEvent = None  # type: ignore
    ObservationEvent = None  # type: ignore
    MessageEvent = None  # type: ignore
    AgentErrorEvent = None  # type: ignore
    ConversationErrorEvent = None  # type: ignore
    _SDK_AVAILABLE = False


# Event class names we always drop from the compact trajectory.
# These are state-machine bookkeeping events, not agent reasoning/actions,
# and they dominate the stream (~50% of rows in a typical run).
_DROPPED_CLASS_NAMES = frozenset(
    {
        "ConversationStateUpdateEvent",
        "SystemPromptEvent",
    }
)


# Hard cap on per-content character length when we serialise into the
# compact trajectory. Keeps the in-memory store and the JSON payload small
# even when a tool dumps a giant blob (e.g. cat'ing a 100KB file).
_CONTENT_CHAR_CAP = 2000


def extract_text(obj: Any) -> str:
    """Safely flatten any of the SDK's content shapes into plain text.

    Handles:
      - ``str``
      - ``TextContent`` (object with a ``.text: str`` attribute)
      - ``Sequence[TextContent]`` (list/tuple of the above)
      - Plain lists/tuples of strings

    Returns an empty string for anything else — this is intentional: we never
    want to fall back to ``repr()`` on an SDK object (it produces noisy,
    Pydantic-flavoured output that confuses both humans and the LLM judge).
    """
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    # Single TextContent-like object
    if hasattr(obj, "text") and isinstance(getattr(obj, "text"), str):
        return obj.text
    # Sequence of TextContent-like objects (Sequence[TextContent])
    if isinstance(obj, (list, tuple)):
        parts: list[str] = []
        for item in obj:
            if hasattr(item, "text") and isinstance(getattr(item, "text"), str):
                parts.append(item.text)
            elif isinstance(item, str):
                parts.append(item)
        if parts:
            return " ".join(parts)
    return ""


def parse_tool_args(tc: Any) -> tuple[str, dict]:
    """Extract ``(args_string, args_dict)`` from a tool-call object.

    OpenHands' ``MessageToolCall`` (``openhands.sdk.llm.message``) is flat:
    ``tc.name`` and ``tc.arguments`` (the latter is a JSON-encoded string).
    The OpenAI Chat Completions API uses a nested shape — ``tc.function.name``
    and ``tc.function.arguments`` — and ``MessageToolCall.to_chat_dict()``
    serialises *to* that nested shape, which is what made the older flat
    code path silently regress to empty args. Try the flat form first and
    fall back to the nested form so both representations work.

    A malformed/empty args payload yields ``("", {})`` rather than raising —
    this helper sits in the agent's hot loop and must never throw.
    """
    args_str = getattr(tc, "arguments", None)
    if args_str is None:
        fn = getattr(tc, "function", None)
        args_str = getattr(fn, "arguments", None) if fn is not None else None
    args_str = args_str or ""
    try:
        args_dict = json.loads(args_str) if args_str else {}
    except (json.JSONDecodeError, TypeError):
        args_dict = {}
    return args_str, args_dict


def _safe_dump(event: Any) -> dict[str, Any]:
    """Best-effort ``model_dump`` that never raises."""
    if hasattr(event, "model_dump"):
        try:
            return event.model_dump()  # type: ignore[no-any-return]
        except Exception:  # noqa: BLE001
            return {}
    return {}


def _extract_tool_name(event: Any) -> Optional[str]:
    """Pull a tool name from an event, preferring the attribute over the dump."""
    name = getattr(event, "tool_name", None)
    if name:
        return str(name).strip()
    fallback = _safe_dump(event).get("tool_name")
    return str(fallback).strip() if fallback else None


def _truncate(text: str, cap: int = _CONTENT_CHAR_CAP) -> str:
    """Truncate with a visible marker so the user knows there's more."""
    if len(text) <= cap:
        return text
    return text[:cap].rstrip() + " …[truncated]"


def compact_event(event: Any) -> Optional[dict[str, Any]]:
    """Translate one SDK event into a UI-friendly compact dict.

    Returns ``None`` for events we deliberately drop (state-machine updates,
    system prompts) — callers should skip those instead of appending.

    Output shape (all keys optional except ``event_type``):
        {
            "event_type": "ActionEvent",        # SDK class name
            "tool_name": "bash" | None,         # for tool-call/observation rows
            "content": "summary text…",         # human-readable, truncated
            "args": {...},                      # parsed tool args (ActionEvent only)
            "is_finish": True,                  # marks the agent's final answer
        }

    The dispatcher uses ``isinstance`` when the SDK is importable, and
    falls back to class-name + model_dump heuristics when it isn't (e.g.
    in tests, or when REAL_AGENT_ENABLED is False).
    """
    class_name = type(event).__name__

    # Drop bookkeeping events early. Cheaper than a full model_dump.
    if class_name in _DROPPED_CLASS_NAMES:
        return None

    base: dict[str, Any] = {
        "event_type": class_name,
    }
    tool_name = _extract_tool_name(event)
    if tool_name:
        base["tool_name"] = tool_name

    # ----- type-aware dispatch (preferred) -----
    if _SDK_AVAILABLE:
        if ActionEvent is not None and isinstance(event, ActionEvent):
            return _compact_action_event(event, base)

        if ObservationEvent is not None and isinstance(event, ObservationEvent):
            return _compact_observation_event(event, base)

        if MessageEvent is not None and isinstance(event, MessageEvent):
            return _compact_message_event(event, base)

        if AgentErrorEvent is not None and isinstance(event, AgentErrorEvent):
            error_msg = str(getattr(event, "error", "") or event)
            base["content"] = _truncate(error_msg)
            return base

        if ConversationErrorEvent is not None and isinstance(
            event, ConversationErrorEvent
        ):
            code = getattr(event, "code", None) or "ConversationError"
            detail = getattr(event, "detail", None) or ""
            base["content"] = _truncate(f"{code}: {detail}".strip(": "))
            return base

    # ----- generic fallback (SDK not loaded, or unknown event class) -----
    dumped = _safe_dump(event)
    text = (
        extract_text(dumped.get("extended_content"))
        or extract_text(dumped.get("content"))
        or extract_text(dumped.get("message"))
        or extract_text(dumped.get("thought"))
        or str(dumped.get("reasoning_content") or "")
    )
    if text:
        base["content"] = _truncate(text)
    return base


def _compact_action_event(event: Any, base: dict[str, Any]) -> dict[str, Any]:
    """ActionEvent = either a tool call OR a pure reasoning step."""
    tool_call = getattr(event, "tool_call", None)
    if tool_call is not None:
        tool_name = getattr(event, "tool_name", None) or "unknown"
        _, args_dict = parse_tool_args(tool_call)

        # The "finish" tool is the agent's way of signalling "I'm done";
        # its args carry the final answer text. We surface that as content
        # and mark the row so the UI can highlight it differently if wanted.
        if str(tool_name).lower() in ("finish", "finishtool"):
            finish_text = (
                args_dict.get("message")
                or args_dict.get("outputs")
                or args_dict.get("text")
                or extract_text(getattr(event, "thought", None))
                or ""
            )
            base["tool_name"] = str(tool_name)
            base["content"] = _truncate(str(finish_text))
            base["is_finish"] = True
            return base

        # Build a short inline summary: "command=curl https://..." or
        # "path=/etc/hosts" — whichever arg is most descriptive.
        detail = (
            args_dict.get("command")
            or args_dict.get("query")
            or args_dict.get("path")
            or ""
        )
        summary = f"{tool_name}({_short_arg(detail)})" if detail else f"{tool_name}(…)"
        base["tool_name"] = str(tool_name)
        base["content"] = summary
        if args_dict:
            base["args"] = args_dict
        return base

    # No tool_call → pure reasoning. SDK exposes either ``thought``
    # (Sequence[TextContent]) or ``reasoning_content`` (str).
    thought_text = extract_text(getattr(event, "thought", None))
    if thought_text:
        base["content"] = _truncate(thought_text)
        return base

    reasoning = getattr(event, "reasoning_content", None)
    if isinstance(reasoning, str) and reasoning.strip():
        base["content"] = _truncate(reasoning)
        return base

    return base


def _compact_observation_event(event: Any, base: dict[str, Any]) -> dict[str, Any]:
    """ObservationEvent = the result of the previous tool call."""
    obs = getattr(event, "observation", None)
    if obs is not None:
        raw = getattr(obs, "content", None) or getattr(obs, "text", None)
        text = extract_text(raw)
        if not text:
            # Last-resort: stringify the observation. Some custom observation
            # types implement __str__ usefully (e.g. CmdOutput).
            text = str(obs)
    else:
        text = ""
    base["content"] = _truncate(text)
    return base


def _compact_message_event(event: Any, base: dict[str, Any]) -> dict[str, Any]:
    """MessageEvent = a free-form message from the agent (often the answer)."""
    text = (
        extract_text(getattr(event, "extended_content", None))
        or (getattr(event, "reasoning_content", None) or "")
        or extract_text(getattr(event, "content", None))
        or extract_text(getattr(getattr(event, "message", None), "content", None))
    )
    if text:
        base["content"] = _truncate(text)
    return base


def _short_arg(value: Any, cap: int = 120) -> str:
    """Render a single arg value as a short single-line preview for summaries."""
    if value is None:
        return ""
    text = str(value).replace("\n", " ").strip()
    if len(text) > cap:
        text = text[: cap - 1].rstrip() + "…"
    return text


# ---------------------------------------------------------------------------
# compact_events_to_replay_events — adapter for autotest persistence
# ---------------------------------------------------------------------------
# The autotest runner captures events in the *compact* format
# (``compact_event`` above) but the trajectory drawer + metrics counters
# both consume the SSE-shaped event dicts that ``server.py`` writes for
# chat turns (keys ``type``/``tool``/``detail``/``args``/``text``).
#
# This adapter bridges the two so an autotest run can be mirrored into
# ``task_runs.raw_events`` (see ``routers/employees._persist_autotest_task_run``)
# and replayed by ``trajectory.build_nodes_from_events`` without requiring
# a parallel rendering pipeline.
# ---------------------------------------------------------------------------


def compact_events_to_replay_events(events: list[dict] | None) -> list[dict]:
    """Translate compact_event() dicts into the SSE-shaped events the
    trajectory tree builder + metrics aggregations expect.

    Mapping (compact ``event_type`` -> SSE ``type``):
      - ``ActionEvent`` with ``is_finish``        -> ``answer``
      - ``ActionEvent`` with ``tool_name``        -> ``tool_call``
      - ``ActionEvent`` (reasoning only)          -> ``reasoning``
      - ``ObservationEvent``                      -> ``tool_result``
      - ``MessageEvent``                          -> ``answer``
      - ``AgentErrorEvent`` / ``ConversationErrorEvent`` -> ``error``

    Tool-call rows get a monotonically increasing ``turn`` so the drawer
    can label them, mirroring ``server._map_event_to_sse``. Timestamps
    flow through unchanged from the compact event's ``ts`` field (added
    by ``test_case_runner._callback``).
    """
    out: list[dict] = []
    turn = 0
    for ev in events or []:
        et = ev.get("event_type")
        ts = ev.get("ts")

        if et == "ActionEvent":
            if ev.get("is_finish"):
                text = ev.get("content") or ""
                out.append({"type": "answer", "text": text, "timestamp": ts})
                continue
            tool = ev.get("tool_name")
            if tool:
                turn += 1
                out.append(
                    {
                        "type": "tool_call",
                        "tool": str(tool),
                        "detail": ev.get("content") or f"Calling {tool}",
                        "args": ev.get("args") or {},
                        "turn": turn,
                        "timestamp": ts,
                    }
                )
                continue
            text = ev.get("content") or ""
            if text:
                out.append({"type": "reasoning", "text": text, "timestamp": ts})
            continue

        if et == "ObservationEvent":
            text = ev.get("content") or ""
            row = {"type": "tool_result", "text": text, "timestamp": ts}
            if ev.get("tool_name"):
                row["tool"] = str(ev.get("tool_name"))
            out.append(row)
            continue

        if et == "MessageEvent":
            text = ev.get("content") or ""
            if text:
                out.append({"type": "answer", "text": text, "timestamp": ts})
            continue

        if et in ("AgentErrorEvent", "ConversationErrorEvent"):
            text = ev.get("content") or ""
            out.append({"type": "error", "message": text, "timestamp": ts})
            continue

    return out


# ---------------------------------------------------------------------------
# serialize_trajectory — human-readable transcript from raw SDK events
# ---------------------------------------------------------------------------
# Previously lived in reflexion_agent/agent.py as ``_serialize_trajectory``.
# Moved here so test_case_runner.py and reflexion_agent/agent.py share the
# same serializer — one source of truth for "what did the agent do?"
#
# Uses duck-typing (getattr) instead of isinstance so it never needs the
# SDK imports and never crashes on an unexpected event type.
# ---------------------------------------------------------------------------


def serialize_trajectory(events: Any) -> str:
    """Convert raw OpenHands SDK event objects into a labeled text transcript.

    Output format (one line per meaningful event):

        [ASSISTANT] I'll look up the SEC filing…
        [Turn 1] [ACTION] browser_navigate
          Arguments: url='https://sec.gov/…'
          [Agent reasoning] The user asked about Apple financials…
        [OBSERVATION] browser_navigate: Page loaded successfully…
        [Turn 2] [ACTION] browser_get_content
          Arguments: …
        [OBSERVATION] browser_get_content: <html>…
        [ASSISTANT] Based on the filing, Apple's Q3 revenue was…

    Returns ``"[trajectory: no events captured]"`` if no meaningful events
    are found (e.g. the agent crashed before producing any output).
    """
    lines: list[str] = []
    turn = 0
    counts = {"message": 0, "action": 0, "observation": 0, "error": 0, "other": 0}

    for event in events or []:

        # ── MessageEvent (has a non-None 'role' attribute) ────────────
        role = getattr(event, "role", None)
        if role is not None:
            text = extract_text(getattr(event, "extended_content", None))
            if not text:
                text = getattr(event, "reasoning_content", None) or ""
            if not text:
                text = extract_text(getattr(event, "content", None))
            if text:
                lines.append(f"[{str(role).upper()}] {text.strip()}")
            counts["message"] += 1
            continue

        # ── ActionEvent (tool call) ───────────────────────────────────
        tool_call = getattr(event, "tool_call", None)
        action_attr = getattr(event, "action", None)

        if tool_call is not None or action_attr is not None:
            turn += 1
            tool_name = (
                getattr(event, "tool_name", None)
                or getattr(event, "tool", None)
                or "unknown"
            )
            lines.append(f"[Turn {turn}] [ACTION] {tool_name}")

            if tool_call is not None:
                _, args_dict = parse_tool_args(tool_call)
                if args_dict:
                    args_display = ", ".join(
                        f"{k}={repr(str(v))[:80]}" for k, v in args_dict.items()
                    )
                    lines.append(f"  Arguments: {args_display}")
            else:
                lines.append(f"  Arguments: {str(action_attr)[:300]}")

            thought = extract_text(getattr(event, "thought", None))
            if not thought:
                thought = getattr(event, "reasoning_content", None) or ""
            if thought:
                lines.append(f"  [Agent reasoning] {thought.strip()[:400]}")

            counts["action"] += 1
            continue

        # ── ObservationEvent (tool result) ────────────────────────────
        observation = getattr(event, "observation", None)
        result_attr = getattr(event, "result", None)

        if observation is not None or result_attr is not None:
            tool_name = getattr(event, "tool_name", None) or ""

            if observation is not None:
                raw = (
                    getattr(observation, "content", None)
                    or getattr(observation, "text", None)
                )
                content = extract_text(raw) or str(observation)
            else:
                content = extract_text(result_attr) or str(result_attr)

            content = content.strip()
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
