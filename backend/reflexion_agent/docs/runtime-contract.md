# Runtime Contract

This document specifies what the Reflexion component **expects** from its
host runtime (`agent.py`) and from the broader environment. If any of these
requirements are violated, the Reflexion pipeline will either fail at
startup or produce incorrect results.

## 1. Import Contract

The public API is defined exclusively in `reflexion/__init__.py`:

```python
from reflexion import evaluate_trajectory, generate_reflection, ReflexionMemory
from reflexion import EvaluationResult  # if you need the dataclass
```

**Never** import submodules directly:

```python
# WRONG — breaks if internal file names change
from reflexion.evaluator import evaluate_trajectory
from reflexion.memory import ReflexionMemory
```

This discipline ensures the `reflexion/` package can be vendored or moved
into a monorepo without breaking external callers.

## 2. The `llm_call` Adapter

All three Reflexion modules (`evaluator`, `reflector`, `memory`) are
**decoupled** from the OpenHands SDK. They never import `openhands`
themselves. Instead, the host must provide a callable with this signature:

```python
def llm_call(system_prompt: str, user_prompt: str) -> str:
    ...
```

The callable must:

- Accept two positional string arguments.
- Return the LLM's response as a plain string.
- Handle retries and timeouts internally (the Reflexion modules do not retry).

In `agent.py`, this is built by `_make_llm_call(llm_client)`, which
wraps the OpenHands `LLM.completion()` API:

```python
def _make_llm_call(llm_client):
    def call(system_prompt: str, user_prompt: str) -> str:
        messages = [
            Message(role="system", content=[TextContent(text=system_prompt)]),
            Message(role="user", content=[TextContent(text=user_prompt)]),
        ]
        response = llm_client.completion(messages)
        return " ".join(
            c.text for c in response.message.content if hasattr(c, "text")
        )
    return call
```

If you switch LLM providers, you only need to rewrite this adapter —
the Reflexion modules remain unchanged.

## 3. The `trajectory` String

The evaluator and reflector both receive a `trajectory: str` parameter.
This must be a serialized representation of the agent's execution history.

In the current implementation, `agent.py` produces it with:

```python
trajectory = str(list(conversation.state.events))
```

Key requirements:

- Must include the agent's actions, tool calls, and observations.
- Must be serializable to a string (the Reflexion modules treat it as
  opaque text that gets forwarded to the LLM).
- Should not be truncated — the LLM judge needs the full log to assess
  success or failure.

**Common mistake:** Using `conversation.events` instead of
`conversation.state.events`. The `events` property does not exist on
`LocalConversation` directly; it lives on the `state` object.

## 4. The `task` String

Both `evaluate_trajectory()` and `generate_reflection()` receive a
`task: str` parameter. This must be the **original** user instruction,
**not** the augmented prompt that includes injected reflections.

In `agent.py`, the original instruction is stored in `instruction` while
the augmented one is stored in `full_instruction`. Always pass `instruction`:

```python
evaluation = evaluate_trajectory(
    task=instruction,       # original
    trajectory=trajectory,
    llm_call=llm_call,
)
```

If you pass `full_instruction` instead, the evaluator will see the
reflections as part of the task specification and produce a misleading
judgment.

## 5. Environment Variables

The Reflexion pipeline reads the following from `.env` (via `python-dotenv`):

| Variable | Default | Required | Purpose |
|---|---|---|---|
| `ENABLE_REFLEXION` | `false` | No | Set to `true` to activate the retry loop |
| `MAX_REFLEXION_ATTEMPTS` | `3` | No | How many attempts before giving up |
| `REFLEXION_SCORE_THRESHOLD` | `0.75` | No | Score escape hatch: loop exits when `evaluation.score >= threshold`, even if `success=False`. Valid range `0.0–1.0`; set to `1.0` to disable. Invalid values fall back to `0.75`. |
| `REFLEXION_MEMORY_PATH` | (blank) | No | Override the default memory file location |

When `REFLEXION_MEMORY_PATH` is blank or absent, `ReflexionMemory` uses
its built-in default: `reflexion/data/reflexion_memory.json` (resolved
relative to the package's own directory via `__file__`).

These variables are read in `agent.py`, not inside the `reflexion/` package.
The package itself has no knowledge of `.env` files.

### 5.1 Per-request override (HTTP API)

The FastAPI backend accepts `use_reflexion` (boolean, default `false`) on each
`POST /api/chat` body. The server passes this into `runtime(..., use_reflexion=...)`.
When `use_reflexion` is `true`, the Reflexion loop runs for that request even if
`ENABLE_REFLEXION` in `.env` is unset or false. When `use_reflexion` is `false`,
Reflexion is skipped for that request even if `ENABLE_REFLEXION=true` in `.env`.

For the CLI entrypoint (`python -m reflexion_agent.agent` or direct `runtime()` calls),
omit `use_reflexion` so it stays `None` and the effective behavior follows
`ENABLE_REFLEXION` / `MAX_REFLEXION_ATTEMPTS` from the environment.

### 5.2 Selected skills (`skill_ids`)

The FastAPI backend accepts an optional `skill_ids` field on each `POST /api/chat`
body: a list of skill identifiers matching the catalog returned by `GET /api/skills`.

When `skill_ids` is **non-empty**, the server builds a temporary workspace for that
request: it copies the optional `mount_dir` and any uploaded files into that
workspace, then **replaces** OpenHands project skill locations
(`.agents/skills/`, `.openhands/skills/`, and legacy `.openhands/microagents/`)
with packages materialized **only** for the listed IDs. The agent runtime’s
`load_project_skills(work_dir=...)` therefore sees exactly those skills for that
request (not a union with pre-existing skill trees from the copied mount).

When `skill_ids` is omitted or empty, behavior is unchanged from before: the
effective mount is the resolved upload staging and/or `mount_dir` without this
injection step.

Unknown IDs produce `400` with `Unknown skill_id: ...`. A skill that lists
auxiliary files in metadata but has no retrievable content (e.g. missing on disk
and not in memory) produces `400` with a clear message.

## 6. Python Version

The Reflexion modules use:
- Dataclasses (`dataclasses` module)
- `pathlib.Path`
- f-strings
- `typing.Optional`, `typing.List`

Minimum required: **Python 3.9+**. The OpenHands SDK requires 3.12+, so
this is satisfied by default in the capstone conda environment.

## 7. No External Dependencies

The `reflexion/` package imports only the Python standard library:
`json`, `logging`, `os`, `time`, `pathlib`, `dataclasses`, `typing`.

It has **zero** third-party dependencies. All LLM interaction is injected
via the `llm_call` callable. This is by design — it makes the package
trivially portable to the monorepo without adding dependency conflicts.

## 8. File System Assumptions

- `ReflexionMemory` creates the `reflexion/data/` directory automatically
  on first write (via `Path.parent.mkdir(parents=True, exist_ok=True)`).
- The memory JSON file is read/written with `utf-8` encoding.
- If the JSON file is corrupt, `_load()` logs a warning and starts with
  an empty list — it never crashes.
- The `reflexion/data/` directory is gitignored; runtime artifacts should
  not be committed.

---

## 9. `tools.py` Import Path Fragility (Monorepo Migration Risk)

The host runtime currently imports custom tools with a bare module name:

```python
# In agent.py (current)
from tools import BashTool, FileEditorTool, TaskTrackerTool
```

This is a **relative-to-cwd import**, not a package import. It only works
when `tools.py` is in the same directory as `agent.py` and Python is
invoked from that directory.

**When this breaks:** In the monorepo, `agent.py` will move to
`agent/agent.py`. If `tools.py` is not moved alongside it, or if Python
is invoked from the monorepo root rather than the `agent/` subdirectory,
this import will raise `ModuleNotFoundError: No module named 'tools'`.

**Recommended fix before the monorepo merge:**

Option A (simplest): Keep `tools.py` next to `agent.py` at all times.
The move is `agent/tools.py` alongside `agent/agent.py`. No import change
needed.

Option B (cleaner): Convert `tools.py` into a proper submodule of the
agent package:

```
agent/
├── __init__.py
├── agent.py
└── tools.py      ← same file, new location
```

Then update the import in `agent.py`:

```python
from agent.tools import BashTool, FileEditorTool, TaskTrackerTool
```

And add the monorepo root to `PYTHONPATH` in `start.sh`:

```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
python agent/agent.py ...
```

**Note:** The `reflexion/` package itself is not affected by this — it
has zero imports from `tools.py` and never imports `agent.py`. Only the
host runtime side needs attention.

## 10. Per-Session Workspace and Memory Scoping

The current setup uses a single shared workspace directory and a single
global memory file. This is fine for single-user development but
**requires explicit scoping in a multi-user hosted service**.

### Workspace scoping

Every agent session must receive a unique workspace directory. If two
sessions share the same workspace, their file operations will overwrite
each other:

```python
# In the backend server — generate per-request paths
import uuid, os
session_id = str(uuid.uuid4())
workspace_dir = f"/tmp/sessions/{session_id}/workspace"
os.makedirs(workspace_dir, exist_ok=True)

# Pass to runtime
runtime(repo_dir=workspace_dir, instruction=task, mount_dir=workspace_dir)
```

Clean up the session directory after the run completes (or on a schedule).

### Memory scoping

By default, `ReflexionMemory` writes to `reflexion/data/reflexion_memory.json`
— one global file. In a multi-user context, all users share the same
memory pool. This means:

- User A's reflection about a CSV task is retrieved for User B's CSV task
  (potentially useful, but unintended)
- Concurrent writes can corrupt the file (see `edge-cases.md` §10)

To isolate memory per session, pass a session-scoped path:

```python
memory = ReflexionMemory(f"reflexion/data/{session_id}.json")
```

To share memory across sessions for the same user (so the agent learns
from past interactions with that user specifically), use a user-scoped
path:

```python
memory = ReflexionMemory(f"reflexion/data/user-{user_id}.json")
```

The choice between session-scoped and user-scoped memory is a product
decision. The code supports both without modification — only the path
passed to `ReflexionMemory()` changes.
