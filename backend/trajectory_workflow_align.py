"""LLM-driven alignment between an agent trajectory and an expected workflow.

This is the trajectory-page sibling of :mod:`backend.test_case_verifier`:
the test-case verifier judges a *test case run* against a workflow, this
module judges an arbitrary *task run trajectory* (recorded from a chat
session) against a workflow the user picks at view time.

Two outputs are returned:

- ``action_assignments``: per agent action, which workflow step (path)
  the action most closely advances, plus a short rationale. The frontend
  renders this as a chip on each action card so the user can see how
  every step maps onto the expected workflow.
- ``workflow_alignment``: per LEAF workflow step, a binary
  ``satisfied`` flag plus an evidence fragment. Identical shape to the
  test-case verifier output so :mod:`backend.workflow.compute_workflow_completion`
  can derive the ``{passed, total, rate}`` rollup deterministically.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from openai import AsyncOpenAI

from config import OPENAI_API_KEY, VERIFIER_MODEL
from test_case_verifier import _resolve_openai_model, _sanitize_alignment

logger = logging.getLogger(__name__)


_PROMPT = (
    "You are an evaluator that maps an AI agent's recorded trajectory to an "
    "expected workflow tree.\n\n"
    "Inputs:\n"
    "- workflow: a tree of expected steps. Each step has a title, an optional "
    "description, and optional nested 'children'. A LEAF step is one with "
    "no children.\n"
    "- actions: an ordered numbered list of actions the agent took. Each "
    "line looks like `[<idx>] Call \\`<tool>\\` — <key>=<value>; …` (or "
    "similar for file edits, reflections, errors, etc.). Treat the "
    "`<key>=<value>` fragments as ground truth — they are the actual tool "
    "arguments (URL, command, query, path, search text) the agent used.\n\n"
    "Tasks:\n"
    "1. For EACH action, decide which single workflow step it most closely "
    "advances. workflow_step_path is the index path into workflow.root_steps "
    "and then .children recursively (e.g. [0] = first root step, [1, 0] = "
    "first child of the second root step). Use [] (empty path) ONLY when "
    "the action is genuinely off-task or pure overhead (task tracker bookkeeping, "
    "MEMORY.md upkeep, internal reflections); DO NOT use [] just because "
    "the action's contribution is small — research/browsing/data extraction "
    "actions belong to the matching workflow leaf even when individual.\n"
    "2. For EVERY LEAF step in the workflow, decide whether the action set "
    "taken together SATISFIES that step. Adherence is BINARY (true/false), "
    "no partial credit.\n\n"
    "Return strict JSON with EXACTLY this shape:\n"
    "{\n"
    "  \"action_assignments\": [\n"
    "    {\"action_index\": <int>, \"workflow_step_path\": [<int>, ...], "
    "\"rationale\": <string>}\n"
    "  ],\n"
    "  \"workflow_alignment\": {\n"
    "    \"steps\": [\n"
    "      {\"path\": [<int>, ...], \"satisfied\": <bool>, \"evidence\": <string>}\n"
    "    ]\n"
    "  }\n"
    "}\n\n"
    "Constraints:\n"
    "- action_index is the zero-based index in the actions list and must be "
    "present for every action.\n"
    "- 'rationale' and 'evidence' fragments must be ≤ 200 chars.\n"
    "- When the action line carries a concrete fragment (URL, command, search "
    "query, file path, typed text), QUOTE that fragment verbatim in the "
    "rationale instead of paraphrasing — e.g. `navigates to gleif.org/lei-lookup` "
    "rather than `browser navigation likely starts LEI lookup`. This makes "
    "the assignments auditable.\n"
    "- Do not include any aggregate score; the consumer derives it from the "
    "step list."
)


def _sanitize_action_assignments(parsed: Any, action_count: int) -> list[dict[str, Any]]:
    """Coerce the LLM ``action_assignments`` payload into a safe list.

    Drops malformed entries silently so a partially garbled response still
    produces something usable.
    """
    if not isinstance(parsed, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for entry in parsed:
        if not isinstance(entry, dict):
            continue
        idx = entry.get("action_index")
        if not isinstance(idx, int) or idx < 0 or idx >= action_count:
            continue
        path = entry.get("workflow_step_path")
        if not isinstance(path, list) or not all(isinstance(i, int) for i in path):
            path = []
        cleaned.append(
            {
                "action_index": idx,
                "workflow_step_path": list(path),
                "rationale": str(entry.get("rationale") or "")[:300],
            }
        )
    cleaned.sort(key=lambda e: e["action_index"])
    return cleaned


async def align_trajectory_to_workflow(
    *, workflow: dict, action_descriptions: list[str]
) -> dict[str, Any]:
    """Run the alignment LLM and return ``{action_assignments, workflow_alignment}``.

    ``action_descriptions`` is the ordered list of one-line strings for each
    action node in the trajectory (typically produced by the same helper
    that feeds :mod:`trajectory_llm`). The function does not mutate either
    argument.
    """
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is not configured; trajectory workflow alignment "
            "uses the same LLM judge as test-case verification."
        )

    target_model = _resolve_openai_model(VERIFIER_MODEL)
    client = AsyncOpenAI(api_key=OPENAI_API_KEY, timeout=60.0)

    # Tighten the actions block formatting to keep the model from drifting
    # off into prose: each line is ``[<idx>] <description>`` so the LLM has
    # an unambiguous handle to reference back as ``action_index``.
    actions_block = "\n".join(
        f"[{i}] {desc}" for i, desc in enumerate(action_descriptions)
    )
    payload = {
        "workflow": workflow,
        "actions": actions_block,
    }
    # Surface the actions we're feeding the judge so we can debug
    # "everything is unassigned" cases without re-deriving the trajectory:
    # if these lines look like ``Call `browser_navigate` — Calling
    # browser_navigate`` then args isn't being captured upstream; if they
    # look like ``Call `browser_navigate` — url=https://…`` then the judge
    # has the info and any genuine [] really is the model's choice.
    logger.info(
        "Workflow alignment input: %d actions, sample=%s",
        len(action_descriptions),
        action_descriptions[:5],
    )
    messages = [
        {"role": "system", "content": _PROMPT},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=True)},
    ]

    try:
        resp = await client.chat.completions.create(
            model=target_model,
            messages=messages,
            temperature=1.0,
            max_completion_tokens=32768,
            response_format={"type": "json_object"},
        )
    except Exception:
        # Fallback for models that don't support response_format.
        resp = await client.chat.completions.create(
            model=target_model,
            messages=messages,
            temperature=1.0,
            max_completion_tokens=32768,
        )

    content = ((resp.choices or [{}])[0].message.content or "").strip()
    logging.info(f"Workflow alignment LLM returned: {content}")
    try:
        parsed = json.loads(content) if content else {}
    except json.JSONDecodeError:
        logger.warning("Workflow alignment LLM returned non-JSON: %s", content[:300])
        parsed = {}
    if not isinstance(parsed, dict):
        parsed = {}

    return {
        "action_assignments": _sanitize_action_assignments(
            parsed.get("action_assignments"),
            action_count=len(action_descriptions),
        ),
        "workflow_alignment": _sanitize_alignment(parsed.get("workflow_alignment")),
    }
