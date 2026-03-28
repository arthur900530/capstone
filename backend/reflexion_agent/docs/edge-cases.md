# Edge Cases and Known Failure Modes

This document catalogs every failure we encountered during integration and
testing, organized into two sections: bugs that required code fixes (and
the lessons learned), and edge cases the code already handles gracefully.

---

## Bugs That Required Code Fixes

These were discovered during the initial integration of the Reflexion
pipeline with the OpenHands SDK v1.15 agent runtime.

### 1. Missing tool modules (`openhands.tools.*`)

**Error:**
```
ModuleNotFoundError: No module named 'openhands.tools'
```

**Root cause:** The original `agent.py` imported `TerminalTool`,
`FileEditorTool`, and `TaskTrackerTool` from `openhands.tools.*`, but
SDK v1.15 removed those pre-built tool classes entirely. Tools must now
be defined as `ToolDefinition` subclasses with a `.create()` classmethod.

**Fix:** Created `tools.py` with three custom `ToolDefinition` subclasses
(`BashTool`, `FileEditorTool`, `TaskTrackerTool`) and registered them at
startup via `register_tool()`.

**Lesson:** When upgrading the SDK, always check whether the tool module
structure has changed. The SDK's `__init__.py` exports `Tool` (a name-only
spec), not concrete tool implementations.

### 2. LLM provider not recognized by litellm

**Error:**
```
litellm.BadRequestError: LLM Provider NOT provided.
You passed model=nvidia/nemotron-3-super-120b-a12b:free
```

**Root cause:** The `MODEL` value in `.env` was set to the bare OpenRouter
model name without a provider prefix. `litellm` (used internally by the
SDK) needs the `openrouter/` prefix to know which API gateway to route to.

**Fix:** Changed `MODEL` in `.env` from `nvidia/nemotron-3-super-120b-a12b:free`
to `openrouter/nvidia/nemotron-3-super-120b-a12b:free`.

**Lesson:** Any model accessed via OpenRouter must be prefixed with
`openrouter/` in the `MODEL` variable. The same rule applies to other
litellm-supported providers (e.g. `huggingface/`, `together_ai/`).

### 3. Trajectory capture: wrong attribute path

**Error:**
```
AttributeError: 'LocalConversation' object has no attribute 'events'
```

**Root cause:** The Reflexion loop tried to access `conversation.events`,
but in SDK v1.15, the event log lives at `conversation.state.events`.
`LocalConversation` exposes a `.state` property which holds a
`ConversationState` object, and the events are on that state.

**Fix:** Changed `str(list(conversation.events))` to
`str(list(conversation.state.events))`.

**Lesson:** The `Conversation` factory returns a `LocalConversation`.
Always access events via `.state.events`, not directly on the conversation.

### 4. LLM adapter: wrong method name

**Error:**
```
AttributeError: 'LLM' object has no attribute 'call'
```

**Root cause:** The `_make_llm_call` adapter called `llm_client.call(messages)`
using raw dicts, but SDK v1.15's `LLM` class uses `.completion()` with
`Message` objects (not `.call()` with dicts).

**Fix:** Rewrote the adapter to:
1. Build `Message` and `TextContent` objects instead of raw dicts.
2. Call `llm_client.completion(messages)` instead of `llm_client.call(messages)`.
3. Extract the response text from `response.message.content` (a list of
   `TextContent`/`ThinkingBlock` items).

**Lesson:** The LLM interface is the most SDK-version-sensitive part of
the integration. When upgrading, check both the method name and the
message format.

### 5. Tools ignoring the workspace directory

**Symptom:** The agent ran commands and wrote files in `Capstone/` (the
Python process's cwd) instead of `Capstone/workspace/` (the configured
workspace). This caused the agent to see its own source code and get
confused searching for files it had supposedly created.

**Root cause:** `BashExecutor` ran `subprocess.run()` without a `cwd`
argument, and `FileEditorExecutor` resolved relative paths against the
process cwd.

**Fix:**
1. Added a `_workspace_dir(conversation)` helper that extracts
   `conversation.state.workspace.working_dir`.
2. `BashExecutor` now passes `cwd=workspace_dir` to `subprocess.run()`.
3. `FileEditorExecutor` resolves relative paths against the workspace
   directory before any file operation.

**Lesson:** Any tool executor that touches the file system must use the
workspace path from the conversation, not the Python process cwd. This
is especially important when the agent creates and then references files
within the same conversation.

---

## Edge Cases Handled Gracefully by Code

These are situations the Reflexion modules already handle without crashing.

### 6. LLM returns malformed JSON from the evaluator

**What happens:** The LLM judge returns a response that is not valid JSON,
or wraps it in markdown code fences, or includes extra commentary.

**How it's handled:** `_parse_llm_verdict()` in `evaluator.py`:
1. Strips markdown `` ``` `` fences if present.
2. Attempts `json.loads()`.
3. On any parse error (`JSONDecodeError`, `KeyError`, `ValueError`,
   `TypeError`), returns a fallback:
   ```python
   EvaluationResult(
       success=False,
       score=0.0,
       failing_step=None,
       summary=f"Evaluation parse error: {exc}",
   )
   ```

**Effect:** The pipeline treats a parse failure as a task failure, which
triggers a reflection and retry. This is the safe default — it's better
to retry than to silently declare success.

### 7. Corrupt or missing memory file

**What happens:** The `reflexion_memory.json` file is deleted, truncated,
or contains invalid JSON (e.g. from a process killed mid-write).

**How it's handled:** `ReflexionMemory._load()` in `memory.py`:
1. If the file does not exist, starts with an empty list (no error).
2. If the file exists but `json.load()` raises `JSONDecodeError`,
   `KeyError`, or `TypeError`, logs a warning and starts with an empty
   list.

**Effect:** The agent loses its memory of past reflections but continues
to function. The next successful write will create a valid file again.

### 8. No relevant reflections for a new task

**What happens:** The memory file exists and contains reflections, but
none of them are semantically related to the current task (Jaccard
similarity is 0.0 for all entries).

**How it's handled:** `format_for_prompt()` returns `None` when
`retrieve()` returns an empty list. The caller in `agent.py` checks:
```python
if past_context:
    full_instruction = past_context + "\n\n---\n\n..." + instruction
```

**Effect:** The agent receives the raw instruction without any reflection
prefix, equivalent to a first-ever attempt. No spurious or irrelevant
reflections are injected.

---

## Integration Risks for Monorepo / Hosted Service

These are **not yet bugs** in the current single-user development setup,
but will become bugs the moment the agent is hosted as a multi-user
service or merged into the monorepo. They require design decisions before
that merge happens.

### 9. SDK removed `DockerWorkspace` — tools run directly on the host machine

**Background:** openhands-sdk v1.14 and earlier used `DockerWorkspace` to
run all agent tool calls (`BashTool`, `FileEditorTool`) inside a Docker
container. The container acted as a sandbox: destructive shell commands
could only damage the container, not the host. SDK v1.15 removed
`DockerWorkspace` entirely, replacing it with `LocalWorkspace`.

**Current behavior:** `BashTool` calls `subprocess.run(command, shell=True)`.
That command executes directly on the machine running `agent.py`. There is
no sandbox, no container, and no permission boundary between the agent's
actions and the host filesystem.

**Why this is not yet a problem:** In the current setup, `agent.py` runs
on a developer's laptop for a single task at a time. The developer is also
the only user and accepts the risk.

**Why this becomes a problem in the monorepo / hosted beta:**

1. **Security.** If a user submits a task and the LLM generates a
   destructive command (e.g. `rm -rf /`, a loop that fills the disk, or
   a network request that exfiltrates data), that command runs on your
   server with the full privileges of the Python process.

2. **Multi-user isolation.** Without a per-request container, concurrent
   user sessions share the same host. User A's agent can read or overwrite
   User B's workspace files if the workspace paths are not perfectly
   isolated.

3. **Reproducibility.** Without a container, the agent's environment
   depends on whatever is installed on the host. A package present on
   one deployment but not another will produce different agent behavior.

**Recommended mitigation:** Do not add Docker inside the agent itself.
Instead, containerize the entire `agent.py` process at the deployment
layer:

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY . .
RUN pip install openhands-sdk python-dotenv pydantic
ENTRYPOINT ["python", "agent.py"]
```

For each incoming user request, your backend spins up a fresh container,
passes the task via `-i`, and discards the container when done. The agent
thinks it is running on `LocalWorkspace` — which it is, but that "local"
machine is now an ephemeral container, not the production host.

This recovers the isolation properties that `DockerWorkspace` previously
provided, without requiring any changes to the SDK or the Reflexion code.

**Per-user workspace path.** Regardless of whether you containerize,
always pass a unique workspace directory per user session (e.g.
`/tmp/session-<uuid>/workspace`). See section 10 for the memory file
equivalent.

### 10. Memory file has no file locking — concurrent writes will corrupt data

**Current behavior:** `ReflexionMemory._save()` writes the entire JSON
array to disk on every `store()` call using a plain `open(..., "w")`.
There is no file lock, no atomic rename, and no transaction.

**Why this is not yet a problem:** Only one agent process runs at a time
in the current development setup.

**Why this becomes a problem in a hosted service:** If two user requests
arrive simultaneously, two `agent.py` processes start. Both load the
memory file at startup. Both finish their first attempt and call
`memory.store()`. Both processes read the original list, append their new
entry, and write the full list back. The second write wins — the first
process's reflection is silently lost. Under heavier concurrency, entries
from multiple processes interleave unpredictably or the file ends up
containing partial JSON.

**Recommended mitigations (choose one based on scale):**

| Scale | Mitigation |
|---|---|
| PoC / low traffic | Give each user session its own memory file path (e.g. `reflexion/data/<session-id>.json`). Concurrent writes to different files are safe. |
| Multi-user production | Replace the JSON file with a database (SQLite with WAL mode, or PostgreSQL). The `ReflexionMemory` interface (`store`, `retrieve`, `clear`) is stable — only `_load`/`_save` need to change. |
| Containerized (option from §9) | Each container has its own isolated filesystem, so each user's agent writes to its own memory file with no sharing. Simple and requires zero code changes. |

**Per-session scoping in the host runtime (`agent.py`):**

```python
# Generate a unique memory path per user session
import uuid
session_id = str(uuid.uuid4())
memory = ReflexionMemory(f"reflexion/data/{session_id}.json")
```

The `reflexion/data/` directory is gitignored and auto-created, so
session files accumulate there safely. Add a cleanup job to remove old
session files if disk usage becomes a concern.
