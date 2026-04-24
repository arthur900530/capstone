"""Transform persisted task-run events into visualizable trajectory trees."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


STATUS_SUCCESS = "success"
STATUS_FAILURE = "failure"
STATUS_UNKNOWN = "unknown"

NODE_ACTION = "action"
NODE_SEQUENCE = "sequence"


@dataclass
class TimeData:
    before: str | None = None
    after: str | None = None

    def to_dict(self) -> dict:
        return {
            "before": self.before,
            "after": self.after,
        }


@dataclass
class StateData:
    before: str | None = None
    after: str | None = None
    diff_score: float | None = None
    tool_output: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "before": self.before,
            "after": self.after,
            "diff_score": self.diff_score,
            "tool_output": self.tool_output,
            "extra": self.extra,
        }


@dataclass
class ActionNode:
    action: str
    state: StateData
    goal: str | None = None
    time: TimeData | None = None
    status: str = STATUS_UNKNOWN
    status_reason: str | None = None
    node_type: str = NODE_ACTION
    length: int = 1

    def to_dict(self) -> dict:
        return {
            "node_type": self.node_type,
            "action": self.action,
            "state": self.state.to_dict(),
            "goal": self.goal,
            "time": self.time.to_dict() if self.time is not None else None,
            "status": self.status,
            "status_reason": self.status_reason,
        }


@dataclass
class SequenceNode:
    nodes: list[ActionNode | "SequenceNode"]
    goal: str | None = None
    status: str = STATUS_UNKNOWN
    status_reason: str | None = None
    node_type: str = NODE_SEQUENCE

    @property
    def length(self) -> int:
        return len(self.nodes)

    def to_dict(self) -> dict:
        return {
            "node_type": self.node_type,
            "nodes": [to_dict(node) for node in self.nodes],
            "goal": self.goal,
            "status": self.status,
            "status_reason": self.status_reason,
        }


def to_dict(node: ActionNode | SequenceNode) -> dict:
    return node.to_dict()


def _join_text(parts: list[str]) -> str | None:
    cleaned = [part.strip() for part in parts if isinstance(part, str) and part.strip()]
    if not cleaned:
        return None
    return "\n\n".join(cleaned)


def _append_tool_output(node: ActionNode, text: str | None) -> None:
    if not text:
        return
    if node.state.tool_output:
        node.state.tool_output = f"{node.state.tool_output}\n\n{text}"
    else:
        node.state.tool_output = text


def _tool_category(tool_name: str | None) -> str:
    name = (tool_name or "").lower()
    if not name:
        return "other"
    if any(part in name for part in ("bash", "shell", "terminal", "execute")):
        return "terminal"
    if any(part in name for part in ("browser", "web", "navigate", "click", "scroll")):
        return "browse"
    if any(part in name for part in ("file", "edit", "write", "read")):
        return "file"
    return "other"


def _event_category(event_type: str, event: dict) -> str:
    if event_type == "file_edit":
        return "file"
    if event_type == "reflection":
        return "reflection"
    if event_type == "answer":
        return "answer"
    if event_type == "chat_response":
        return "chat"
    if event_type == "error":
        return "error"
    if event_type == "reasoning":
        return "reasoning"
    if event_type == "tool_call":
        return _tool_category(event.get("tool"))
    return "other"


def _compact_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return str(value)


def _maybe_sequence(nodes: list[ActionNode], goal: str | None = None) -> ActionNode | SequenceNode:
    if len(nodes) == 1:
        return nodes[0]
    return SequenceNode(nodes=nodes, goal=goal, status=_sequence_status(nodes))


def build_nodes_from_events(events: list[dict]) -> tuple[list[ActionNode], list[int]]:
    """Convert raw persisted events into action nodes plus trial boundaries."""
    nodes: list[ActionNode] = []
    trial_boundaries: list[int] = []
    pending_reasoning: list[str] = []
    current_trial = 1

    for event in events or []:
        event_type = event.get("type")
        timestamp = event.get("timestamp")

        if event_type == "trial_start":
            next_trial = int(event.get("trial") or (current_trial + 1 if nodes else 1))
            if nodes and len(nodes) not in trial_boundaries:
                trial_boundaries.append(len(nodes))
            current_trial = max(next_trial, 1)
            continue

        if event_type == "reasoning":
            text = _compact_text(event.get("text") or event.get("content"))
            if text:
                pending_reasoning.append(text)
            continue

        goal = _join_text(pending_reasoning)

        if event_type == "tool_call":
            tool = event.get("tool") or "unknown"
            detail = event.get("detail") or f"Calling {tool}"
            node = ActionNode(
                action=f"{tool}: {detail}",
                goal=goal,
                time=TimeData(before=timestamp),
                state=StateData(
                    extra={
                        "event_type": "tool_call",
                        "tool": tool,
                        "detail": detail,
                        "args": event.get("args") or {},
                        "turn": event.get("turn"),
                        "trial_index": current_trial,
                        "category": _event_category(event_type, event),
                    }
                ),
            )
            nodes.append(node)
            pending_reasoning = []
            continue

        if event_type == "file_edit":
            path = event.get("path") or "(unknown path)"
            command = event.get("command") or "edit"
            node = ActionNode(
                action=f"{command}: {path}",
                goal=goal,
                time=TimeData(before=timestamp, after=timestamp),
                state=StateData(
                    extra={
                        "event_type": "file_edit",
                        "command": command,
                        "path": path,
                        "file_text": event.get("file_text"),
                        "old_str": event.get("old_str"),
                        "new_str": event.get("new_str"),
                        "insert_line": event.get("insert_line"),
                        "turn": event.get("turn"),
                        "trial_index": current_trial,
                        "category": "file",
                    }
                ),
            )
            nodes.append(node)
            pending_reasoning = []
            continue

        if event_type == "tool_result":
            text = _compact_text(event.get("text") or event.get("content"))
            if nodes:
                _append_tool_output(nodes[-1], text)
                if nodes[-1].time is None:
                    nodes[-1].time = TimeData(after=timestamp)
                else:
                    nodes[-1].time.after = timestamp
            continue

        if event_type == "self_eval":
            if nodes:
                nodes[-1].status = (
                    STATUS_SUCCESS if event.get("is_confident") else STATUS_FAILURE
                )
                nodes[-1].status_reason = _compact_text(event.get("critique"))
                nodes[-1].state.extra.setdefault("self_eval", {})
                nodes[-1].state.extra["self_eval"] = {
                    "is_confident": event.get("is_confident"),
                    "confidence_score": event.get("confidence_score"),
                    "critique": event.get("critique"),
                }
                if nodes[-1].time is None:
                    nodes[-1].time = TimeData(after=timestamp)
                else:
                    nodes[-1].time.after = timestamp
            continue

        if event_type == "reflection":
            text = _compact_text(event.get("text") or event.get("content"))
            node = ActionNode(
                action="reflection",
                goal=goal,
                time=TimeData(before=timestamp, after=timestamp),
                state=StateData(
                    tool_output=text,
                    extra={
                        "event_type": "reflection",
                        "trial_index": current_trial,
                        "category": "reflection",
                    },
                ),
            )
            nodes.append(node)
            pending_reasoning = []
            continue

        if event_type in {"answer", "chat_response", "error"}:
            text = _compact_text(event.get("text") or event.get("message") or event.get("content"))
            status = STATUS_FAILURE if event_type == "error" else STATUS_SUCCESS
            node = ActionNode(
                action=event_type,
                goal=goal,
                status=status,
                time=TimeData(before=timestamp, after=timestamp),
                state=StateData(
                    tool_output=text,
                    extra={
                        "event_type": event_type,
                        "trial_index": current_trial,
                        "category": _event_category(event_type, event),
                    },
                ),
            )
            nodes.append(node)
            pending_reasoning = []
            continue

    return nodes, trial_boundaries


def _collapse_trial_nodes(nodes: list[ActionNode]) -> list[ActionNode | SequenceNode]:
    collapsed: list[ActionNode | SequenceNode] = []
    current_bucket: list[ActionNode] = []
    current_category: str | None = None

    for node in nodes:
        category = node.state.extra.get("category") or "other"
        if current_bucket and category != current_category:
            collapsed.append(_maybe_sequence(current_bucket))
            current_bucket = []
        current_bucket.append(node)
        current_category = category

    if current_bucket:
        collapsed.append(_maybe_sequence(current_bucket))
    return collapsed


def _sequence_status(nodes: list[ActionNode | SequenceNode]) -> str:
    statuses = [getattr(node, "status", STATUS_UNKNOWN) for node in nodes]
    if any(status == STATUS_FAILURE for status in statuses):
        return STATUS_FAILURE
    if any(status == STATUS_SUCCESS for status in statuses):
        return STATUS_SUCCESS
    return STATUS_UNKNOWN


def segment_nodes(nodes: list[ActionNode], trial_boundaries: list[int]) -> SequenceNode:
    """Group action nodes into a rule-based hierarchy."""
    boundaries = sorted(set(i for i in trial_boundaries if 0 < i < len(nodes)))
    ranges: list[tuple[int, int]] = []
    start = 0
    for boundary in boundaries:
        ranges.append((start, boundary))
        start = boundary
    ranges.append((start, len(nodes)))

    trial_nodes: list[ActionNode | SequenceNode] = []
    for trial_idx, (trial_start, trial_end) in enumerate(ranges, start=1):
        trial_actions = nodes[trial_start:trial_end]
        if not trial_actions:
            continue
        for action in trial_actions:
            action.state.extra.setdefault("trial_index", trial_idx)
        collapsed = _collapse_trial_nodes(trial_actions)
        trial_node = SequenceNode(
            nodes=collapsed,
            goal=f"Trial {trial_idx}",
            status=_sequence_status(collapsed),
        )
        trial_nodes.append(trial_node)

    root = SequenceNode(
        nodes=trial_nodes or [],
        goal="Task trajectory",
        status=_sequence_status(trial_nodes),
    )
    return root


def flatten_action_nodes(node: ActionNode | SequenceNode) -> list[ActionNode]:
    if isinstance(node, ActionNode):
        return [node]

    flat: list[ActionNode] = []
    for child in node.nodes:
        flat.extend(flatten_action_nodes(child))
    return flat


# ── Goal hierarchy (for the employee report card) ───────────────────────────
#
# The report card visualizes a task as a set of "top-level goals", each with
# (optionally) nested sub-goals and a pool of leaf action steps underneath.
# A segmented bar rendered from this hierarchy uses each top-level goal's
# leaf_total as its width and leaf_rate as its color, so the bar honestly
# reflects where the agent spent effort and how much of it actually worked.


def _child_path(parent: str, index: int) -> str:
    return str(index) if parent == "root" else f"{parent}.{index}"


def _sequence_children_are_all_actions(node: dict) -> bool:
    children = node.get("nodes") or []
    if not children:
        return False
    return all(child.get("node_type") == "action" for child in children)


def _sequence_has_sequence_children(node: dict) -> bool:
    return any(
        (child.get("node_type") == "sequence")
        for child in (node.get("nodes") or [])
    )


def _top_level_sequences(
    root: dict,
    annotations: dict | None,
) -> list[tuple[dict, str, list[str | None]]]:
    """Return the (node, path, ancestor_statuses) tuples that become the
    "top-level goals" on the report card.

    ``segment_nodes`` produces a three-level tree:
        root  →  trial_N  →  category-collapsed sub-sequences (the goals)
    We skip the trial wrappers so goals from every trial appear as peers on
    one segmented bar; the rare two-level degenerate tree
    (root → all-action leaf) falls back to surfacing the root itself.

    ``ancestor_statuses`` is the chain of LLM-annotation statuses from the
    tree root down to (but not including) the surfaced goal. It's what
    lets the depth-weighted scoring credit a root-level "failure" verdict
    even when the surfaced goals are all "success" — without it, the UI
    would paint a reassuring green bar over a session the LLM flagged.
    """
    results: list[tuple[dict, str, list[str | None]]] = []
    anns = annotations or {}
    root_status = (anns.get("root") or {}).get("status") or root.get("status")

    for i, child in enumerate(root.get("nodes") or []):
        if child.get("node_type") != "sequence":
            continue
        child_path = _child_path("root", i)
        child_status = (anns.get(child_path) or {}).get("status") or child.get("status")

        if _sequence_has_sequence_children(child):
            # Trial wrapper — surface its sequence children with [root, trial]
            # as their ancestor chain so the depth-weighted score sees both.
            for j, grand in enumerate(child.get("nodes") or []):
                if grand.get("node_type") == "sequence":
                    results.append(
                        (
                            grand,
                            _child_path(child_path, j),
                            [root_status, child_status],
                        )
                    )
            continue

        # Root child is itself a leaf goal (all actions) or an atypical
        # single-level sequence — surface it directly with [root] ancestors.
        results.append((child, child_path, [root_status]))

    # Degenerate: the root has only action children (e.g. an ultra-short
    # single-step task). Treat the root as the one synthetic top-level goal
    # with an empty ancestor chain (it *is* the root).
    if not results and _sequence_children_are_all_actions(root):
        results.append((root, "root", []))

    return results


def _action_status(
    action: dict,
    inherited_status: str,
) -> str:
    """Leaf-step status: prefer an explicit action status (set from
    ``self_eval`` / terminal ``answer`` / ``error`` events), otherwise
    inherit the enclosing leaf sequence's LLM judgement so the KPI isn't
    mostly "unknown".
    """
    own = action.get("status") or STATUS_UNKNOWN
    if own in (STATUS_SUCCESS, STATUS_FAILURE):
        return own
    if inherited_status in (STATUS_SUCCESS, STATUS_FAILURE):
        return inherited_status
    return STATUS_UNKNOWN


def _leaf_step_dict(action: dict, path: str, inherited_status: str) -> dict:
    extra = (action.get("state") or {}).get("extra") or {}
    tool_output = (action.get("state") or {}).get("tool_output")
    return {
        "path": path,
        "action": action.get("action") or "",
        "status": _action_status(action, inherited_status),
        "category": extra.get("category") or "other",
        "tool_output_excerpt": (tool_output or "")[:400] if tool_output else None,
    }


def _leaf_stats(steps: list[dict]) -> dict:
    total = len(steps)
    achieved = sum(1 for s in steps if s["status"] == STATUS_SUCCESS)
    failed = sum(1 for s in steps if s["status"] == STATUS_FAILURE)
    unknown = total - achieved - failed
    rate = (achieved / total) if total else 0.0
    return {
        "total": total,
        "achieved": achieved,
        "failed": failed,
        "unknown": unknown,
        "rate": round(rate, 4),
    }


def _build_goal(
    node: dict,
    path: str,
    annotations: dict,
    depth: int,
    ancestor_status: str,
    ancestor_statuses: list[str | None] | None = None,
) -> dict:
    """Recursively produce a Goal dict from a SequenceNode."""
    ann = annotations.get(path) or {}
    llm = node.get("llm") or {}  # Present if apply_annotations() already ran.
    goal_text = ann.get("goal") or llm.get("goal") or node.get("goal") or "Sub-goal"
    status = ann.get("status") or llm.get("status") or node.get("status") or STATUS_UNKNOWN
    status_reason = ann.get("status_reason") or llm.get("status_reason")
    # Propagate the strongest known status from this node down into its
    # action descendants so leaf-step KPIs aren't starved of signal.
    effective_status = (
        status
        if status in (STATUS_SUCCESS, STATUS_FAILURE)
        else ancestor_status
    )

    children = node.get("nodes") or []
    goal: dict = {
        "path": path,
        "goal": goal_text,
        "status": status,
        "status_reason": status_reason,
        "depth": depth,
        # Chain of LLM-verdict statuses from the task root down to (but
        # excluding) this goal. The depth-weighted scoring uses it so a
        # root-level "failure" annotation can pull a top-level goal's
        # displayed rate down even when the goal itself was "success".
        "ancestor_statuses": list(ancestor_statuses or []),
        "is_leaf": _sequence_children_are_all_actions(node),
        "subgoals": [],
        "leaf_steps": [],
    }

    if goal["is_leaf"]:
        steps = [
            _leaf_step_dict(child, _child_path(path, i), effective_status)
            for i, child in enumerate(children)
            if child.get("node_type") == "action"
        ]
        goal["leaf_steps"] = steps
        goal.update(_prefixed_leaf_stats(_leaf_stats(steps)))
        return goal

    # Non-leaf: recurse into child sequences; skip any stray action children
    # (they're rare but possible around terminal events).
    subgoals: list[dict] = []
    orphan_steps: list[dict] = []
    child_ancestors = list(goal["ancestor_statuses"]) + [status]
    for i, child in enumerate(children):
        child_path = _child_path(path, i)
        if child.get("node_type") == "sequence":
            subgoals.append(
                _build_goal(
                    child,
                    child_path,
                    annotations,
                    depth + 1,
                    effective_status,
                    ancestor_statuses=child_ancestors,
                )
            )
        elif child.get("node_type") == "action":
            orphan_steps.append(
                _leaf_step_dict(child, child_path, effective_status)
            )

    goal["subgoals"] = subgoals
    goal["leaf_steps"] = orphan_steps

    # Aggregate leaf stats across all descendants so the segmented bar width
    # = leaf_total and segment color = leaf_rate of the whole subtree.
    agg_total = sum(g["leaf_total"] for g in subgoals) + len(orphan_steps)
    agg_achieved = sum(g["leaf_achieved"] for g in subgoals) + sum(
        1 for s in orphan_steps if s["status"] == STATUS_SUCCESS
    )
    agg_failed = sum(g["leaf_failed"] for g in subgoals) + sum(
        1 for s in orphan_steps if s["status"] == STATUS_FAILURE
    )
    agg_unknown = agg_total - agg_achieved - agg_failed
    agg_rate = (agg_achieved / agg_total) if agg_total else 0.0
    goal.update(
        {
            "leaf_total": agg_total,
            "leaf_achieved": agg_achieved,
            "leaf_failed": agg_failed,
            "leaf_unknown": agg_unknown,
            "leaf_rate": round(agg_rate, 4),
        }
    )
    return goal


def _prefixed_leaf_stats(stats: dict) -> dict:
    return {
        "leaf_total": stats["total"],
        "leaf_achieved": stats["achieved"],
        "leaf_failed": stats["failed"],
        "leaf_unknown": stats["unknown"],
        "leaf_rate": stats["rate"],
    }


def extract_goal_hierarchy(
    tree: SequenceNode | dict,
    annotations: dict | None = None,
) -> list[dict]:
    """Return the list of top-level goals for a task as a hierarchy.

    Each top-level goal carries nested ``subgoals`` and ``leaf_steps`` along
    with rolled-up ``leaf_total`` / ``leaf_achieved`` / ``leaf_rate`` counters.
    If the tree is degenerate (no sequence-of-sequences), a single synthetic
    top-level goal is returned so the bar visualization always has one
    segment.
    """
    tree_dict = tree.to_dict() if isinstance(tree, SequenceNode) else tree
    annotations = annotations or {}

    top_level = _top_level_sequences(tree_dict, annotations)
    goals: list[dict] = []
    for node, path, ancestor_statuses in top_level:
        # The nearest-known ancestor status is what leaf-step inheritance
        # uses when an action has no explicit self_eval; walk the chain
        # backward so a leaf in a "trial failure → sub-goal unknown" tree
        # still inherits the trial's failure verdict.
        nearest = next(
            (s for s in reversed(ancestor_statuses) if s in (STATUS_SUCCESS, STATUS_FAILURE)),
            STATUS_UNKNOWN,
        )
        goals.append(
            _build_goal(
                node,
                path,
                annotations,
                depth=0,
                ancestor_status=nearest,
                ancestor_statuses=ancestor_statuses,
            )
        )

    if goals:
        return goals

    # Fallback: flatten all actions into a single synthetic "Task" goal.
    all_actions: list[dict] = []

    def _walk(node: dict, path: str) -> None:
        if not isinstance(node, dict):
            return
        if node.get("node_type") == "action":
            all_actions.append(
                _leaf_step_dict(node, path, STATUS_UNKNOWN)
            )
            return
        for i, child in enumerate(node.get("nodes") or []):
            _walk(child, _child_path(path, i))

    _walk(tree_dict, "root")
    if not all_actions:
        return []
    stats = _leaf_stats(all_actions)
    return [
        {
            "path": "root",
            "goal": tree_dict.get("goal") or "Task",
            "status": tree_dict.get("status") or STATUS_UNKNOWN,
            "status_reason": None,
            "depth": 0,
            "is_leaf": True,
            "subgoals": [],
            "leaf_steps": all_actions,
            **_prefixed_leaf_stats(stats),
        }
    ]


def top_level_summary(goals: list[dict]) -> dict:
    """Counters for the 'Top-level goals' KPI tile.

    ``fully_achieved`` counts goals where BOTH (a) every leaf step succeeded
    (leaf_rate == 1.0) AND (b) the LLM didn't flag the goal as a failure.
    The conjunction keeps the KPI honest in two directions: a clean leaf
    trace can't hide an overall-goal failure the LLM identified, and a rosy
    LLM verdict can't hide sub-step failures.
    ``llm_achieved`` / ``llm_failed`` remain the raw per-verdict counts so
    callers can still see the LLM-only signal if they need it.
    """
    total = len(goals)
    fully = sum(
        1
        for g in goals
        if g.get("leaf_total", 0) > 0
        and g.get("leaf_rate") == 1.0
        and g.get("status") != STATUS_FAILURE
    )
    llm_achieved = sum(1 for g in goals if g.get("status") == STATUS_SUCCESS)
    llm_failed = sum(1 for g in goals if g.get("status") == STATUS_FAILURE)
    return {
        "total": total,
        "fully_achieved": fully,
        "llm_achieved": llm_achieved,
        "llm_failed": llm_failed,
    }


def leaf_step_summary(goals: list[dict]) -> dict:
    """Aggregated leaf-step counters across every top-level goal's subtree."""
    total = sum(int(g.get("leaf_total") or 0) for g in goals)
    achieved = sum(int(g.get("leaf_achieved") or 0) for g in goals)
    failed = sum(int(g.get("leaf_failed") or 0) for g in goals)
    unknown = total - achieved - failed
    rate = (achieved / total) if total else 0.0
    return {
        "total": total,
        "achieved": achieved,
        "failed": failed,
        "unknown": unknown,
        "rate": round(rate, 4),
    }


# ── Depth-weighted aggregated score ─────────────────────────────────────────
#
# "Overall success rate" for a session and "step success rate" both use the
# same aggregated-mean formula:
#
#     score = Σ_d  w_d · mean_d   /   Σ_d  w_d                 (w_d = 0.5^(d+1))
#
# where ``mean_d`` is the mean binary status (success=1, failure=0, unknown
# skipped) of every node at depth d, and the normalisation by observed
# weights keeps the result in [0,1] even when some levels carry no signal.
# Top-level goals live at depth 0 so they contribute with weight 0.5, their
# sub-goals at 0.25, leaf steps at 0.125, and so on — matching the spec.


def _status_bit(status: str | None) -> int | None:
    if status == STATUS_SUCCESS:
        return 1
    if status == STATUS_FAILURE:
        return 0
    return None


def _collect_level_bits(
    goal: dict,
    levels: dict[int, list[int]],
    depth: int,
) -> None:
    """Mutate ``levels`` so ``levels[d]`` holds every known status bit at
    depth ``d`` of the goal tree rooted at ``goal``. Leaf action steps live
    one level below their enclosing leaf goal.
    """
    bit = _status_bit(goal.get("status"))
    if bit is not None:
        levels.setdefault(depth, []).append(bit)

    subs = goal.get("subgoals") or []
    if subs:
        for sg in subs:
            _collect_level_bits(sg, levels, depth + 1)
        return

    steps = goal.get("leaf_steps") or []
    for step in steps:
        step_bit = _status_bit(step.get("status"))
        if step_bit is not None:
            levels.setdefault(depth + 1, []).append(step_bit)


def _score_from_levels(levels: dict[int, list[int]]) -> float | None:
    """Compute Σ(w_d · mean_d) / Σ(w_d) with w_d = 0.5^(d+1).

    Returns ``None`` when no level carries any known signal (the whole
    subtree is still unannotated) so callers can distinguish "zero score"
    from "no signal".
    """
    num = 0.0
    den = 0.0
    for depth in sorted(levels.keys()):
        arr = levels[depth]
        if not arr:
            continue
        weight = 0.5 ** (depth + 1)
        mean = sum(arr) / len(arr)
        num += weight * mean
        den += weight
    if den <= 0:
        return None
    return num / den


def _prepend_ancestor_bits(
    levels: dict[int, list[int]],
    ancestor_statuses: list[str | None] | None,
) -> int:
    """Seed ``levels`` with ancestor status bits at depths 0..len-1 and
    return the depth offset (= len of ancestor chain) that the goal
    itself should enter at.

    Unknown ancestors still advance the depth offset so nested goals
    stay at the right level even when the LLM verdict is missing.
    """
    offset = 0
    for depth, status in enumerate(ancestor_statuses or []):
        bit = _status_bit(status)
        if bit is not None:
            levels.setdefault(depth, []).append(bit)
        offset = depth + 1
    return offset


def weighted_goal_score(goal: dict) -> float | None:
    """Depth-weighted aggregated score for a goal *in its tree context*.

    Ancestor LLM verdicts (from the goal's ``ancestor_statuses`` chain)
    enter at shallow depths so a root-level "failure" isn't silently
    dropped when we score one of its descendant goals. The goal itself
    then sits at ``len(ancestor_statuses)`` (weight 0.5^(k+1)), its
    subgoals one level deeper, and so on.
    """
    levels: dict[int, list[int]] = {}
    offset = _prepend_ancestor_bits(levels, goal.get("ancestor_statuses"))
    _collect_level_bits(goal, levels, offset)
    return _score_from_levels(levels)


def weighted_task_score_from_tree(
    tree_dict: dict | None,
    annotations: dict | None,
) -> float | None:
    """Full-tree depth-weighted score using the stored LLM annotations.

    Walks the segmented trajectory tree from the root and credits every
    node at its tree depth: the root sits at depth 0 (weight 0.5), trial
    wrappers at depth 1, category-collapsed goals at depth 2, and leaf
    ActionNodes at the bottom. Each sequence node's status prefers its
    LLM annotation (``annotations[path]``) over the rule-based fallback
    so the "overall success rate" always honours the latest verdict —
    including the root annotation, which the earlier implementation
    dropped before reaching the KPIs.
    """
    if not tree_dict:
        return None
    anns = annotations or {}
    levels: dict[int, list[int]] = {}

    def walk(node: dict, path: str, depth: int) -> None:
        if not isinstance(node, dict):
            return
        if node.get("node_type") == "action":
            bit = _status_bit(node.get("status"))
            if bit is not None:
                levels.setdefault(depth, []).append(bit)
            return
        ann = anns.get(path) or {}
        status = ann.get("status") or node.get("status")
        bit = _status_bit(status)
        if bit is not None:
            levels.setdefault(depth, []).append(bit)
        for i, child in enumerate(node.get("nodes") or []):
            walk(child, _child_path(path, i), depth + 1)

    walk(tree_dict, "root", 0)
    return _score_from_levels(levels)


def weighted_task_score(goals: list[dict]) -> float | None:
    """Depth-weighted aggregated score for a task given its extracted goals.

    Kept for callers that only have the surfaced goal list on hand (e.g.
    tests). Prefers the shared ancestor prefix baked into the first goal
    so root/trial LLM verdicts still surface in the score; callers with
    access to the raw tree + annotations should use
    :func:`weighted_task_score_from_tree` instead, which is strictly more
    accurate (it also accounts for sibling trials).
    """
    if not goals:
        return None
    levels: dict[int, list[int]] = {}
    shared_ancestors = goals[0].get("ancestor_statuses") or []
    offset = _prepend_ancestor_bits(levels, shared_ancestors)
    for g in goals:
        _collect_level_bits(g, levels, offset)
    return _score_from_levels(levels)


def _attach_weighted_rates(goals: list[dict]) -> None:
    """Populate ``weighted_rate`` on every goal in-place.

    Each goal's ``weighted_rate`` is the depth-weighted aggregated mean
    *including its ancestor LLM verdicts* so a tooltip that claims
    "X% achieved" tells the same story as the task-level KPI — and
    crucially, a goal whose root was flagged "failure" can no longer
    paint itself green just because its own leaves succeeded.
    """
    def visit(goal: dict) -> None:
        for sg in (goal.get("subgoals") or []):
            # Sub-goals inherit their parent's ancestor chain + the
            # parent's own status so their score keeps the same context.
            sg["ancestor_statuses"] = list(goal.get("ancestor_statuses") or []) + [
                goal.get("status")
            ]
            visit(sg)
        goal["weighted_rate"] = weighted_goal_score(goal)

    for g in goals:
        visit(g)
