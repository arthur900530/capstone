"""LLM-based post-processing of trajectory trees.

This module mirrors the `induce.py` step of
https://github.com/zorazrw/ai4work-resources/tree/main/profiling :
for every ``SequenceNode`` in a segmented trajectory we ask an LLM to
(a) summarize a concise ``goal`` from its child subgoals, and
(b) judge whether that goal was achieved by the underlying action sequence.

Prompts live in ``backend/prompts/`` and are loaded verbatim from the
reference repo so the induced-workflow semantics stay compatible.

The public entry points are:

- :func:`annotate_tree` — walks a tree, returns a ``{path -> annotation}``
  dict suitable for persisting as JSONB on ``task_runs``.
- :func:`apply_annotations` — merges a cached annotation dict back onto a
  serialized tree (``tree.to_dict()``) in-place so the frontend can render
  LLM goals / status without re-calling the model.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

from config import API_KEY, VERIFIER_MODEL, BASE_URL
from trajectory import (
    STATUS_FAILURE,
    STATUS_SUCCESS,
    STATUS_UNKNOWN,
    ActionNode,
    SequenceNode,
)

logger = logging.getLogger(__name__)

_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")

_GOAL_PROMPT_PATH = os.path.join(_PROMPTS_DIR, "get_node_goal.txt")
_STATUS_PROMPT_PATH = os.path.join(_PROMPTS_DIR, "get_node_status.txt")

# Cap LLM inputs so a single huge file edit or stdout dump can't blow up the
# context window. We keep tool output excerpts compact.
_MAX_SUBGOAL_CHARS = 400
_MAX_SUBGOALS = 40


def _load_prompt(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read().strip()


_GOAL_PROMPT = _load_prompt(_GOAL_PROMPT_PATH)
_STATUS_PROMPT = _load_prompt(_STATUS_PROMPT_PATH)


def _get_client():
    """Lazily build an AsyncOpenAI client pointing at our configured endpoint.

    Import is lazy so environments without the ``openai`` package (for ex.
    minimal CI) can still import the ``trajectory_llm`` module, as long as
    they never call :func:`annotate_tree`.
    """
    from openai import AsyncOpenAI  # type: ignore

    return AsyncOpenAI(api_key=API_KEY, base_url=BASE_URL)


# ── Subgoal extraction ──────────────────────────────────────────────────────


def _clip(text: str, limit: int = _MAX_SUBGOAL_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "…"


# Keys to surface first when building a tool-call summary. Order matters:
# the most diagnostic key for each tool family (URL for browse, command for
# bash, query for search) leads so the LLM can disambiguate calls of the
# same tool that target different workflow steps.
_PRIMARY_ARG_KEYS: tuple[str, ...] = (
    "command",                       # bash / terminal
    "query", "search_query", "q",    # web-search variants
    "url",                           # browser navigate / fetch
    "action",                        # browser_tool_set sub-action ("navigate", "click", …)
    "path",                          # file ops
    "code",                          # python / jupyter
    "prompt",                        # delegate / sub-agent
    "task",                          # task_tracker
    "selector",                      # css / xpath
    "index",                         # element index
    "text",                          # type / message
    "message",                       # finish-style
    "file_text",                     # create
    "new_str",                       # str_replace
    "old_str",                       # str_replace
    "insert_line",                   # insert mode
)

# Keys we deliberately drop from arg summaries — too long, binary, or
# pure scaffolding that adds noise without disambiguation value.
_NOISY_ARG_KEYS: frozenset[str] = frozenset(
    {"thoughts", "reasoning", "image_data", "screenshot", "encoded_image"}
)

_PRIMARY_KEY_BUDGET = 3
_TOTAL_KEY_BUDGET = 4


def _short_arg_value(value: Any, cap: int = 100) -> str:
    """Render a single arg value as a one-liner with sensible truncation."""
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            text = str(value)
    text = text.replace("\n", " ").strip()
    if len(text) > cap:
        text = text[: cap - 1].rstrip() + "…"
    return text


def _looks_boilerplate(detail: str, tool: str) -> bool:
    """``True`` when the persisted ``detail`` is the placeholder ``Calling X``."""
    return detail.lower() == f"calling {tool.lower()}"


def _summarize_tool_args(
    *,
    tool: str,
    args: dict[str, Any] | None,
    fallback_detail: str | None,
    fallback_action: str | None = None,
) -> str:
    """Build a compact ``key=value; key=value`` summary of a tool call.

    The annotator and workflow-alignment judge both rely on this string to
    tell apart calls that share the same tool name but advance very
    different workflow steps (e.g. browse-to-GLEIF vs. browse-to-Google
    News). High-signal keys (URL, command, query, action) are surfaced
    first so the most diagnostic info always lands inside the truncation
    budget. Fallbacks: persisted ``detail`` string → raw ``node.action``
    string with the ``"<tool>: "`` prefix stripped (the latter matters for
    pre-2026-04-23 sessions that were persisted before ``args`` was
    written into ``raw_events``).
    """
    detail = (fallback_detail or "").strip()
    action_str = (fallback_action or "").strip()
    # Strip the "<tool>: " prefix that ``trajectory.build_nodes_from_events``
    # bakes into ``ActionNode.action`` so the fallback isn't just the tool
    # name twice.
    prefix = f"{tool}: "
    if action_str.startswith(prefix):
        action_str = action_str[len(prefix):]
    detail_useful = bool(detail) and not _looks_boilerplate(detail, tool)
    action_useful = bool(action_str) and not _looks_boilerplate(action_str, tool)

    if isinstance(args, dict) and args:
        parts: list[str] = []
        seen: set[str] = set()

        for key in _PRIMARY_ARG_KEYS:
            if len(parts) >= _PRIMARY_KEY_BUDGET:
                break
            if key not in args:
                continue
            value = args[key]
            if value in (None, "", [], {}):
                continue
            parts.append(f"{key}={_short_arg_value(value)}")
            seen.add(key)

        for key, value in args.items():
            if len(parts) >= _TOTAL_KEY_BUDGET:
                break
            if key in seen or key in _NOISY_ARG_KEYS:
                continue
            if value in (None, "", [], {}):
                continue
            parts.append(f"{key}={_short_arg_value(value, cap=60)}")

        summary = "; ".join(parts)
        if summary:
            return summary

    # No usable args dict — fall back to the freest text we have so old
    # sessions (or events written by a code path that didn't persist args)
    # still expose something other than the bare tool name.
    if detail_useful:
        return detail
    if action_useful:
        return action_str
    return ""


def _action_subgoal(node: ActionNode) -> str:
    """One-line description of an ActionNode for the goal prompt."""
    extra = node.state.extra or {}
    event_type = extra.get("event_type") or "action"

    if event_type == "tool_call":
        tool = extra.get("tool") or "tool"
        summary = _summarize_tool_args(
            tool=tool,
            args=extra.get("args"),
            fallback_detail=extra.get("detail"),
            fallback_action=node.action,
        )
        line = f"Call `{tool}` — {summary}" if summary else f"Call `{tool}`"
        return _clip(line, 320)

    if event_type == "file_edit":
        command = extra.get("command") or "edit"
        path = extra.get("path") or "(unknown path)"
        # Surface a short preview of the changed content so the judge can
        # tell apart different edits to the same path (e.g. successive
        # str_replace passes on a report draft).
        preview_value = (
            extra.get("new_str")
            or extra.get("file_text")
            or extra.get("old_str")
            or ""
        )
        preview = _short_arg_value(preview_value, cap=160) if preview_value else ""
        if preview:
            return _clip(f"{command} `{path}` — {preview}", 320)
        return f"{command} `{path}`"

    if event_type == "reflection":
        text = node.state.tool_output or node.action
        return f"Reflect on progress — {_clip(text, 240)}"

    if event_type == "answer":
        return f"Produce answer — {_clip(node.state.tool_output or '', 240)}"

    if event_type == "chat_response":
        return f"Reply to user — {_clip(node.state.tool_output or '', 240)}"

    if event_type == "error":
        return f"Error — {_clip(node.state.tool_output or node.action, 240)}"

    return _clip(node.action, 240)


def _sequence_subgoal(node: SequenceNode) -> str:
    """Use the (just-computed) sequence goal as its subgoal line."""
    return _clip(node.goal or "Subsequence", 240)


def _child_subgoals(node: SequenceNode) -> list[str]:
    lines: list[str] = []
    for child in node.nodes:
        if isinstance(child, ActionNode):
            lines.append(_action_subgoal(child))
        else:
            lines.append(_sequence_subgoal(child))
    if len(lines) > _MAX_SUBGOALS:
        # Keep head + tail context, drop the middle to avoid context bloat.
        head = lines[: _MAX_SUBGOALS // 2]
        tail = lines[-_MAX_SUBGOALS // 2 :]
        lines = head + [f"… ({len(lines) - _MAX_SUBGOALS} more steps) …"] + tail
    return lines


def _sequence_status_from_children(node: SequenceNode) -> str:
    """Fallback status derivation when the LLM call is skipped or fails."""
    statuses = [getattr(child, "status", STATUS_UNKNOWN) for child in node.nodes]
    if any(s == STATUS_FAILURE for s in statuses):
        return STATUS_FAILURE
    if any(s == STATUS_SUCCESS for s in statuses):
        return STATUS_SUCCESS
    return STATUS_UNKNOWN


# ── LLM calls ───────────────────────────────────────────────────────────────


async def _call_llm(client, system_prompt: str, user_content: str) -> str:
    """Thin wrapper around chat completions with sensible defaults."""
    resp = await client.chat.completions.create(
        model=VERIFIER_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
    )
    choice = resp.choices[0] if resp.choices else None
    if choice is None or choice.message is None:
        return ""
    return (choice.message.content or "").strip()


async def _summarize_goal(client, subgoals: list[str]) -> str:
    text = "\n".join(f"[{i + 1}] {line}" for i, line in enumerate(subgoals))
    try:
        return (await _call_llm(client, _GOAL_PROMPT, text)).strip("`").strip()
    except Exception as exc:  # noqa: BLE001 — surface partial results, never crash the view
        logger.warning("goal summarization failed: %s", exc)
        return ""


async def _judge_status(client, goal: str, subgoals: list[str]) -> tuple[str, str | None]:
    user = (
        f"Goal: {goal}\n\n"
        "Action sequence:\n"
        + "\n".join(f"[{i + 1}] {line}" for i, line in enumerate(subgoals))
    )
    try:
        raw = (await _call_llm(client, _STATUS_PROMPT, user)).strip().upper()
    except Exception as exc:  # noqa: BLE001
        logger.warning("status judgment failed: %s", exc)
        return STATUS_UNKNOWN, None

    if raw.startswith("YES"):
        return STATUS_SUCCESS, None
    if raw.startswith("NO"):
        return STATUS_FAILURE, None
    return STATUS_UNKNOWN, raw[:120] or None


# ── Tree walk ───────────────────────────────────────────────────────────────


Annotation = dict[str, Any]
Annotations = dict[str, Annotation]


def _child_path(parent: str, index: int) -> str:
    if parent == "root":
        return str(index)
    return f"{parent}.{index}"


async def _annotate(
    node: ActionNode | SequenceNode,
    path: str,
    client,
    out: Annotations,
) -> None:
    if isinstance(node, ActionNode):
        return  # Action nodes already have per-event goal/status from segmentation.

    # Recurse into children concurrently — siblings can be annotated in parallel
    # because each only depends on its own descendants.
    await asyncio.gather(
        *[
            _annotate(child, _child_path(path, i), client, out)
            for i, child in enumerate(node.nodes)
        ]
    )

    # Now every child SequenceNode has a finalized goal text we can feed upward.
    # Apply pending annotations to the in-memory tree so _child_subgoals() sees
    # the LLM-summarized goal on nested sequences rather than "Trial N".
    for i, child in enumerate(node.nodes):
        child_path = _child_path(path, i)
        ann = out.get(child_path)
        if isinstance(child, SequenceNode) and ann:
            if ann.get("goal"):
                child.goal = ann["goal"]
            if ann.get("status"):
                child.status = ann["status"]

    subgoals = _child_subgoals(node)
    goal_text = await _summarize_goal(client, subgoals)

    # The ai4work pipeline re-derives status after summarizing the goal, so the
    # judgement can use the LLM-written goal rather than the heuristic one.
    status, status_reason = await _judge_status(client, goal_text or node.goal or "", subgoals)

    # Fall back to rule-based status aggregation if the judge was ambiguous.
    if status == STATUS_UNKNOWN:
        status = _sequence_status_from_children(node)

    out[path] = {
        "goal": goal_text or node.goal,
        "status": status,
        "status_reason": status_reason,
    }


async def annotate_tree(tree: SequenceNode) -> Annotations:
    """Run the full induce-style annotation pass and return a path->annotation map."""
    annotations: Annotations = {}
    client = _get_client()
    try:
        await _annotate(tree, "root", client, annotations)
    finally:
        close = getattr(client, "close", None)
        if close is not None:
            try:
                await close()
            except Exception:  # noqa: BLE001
                pass
    return annotations


# ── Applying cached annotations back to a serialized tree ───────────────────


def apply_annotations(tree_dict: dict, annotations: Annotations | None) -> dict:
    """Mutate ``tree_dict`` (the output of ``trajectory.to_dict``) so each
    sequence node carries its cached LLM annotation under ``llm``.

    We keep the original heuristic ``goal`` / ``status`` intact and store the
    LLM version under ``llm`` so the frontend can choose which to show.
    """
    if not annotations:
        return tree_dict

    def _walk(node: dict, path: str) -> None:
        if not isinstance(node, dict):
            return
        if node.get("node_type") != "sequence":
            return
        ann = annotations.get(path)
        if ann:
            node["llm"] = {
                "goal": ann.get("goal"),
                "status": ann.get("status"),
                "status_reason": ann.get("status_reason"),
            }
        for i, child in enumerate(node.get("nodes") or []):
            _walk(child, _child_path(path, i))

    _walk(tree_dict, "root")
    return tree_dict


__all__ = [
    "annotate_tree",
    "apply_annotations",
    "Annotations",
]
