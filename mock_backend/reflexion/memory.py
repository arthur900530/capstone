"""
Episodic memory module for the Reflexion pipeline.

Stores and retrieves verbal reflections so the agent can learn from
past failures across multiple task attempts.  Persistence is via a
JSON file — simple, inspectable, and sufficient for a PoC.

Inspired by the episodic memory buffer described in the Reflexion
paper (Shinn et al., 2023).
"""

import json
import logging
import os
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

_PACKAGE_DIR = Path(__file__).resolve().parent
DEFAULT_MEMORY_PATH = str(_PACKAGE_DIR / "data" / "reflexion_memory.json")


@dataclass
class ReflectionEntry:
    """A single stored reflection with metadata for retrieval."""
    task_id: str
    task_description: str
    reflection: str
    score: float
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "ReflectionEntry":
        return cls(**data)


class ReflexionMemory:
    """Episodic memory buffer that persists reflections to a JSON file.

    Usage
    -----
    >>> mem = ReflexionMemory("reflexion_memory.json")
    >>> mem.store("task-1", "Deploy React app", "I forgot to run npm install...", 0.3)
    >>> relevant = mem.retrieve("Deploy React app", top_k=2)
    """

    def __init__(self, memory_path: str = DEFAULT_MEMORY_PATH):
        self._path = Path(memory_path)
        self._entries: List[ReflectionEntry] = []
        self._load()

    # ── Public API ────────────────────────────────────────────────────

    def store(
        self,
        task_id: str,
        task_description: str,
        reflection: str,
        score: float,
    ) -> None:
        """Persist a new reflection entry.

        Parameters
        ----------
        task_id : str
            Unique identifier for the task attempt.
        task_description : str
            Short description of the task (used for retrieval matching).
        reflection : str
            The verbal reflection text from the reflector.
        score : float
            The evaluation score (0.0–1.0) from the evaluator.
        """
        entry = ReflectionEntry(
            task_id=task_id,
            task_description=task_description,
            reflection=reflection,
            score=score,
        )
        self._entries.append(entry)
        self._save()
        logger.info(
            "Stored reflection for task '%s' (score=%.2f, total entries=%d)",
            task_id, score, len(self._entries),
        )

    def retrieve(
        self,
        task_description: str,
        top_k: int = 3,
    ) -> List[str]:
        """Retrieve the most relevant past reflections for a task.

        Current strategy: keyword overlap scored by Jaccard similarity
        between the query and each stored task description, with ties
        broken by recency.  This is intentionally simple — can be
        upgraded to embedding-based similarity later.

        Parameters
        ----------
        task_description : str
            Description of the upcoming task to find relevant reflections for.
        top_k : int
            Maximum number of reflections to return.

        Returns
        -------
        List[str]
            The reflection texts, ordered by relevance (most relevant first).
        """
        if not self._entries:
            return []

        query_tokens = self._tokenize(task_description)

        scored = []
        for entry in self._entries:
            entry_tokens = self._tokenize(entry.task_description)
            similarity = self._jaccard(query_tokens, entry_tokens)
            scored.append((similarity, entry.timestamp, entry))

        # Sort by similarity (desc), then recency (desc) as tiebreaker
        scored.sort(key=lambda x: (x[0], x[1]), reverse=True)

        results = [item[2].reflection for item in scored[:top_k]]
        logger.info(
            "Retrieved %d/%d reflections for query: %.60s...",
            len(results), len(self._entries), task_description,
        )
        return results

    def clear(self) -> None:
        """Remove all stored reflections and delete the backing file."""
        self._entries.clear()
        if self._path.exists():
            self._path.unlink()
        logger.info("Memory cleared")

    @property
    def size(self) -> int:
        """Number of stored reflection entries."""
        return len(self._entries)

    # ── Formatting helper ─────────────────────────────────────────────

    def format_for_prompt(
        self,
        task_description: str,
        top_k: int = 3,
    ) -> Optional[str]:
        """Retrieve reflections and format them for injection into
        the agent's prompt context.

        Returns None if there are no relevant reflections, so the caller
        can skip injection cleanly.
        """
        reflections = self.retrieve(task_description, top_k=top_k)
        if not reflections:
            return None

        header = "The following are reflections from your previous attempts. " \
                 "Use these lessons to avoid repeating the same mistakes:\n\n"
        body = "\n---\n".join(
            f"Reflection {i+1}:\n{r}" for i, r in enumerate(reflections)
        )
        return header + body

    # ── Private helpers ───────────────────────────────────────────────

    def _load(self) -> None:
        """Load entries from the JSON file if it exists."""
        if not self._path.exists():
            self._entries = []
            return

        try:
            with open(self._path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            self._entries = [ReflectionEntry.from_dict(item) for item in raw]
            logger.info("Loaded %d entries from %s", len(self._entries), self._path)
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("Corrupt memory file %s — starting fresh: %s", self._path, exc)
            self._entries = []

    def _save(self) -> None:
        """Write all entries to the JSON file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump([e.to_dict() for e in self._entries], f, indent=2)

    @staticmethod
    def _tokenize(text: str) -> set:
        """Lowercase split into a set of tokens for Jaccard comparison."""
        return set(text.lower().split())

    @staticmethod
    def _jaccard(a: set, b: set) -> float:
        """Jaccard similarity between two token sets."""
        if not a and not b:
            return 0.0
        intersection = a & b
        union = a | b
        return len(intersection) / len(union)
