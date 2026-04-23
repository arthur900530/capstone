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
