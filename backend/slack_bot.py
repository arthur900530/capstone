"""Slack integration for digital employees.

Listens for @-mentions of the bot in Slack channels and DMs. Parses the
first word of the message to pick which Employee to invoke (e.g.
``@BNYAgent Walter, summarize the 10-K`` looks up an Employee named
"Walter"), then calls the existing ``POST /api/chat`` SSE endpoint over
loopback and mirrors progress into a single Slack message that gets edited
as the agent works.

Started from FastAPI's ``lifespan`` in ``server.py`` when both
``SLACK_BOT_TOKEN`` and ``SLACK_APP_TOKEN`` are set. Otherwise the bot is
silently disabled and the rest of the backend runs unchanged.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Optional

import httpx
from slack_bolt.async_app import AsyncApp
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler

logger = logging.getLogger(__name__)

# Loopback base for the FastAPI backend. start.sh launches uvicorn on
# 127.0.0.1:8000; override only if running the bot out-of-process.
_BACKEND_BASE = os.getenv("SLACK_BACKEND_BASE", "http://127.0.0.1:8000")

# Map slack_thread_key -> agent session_id, so follow-up mentions in the same
# thread keep conversation context. In-memory only; lost on restart, which is
# fine for a v1 (the agent's own /workspace/MEMORY.md persists across sessions
# anyway via Employee.chatSessionIds).
_THREAD_SESSIONS: dict[str, str] = {}

# Per-thread asyncio.Lock so debounced edits don't race when the agent emits
# events faster than the debounce interval.
_THREAD_LOCKS: dict[str, asyncio.Lock] = {}

# Cache the bot's own Slack user id so we can strip <@U…> prefixes without
# hitting auth.test on every event.
_bot_user_id: Optional[str] = None

# Debounce interval for chat.update edits. Slack's soft guideline is ~1/sec
# per message; we stay under it.
_EDIT_DEBOUNCE_SECS = 1.0

# Slack hard cap on a single message is 40k chars; truncate generously below.
_SLACK_MAX_TEXT = 39000


# ─────────────────────────────────────────────────────────────────────────────
# Parsing helpers
# ─────────────────────────────────────────────────────────────────────────────


def _strip_bot_mention(text: str, bot_user_id: str) -> str:
    """Remove a leading ``<@U…>`` reference to the bot itself."""
    return re.sub(rf"^\s*<@{re.escape(bot_user_id)}>\s*", "", text or "").strip()


def _parse_agent_name(text: str) -> tuple[Optional[str], str]:
    """Return ``(agent_name, remaining_task)``.

    Two parsing modes, tried in order:

    1. **Comma/colon delimited** — if the message contains a ``,`` or ``:``,
       everything before the first one is the candidate name and may contain
       spaces. ``"Big Boss, do X"`` → ``("Big Boss", "do X")``.
    2. **First-word** — fallback when no delimiter is present. The first
       whitespace-separated token is the name; underscores and dashes inside
       it are allowed so users who skip the comma can still hit a multi-word
       employee via ``"Big_Boss do X"`` (the lookup normalizes ``_``/``-`` to
       spaces).

    Returns ``(None, "")`` for empty input, ``(name, "")`` for a single token
    with no task body, ``(None, text)`` when nothing looks like a name.
    """
    stripped = (text or "").strip()
    if not stripped:
        return None, ""

    # Mode 1: explicit `,` or `:` separates name from task — spaces allowed
    # in the name, so multi-word names work.
    delim_match = re.match(
        r"^@?([A-Za-z][A-Za-z0-9 _-]*?)\s*[,:]\s*(.*)$",
        stripped,
        re.DOTALL,
    )
    if delim_match:
        return delim_match.group(1).strip(), delim_match.group(2).strip()

    # Mode 2: first token (no spaces inside) is the name. Underscores and
    # dashes are kept so the lookup can map them back to spaces.
    space_match = re.match(
        r"^@?([A-Za-z][A-Za-z0-9_-]*)\s+(.*)$",
        stripped,
        re.DOTALL,
    )
    if space_match:
        return space_match.group(1).strip(), space_match.group(2).strip()

    if " " not in stripped and "\n" not in stripped:
        return stripped.lstrip("@").rstrip(",:").strip() or None, ""
    return None, stripped


# ─────────────────────────────────────────────────────────────────────────────
# Backend HTTP helpers (loopback to FastAPI)
# ─────────────────────────────────────────────────────────────────────────────


def _normalize_name(name: str) -> str:
    """Lower-case, trim, and treat ``_`` / ``-`` as spaces for matching.

    This lets a Slack user write ``Big_Boss`` or ``big-boss`` and still hit an
    employee literally named ``Big Boss``. Multiple consecutive separators
    collapse to one space so ``Big__Boss`` also matches.
    """
    swapped = re.sub(r"[_\-\s]+", " ", (name or "").strip())
    return swapped.lower()


async def _find_employee_by_name(name: str) -> Optional[dict]:
    """Look up an Employee row by name, case-insensitive and tolerant of
    ``_``/``-`` in place of spaces (see ``_normalize_name``)."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{_BACKEND_BASE}/api/employees")
        resp.raise_for_status()
        rows = resp.json()
    target = _normalize_name(name)
    for row in rows:
        if _normalize_name(row.get("name") or "") == target:
            return row
    return None


def _truncate_for_slack(text: str) -> str:
    if len(text) <= _SLACK_MAX_TEXT:
        return text
    return text[:_SLACK_MAX_TEXT] + "\n\n_(truncated)_"


def _format_progress(event_type: str, event_data: dict) -> str:
    """Convert one SSE event into a one-line Slack progress label."""
    if event_type == "tool_call":
        tool = event_data.get("tool") or "tool"
        detail = (event_data.get("detail") or "").strip()
        return f"🔧 {tool}" + (f": {detail[:140]}" if detail else "")
    if event_type == "tool_result":
        return "📥 got tool result"
    if event_type == "reasoning":
        text = (event_data.get("text") or "").strip().replace("\n", " ")
        return f"💭 {text[:140]}" if text else "💭 reasoning…"
    if event_type == "self_eval":
        score = event_data.get("confidence_score")
        return f"🧪 self-eval (confidence={score})"
    if event_type == "reflection":
        return "♻️ reflecting and retrying"
    if event_type == "status":
        msg = (event_data.get("message") or "").strip()
        return f"… {msg}" if msg else "…"
    if event_type == "file_edit":
        path = event_data.get("path") or ""
        return f"✏️ editing {path}"
    return ""


async def _stream_agent(
    employee_id: str,
    question: str,
    session_id: Optional[str],
    on_progress,  # async callable(label: str)
    on_session,   # async callable(session_id: str)
) -> str:
    """Call ``POST /api/chat`` and consume the SSE stream.

    Returns the final answer text. Raises ``RuntimeError`` on agent error.
    """
    body = {
        "question": question,
        "employee_id": employee_id,
        "session_id": session_id,
        "use_reflexion": False,
    }
    final_parts: list[str] = []
    async with httpx.AsyncClient(timeout=None) as client:
        async with client.stream(
            "POST",
            f"{_BACKEND_BASE}/api/chat",
            json=body,
            headers={"Accept": "text/event-stream"},
        ) as resp:
            resp.raise_for_status()
            current_event: Optional[str] = None
            async for line in resp.aiter_lines():
                if not line:
                    current_event = None
                    continue
                if line.startswith("event: "):
                    current_event = line[len("event: "):].strip()
                    continue
                if not line.startswith("data: "):
                    continue
                raw = line[len("data: "):]
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                et = current_event or data.get("type") or ""
                if et == "session":
                    sid = data.get("session_id")
                    if sid:
                        await on_session(sid)
                elif et == "answer":
                    text = (data.get("text") or "").strip()
                    if text:
                        final_parts.append(text)
                elif et == "error":
                    raise RuntimeError(data.get("message") or "Unknown agent error")
                elif et == "done":
                    break
                else:
                    label = _format_progress(et, data)
                    if label:
                        await on_progress(label)
    return "\n\n".join(final_parts).strip() or "_(no answer text returned)_"


# ─────────────────────────────────────────────────────────────────────────────
# Slack handlers
# ─────────────────────────────────────────────────────────────────────────────


def _thread_key(channel: str, thread_ts: Optional[str], is_dm: bool) -> str:
    if is_dm:
        return f"dm:{channel}"
    return f"{channel}:{thread_ts or 'root'}"


def _get_lock(key: str) -> asyncio.Lock:
    lock = _THREAD_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _THREAD_LOCKS[key] = lock
    return lock


async def _ensure_bot_user_id(client) -> str:
    global _bot_user_id
    if _bot_user_id is None:
        auth = await client.auth_test()
        _bot_user_id = auth["user_id"]
    return _bot_user_id


async def _handle_event(event: dict, client, is_dm: bool = False) -> None:
    channel = event["channel"]
    thread_ts = event.get("thread_ts") or event.get("ts")
    user_text = event.get("text") or ""

    bot_uid = await _ensure_bot_user_id(client)
    cleaned = _strip_bot_mention(user_text, bot_uid)
    name, task = _parse_agent_name(cleaned)
    key = _thread_key(channel, thread_ts, is_dm)

    employee = await _find_employee_by_name(name) if name else None

    # Look up the employee before judging "no task" — that way a single-word
    # greeting like "@bot hello" lands in the friendly "I don't know hello"
    # path rather than asking what `hello` should do.
    if not name or employee is None:
        prefix = (
            f"I don't know an employee named `{name}`. "
            if name and employee is None
            else ""
        )
        await client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=(
                prefix
                + "Tag an employee by name, e.g. `@BNY Agent Walter, summarize "
                "the 10-K`. For multi-word names use a comma "
                "(`@BNY Agent Big Boss, do X`) or underscores "
                "(`@BNY Agent Big_Boss do X`). Case-insensitive match "
                "against the employees you've created in the BNY Agent UI."
            ),
        )
        return

    display_name = employee.get("name") or name
    if not task:
        await client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text=f"What should `{display_name}` do? Try `@BNY Agent {display_name}, <task>`.",
        )
        return
    placeholder = await client.chat_postMessage(
        channel=channel,
        thread_ts=thread_ts,
        text=f"_{display_name} is thinking…_",
        username=display_name,  # requires chat:write.customize
    )
    msg_ts = placeholder["ts"]

    lock = _get_lock(key)
    state = {"last_edit": 0.0, "pending": None}

    async def on_progress(label: str):
        state["pending"] = label
        async with lock:
            now = asyncio.get_event_loop().time()
            if now - state["last_edit"] < _EDIT_DEBOUNCE_SECS:
                return
            text_now = state["pending"]
            if text_now is None:
                return
            state["pending"] = None
            try:
                await client.chat_update(
                    channel=channel,
                    ts=msg_ts,
                    text=f"_{display_name}_: {text_now}",
                )
                state["last_edit"] = now
            except Exception:
                logger.exception("Slack chat_update failed during progress")

    async def on_session(sid: str):
        _THREAD_SESSIONS[key] = sid

    session_id = _THREAD_SESSIONS.get(key)
    try:
        final = await _stream_agent(
            employee_id=employee["id"],
            question=task,
            session_id=session_id,
            on_progress=on_progress,
            on_session=on_session,
        )
    except Exception as exc:
        logger.exception("Slack agent call failed")
        try:
            await client.chat_update(
                channel=channel,
                ts=msg_ts,
                text=f"_{display_name}_: ❌ {exc}",
            )
        except Exception:
            logger.exception("Slack chat_update failed during error reporting")
        return

    final_text = _truncate_for_slack(f"*{display_name}*: {final}")
    try:
        await client.chat_update(
            channel=channel,
            ts=msg_ts,
            text=final_text,
        )
    except Exception:
        logger.exception("Slack chat_update failed during final answer")


def _register_handlers(app: AsyncApp) -> None:
    @app.event("app_mention")
    async def _on_mention(event, client):
        await _handle_event(event, client, is_dm=False)

    @app.event("message")
    async def _on_message(event, client):
        # Only handle DMs here; channel messages would loop with app_mention.
        if event.get("channel_type") != "im":
            return
        # Drop edits, deletes, joins, and other non-user-typed system events.
        subtype = event.get("subtype")
        if subtype and subtype not in {"file_share"}:
            return
        # Identify the message as coming from the bot itself across every
        # delivery shape Slack uses. ``bot_id`` and ``subtype: bot_message``
        # cover the documented cases; the ``user == bot_uid`` check is the
        # backstop that catches chat.postMessage replies Slack delivers
        # without a bot_id (the cause of the DM self-reply loop).
        if event.get("bot_id") or event.get("app_id"):
            return
        bot_uid = await _ensure_bot_user_id(client)
        if event.get("user") == bot_uid:
            return
        await _handle_event(event, client, is_dm=True)


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point used by server.py's lifespan
# ─────────────────────────────────────────────────────────────────────────────


async def start_in_background() -> Optional[asyncio.Task]:
    """Start the Socket Mode connection on a background task.

    Returns the task so ``server.py``'s lifespan can cancel it on shutdown.
    Returns ``None`` if either Slack token is missing.
    """
    bot_token = os.getenv("SLACK_BOT_TOKEN")
    app_token = os.getenv("SLACK_APP_TOKEN")
    if not bot_token or not app_token:
        logger.info(
            "Slack disabled — set SLACK_BOT_TOKEN (xoxb-…) and "
            "SLACK_APP_TOKEN (xapp-…) in .env to enable."
        )
        return None

    bolt_app = AsyncApp(token=bot_token, logger=logger)
    _register_handlers(bolt_app)
    handler = AsyncSocketModeHandler(bolt_app, app_token)
    logger.info("Slack bot connecting via Socket Mode…")
    return asyncio.create_task(handler.start_async(), name="slack_socket_mode")
