"""Workflow tree extraction + persistence for skills.

A `Workflow` represents the structured, time-stamped sequence of steps that
demonstrates a skill, typically extracted from a video by the skill-ingestor
LLM. Workflows are stored next to `SKILL.md` as `workflow.json` so they can
be reloaded for video review and used as expected-trajectory ground truth
during LLM-as-judge evaluation.

The dataclasses mirror the style of :mod:`backend.trajectory` so the same
front-end tree component can render both workflows and live trajectories.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable


NODE_WORKFLOW_STEP = "workflow_step"


@dataclass
class WorkflowStep:
    """One node in a workflow tree.

    A leaf step (no children) is the unit of LLM-judge per-step adherence
    grading; non-leaf steps are containers used to group sub-steps and
    provide subtree-level rollups.
    """

    title: str
    description: str = ""
    start_time: float | None = None
    end_time: float | None = None
    children: list["WorkflowStep"] = field(default_factory=list)
    node_type: str = NODE_WORKFLOW_STEP

    def to_dict(self) -> dict:
        return {
            "node_type": self.node_type,
            "title": self.title,
            "description": self.description,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "children": [child.to_dict() for child in self.children],
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "WorkflowStep":
        if not isinstance(data, dict):
            raise ValueError("WorkflowStep payload must be an object")
        title = str(data.get("title") or "").strip()
        if not title:
            raise ValueError("WorkflowStep.title is required")

        raw_children = data.get("children") or []
        children: list[WorkflowStep] = []
        if isinstance(raw_children, list):
            for child in raw_children:
                try:
                    children.append(cls.from_dict(child))
                except Exception:
                    # Drop malformed children but keep the rest of the tree.
                    continue

        return cls(
            title=title,
            description=str(data.get("description") or ""),
            start_time=_coerce_time(data.get("start_time")),
            end_time=_coerce_time(data.get("end_time")),
            children=children,
        )


@dataclass
class Workflow:
    """A rooted forest of workflow steps tied to one skill / source file."""

    skill_name: str
    title: str
    summary: str = ""
    source_file: str | None = None
    root_steps: list[WorkflowStep] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "skill_name": self.skill_name,
            "title": self.title,
            "summary": self.summary,
            "source_file": self.source_file,
            "root_steps": [step.to_dict() for step in self.root_steps],
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "Workflow":
        if not isinstance(data, dict):
            raise ValueError("Workflow payload must be an object")

        skill_name = str(data.get("skill_name") or "").strip()
        title = str(data.get("title") or skill_name).strip()
        if not skill_name:
            raise ValueError("Workflow.skill_name is required")

        raw_steps = data.get("root_steps") or data.get("steps") or []
        if not isinstance(raw_steps, list):
            raw_steps = []
        steps: list[WorkflowStep] = []
        for raw in raw_steps:
            try:
                steps.append(WorkflowStep.from_dict(raw))
            except Exception:
                continue

        return cls(
            skill_name=skill_name,
            title=title or skill_name,
            summary=str(data.get("summary") or ""),
            source_file=(data.get("source_file") or None),
            root_steps=steps,
        )

    @classmethod
    def from_tool_args(cls, **kwargs: Any) -> "Workflow":
        """Build a Workflow from a ``record_workflow`` tool-call payload.

        The LLM emits ``steps`` as a flat keyword (matching the JSON schema)
        but our internal model uses ``root_steps``; normalize here so the
        ingestor can pass through the raw kwargs.
        """

        payload = dict(kwargs)
        if "steps" in payload and "root_steps" not in payload:
            payload["root_steps"] = payload.pop("steps")
        return cls.from_dict(payload)


def _coerce_time(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _skills_dir() -> Path:
    return Path(__file__).resolve().parent / "skills"


def workflow_path(slug: str) -> Path:
    """Return the canonical on-disk path for a skill's workflow JSON."""
    return _skills_dir() / slug / "workflow.json"


def load_workflow(slug: str) -> Workflow | None:
    """Load ``workflow.json`` for ``slug`` if present, else ``None``."""
    if not slug:
        return None
    path = workflow_path(slug)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    try:
        return Workflow.from_dict(data)
    except Exception:
        return None


def save_workflow(slug: str, workflow: Workflow) -> Path:
    """Persist ``workflow`` next to the skill's ``SKILL.md``."""
    path = workflow_path(slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(workflow.to_dict(), indent=2, sort_keys=False))
    return path


def _iter_leaf_paths(steps: Iterable[Any], prefix: tuple[int, ...] = ()) -> Iterable[tuple[int, ...]]:
    """Yield index paths to every leaf step in a (dict-shaped) workflow tree.

    The function accepts either dict payloads (the on-disk shape) or
    :class:`WorkflowStep` instances so callers may use whichever they have on
    hand without an extra conversion.
    """
    for idx, step in enumerate(steps):
        children = _children_of(step)
        path = prefix + (idx,)
        if not children:
            yield path
        else:
            yield from _iter_leaf_paths(children, path)


def _children_of(step: Any) -> list[Any]:
    if isinstance(step, WorkflowStep):
        return list(step.children)
    if isinstance(step, dict):
        children = step.get("children") or []
        if isinstance(children, list):
            return children
    return []


def _root_steps_of(workflow: Any) -> list[Any]:
    if isinstance(workflow, Workflow):
        return list(workflow.root_steps)
    if isinstance(workflow, dict):
        steps = workflow.get("root_steps")
        if isinstance(steps, list):
            return steps
    return []


def compute_workflow_completion(
    workflow: Any, alignment: dict | None
) -> dict | None:
    """Derive the deterministic ``{passed, total, rate}`` rollup.

    ``passed`` counts leaf steps whose entry in ``alignment["steps"]`` has
    ``satisfied: true``. Missing or malformed entries count as ``False``.
    ``rate`` is ``None`` when the workflow has zero leaves.
    """

    if not workflow:
        return None

    root_steps = _root_steps_of(workflow)
    leaf_paths = [list(p) for p in _iter_leaf_paths(root_steps)]
    total = len(leaf_paths)
    if total == 0:
        return {"passed": 0, "total": 0, "rate": None}

    satisfied_paths: set[tuple[int, ...]] = set()
    if isinstance(alignment, dict):
        for entry in alignment.get("steps") or []:
            if not isinstance(entry, dict):
                continue
            raw_path = entry.get("path")
            if not isinstance(raw_path, list) or not all(
                isinstance(i, int) for i in raw_path
            ):
                continue
            if entry.get("satisfied") is True:
                satisfied_paths.add(tuple(raw_path))

    passed = sum(1 for p in leaf_paths if tuple(p) in satisfied_paths)
    rate = passed / total
    return {"passed": passed, "total": total, "rate": rate}
