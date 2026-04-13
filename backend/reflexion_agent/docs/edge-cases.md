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

### 3. Trajectory capture: wrong attribute path, then repr format

**Error:**
```
AttributeError: 'LocalConversation' object has no attribute 'events'
```

**Root cause:** The Reflexion loop tried to access `conversation.events`,
but in SDK v1.15, the event log lives at `conversation.state.events`.
`LocalConversation` exposes a `.state` property which holds a
`ConversationState` object, and the events are on that state.

**Fix (phase 1):** Changed `str(list(conversation.events))` to
`str(list(conversation.state.events))`.

**Further fix (phase 2):** The resulting `str(list(...))` produced a Python
repr dump of SDK objects (e.g. `MessageEvent(role='user', content=[...])`)
that the LLM judge had to parse as Python notation. This was fragile: if the
SDK renamed a class, the format changed silently. Replaced with
`_serialize_trajectory(conversation.state.events)`, a purpose-built function
that emits a labeled human-readable transcript (`[USER]`, `[Turn N] [ACTION]`,
`[OBSERVATION]`, etc.) using duck-typing attribute checks so it remains SDK-
version-agnostic.

**Lesson:** The `Conversation` factory returns a `LocalConversation`.
Always access events via `.state.events`. Always pass the result through
a structured serializer rather than relying on Python repr notation.

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

### 6. LLM returns a malformed or missing field in the evaluator response

**Previous behavior (JSON era — now replaced):** The evaluator asked the LLM
for strict JSON. If any field was missing or the response was wrapped in
markdown fences, `json.loads()` raised an exception and the entire result
collapsed to `EvaluationResult(success=False, score=0.0, ...)`. A score of
`0.0` looked like a total task failure to the loop, causing the pipeline to
over-trigger reflections and retries even when the agent had done a good job
and the judge simply produced slightly malformed output.

**Current behavior (labeled-line format):** The evaluator now instructs the LLM
to reply with four labeled plain-text lines. `_parse_llm_verdict()` extracts
each field with its own regex so a missing or malformed field only affects
that one field — never the entire result:

| Situation | Effect |
|---|---|
| `SCORE:` line missing | `score = 0.5` (neutral — no retry bias) |
| `SUCCESS:` line missing | `success = False` (conservative — assume failure) |
| `FAILING_STEP: none` or `N/A` | `failing_step = None` (string normalized to Python None) |
| `SUMMARY:` line missing | `summary` = placeholder string; logged as WARNING |
| Entire response is garbled | All four field defaults applied; three WARNINGs emitted |
| Score outside `[0.0, 1.0]` | Clamped to `0.0` or `1.0`; logged as WARNING |
| Score has leading minus (e.g. `-0.3`) | Regex doesn't match; treated as missing → `0.5` |

**Why `SCORE` defaults to `0.5` (not `0.0`):** A neutral score doesn't push
the score gate in either direction. `0.0` caused all judge format errors to
look like total failures and force retries. `0.5` is below the default `0.75`
threshold, so the loop still continues on a genuine failure — but it no longer
incorrectly penalizes the agent for the judge's formatting slip.

**Log signatures to watch:**
```
WARNING reflexion_agent.evaluator: [evaluator parse] SCORE field missing or unreadable — defaulting to 0.5 (neutral)
WARNING reflexion_agent.evaluator: [evaluator parse] SUCCESS field missing or unreadable — defaulting to False
DEBUG   reflexion_agent.evaluator: [evaluator parse] SUCCESS=True (from response)
DEBUG   reflexion_agent.evaluator: [evaluator parse] SCORE=0.92 (from response)
```

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

## Over-Triggering Fixes (April 2026)

The following edge cases were identified after observing the Reflexion loop
retrying tasks that the agent had actually completed well. Seven targeted fixes
were applied across `evaluator.py`, `agent.py`, and `reflector.py`.

### Score escape hatch (Fix 1 — `agent.py`)

**Problem:** The loop only stopped when `evaluation.success is True`. A high-
quality partial result (e.g. `success=False, score=0.85`) was retried just as
aggressively as a genuine failure (`success=False, score=0.1`).

**Fix:** Added a second stop condition in `_run_with_reflexion`. If
`evaluation.score >= REFLEXION_SCORE_THRESHOLD` (default `0.75`), the loop
exits even when `success=False`. Log signature:
```
[reflexion gate] Stopping — score 0.80 >= threshold 0.75 despite success=False
```
Set `REFLEXION_SCORE_THRESHOLD=1.0` to disable the escape hatch and require
an explicit `success=True` verdict.

### Labeled-line evaluator prompt and per-field parser (Fixes 2 & 4 — `evaluator.py`)

See §6 above for the full parse behavior. The evaluator system prompt was also
rewritten with five named evaluation dimensions and a scoring guide so the
judge has calibrated anchors rather than choosing scores by intuition.

### Human-readable trajectory serializer (Fix 3 — `agent.py`)

See §3 above. Replaced `str(list(conversation.state.events))` with
`_serialize_trajectory()`.

### Fresh agent per attempt (Fix 5 — `agent.py`)

**Problem:** The same `Agent` object was reused across retry attempts. SDK
internal state (cached completions, mutable agent fields) could leak from one
attempt into the next, making the second attempt's behavior dependent on the
first attempt's residual state in unpredictable ways.

**Fix:** `_create_agent(llm, agent_context)` is now called once per attempt
inside `_run_with_reflexion`. Log signature:
```
[reflexion] Created fresh Agent for attempt 2 (task=abc12345)
```

### Reflector receives critique string only (Fix 6 — `reflector.py`)

**Problem:** `generate_reflection()` previously accepted the full
`EvaluationResult` object (including numeric score and boolean flag). This
mixed gating logic and reflection logic: the reflector was making decisions
based on data it didn't need.

**Fix:** The function signature now accepts `critique: str` — only the
evaluator's summary sentence. The caller in `agent.py` passes
`critique=evaluation.summary`. The reflector prompt contains a `CRITIQUE:`
section with this string; it never sees `score` or `success`.

### Numbered in-session reflections (Fix 7 — `agent.py`)

**Problem:** The previous implementation injected a flat unordered list of
reflections into the next attempt. There was no indication of trial order or
how the agent's strategy had evolved.

**Fix:** `_format_numbered_reflections(session_reflections)` produces labeled
trial blocks (`--- Trial 1 ---`, `--- Trial 2 ---`, ...) prepended to the next
attempt's prompt. Each label gives the agent a clear sense of progression and
helps it avoid simply repeating the same reflection.

---

## Test Suite

All seven fixes above are covered by an automated test suite at:

```
reflexion_agent/tests/test_reflexion_fixes.py
```

Run it with:

```bash
cd capstone_frontend/backend
PYTHONPATH=. pytest reflexion_agent/tests/test_reflexion_fixes.py -v
```

For full log output showing data flow through each component:

```bash
PYTHONPATH=. pytest reflexion_agent/tests/test_reflexion_fixes.py -v -s --log-cli-level=INFO
```

**Test coverage by layer:**

| Layer | Scope | Tests |
|---|---|---|
| Layer 1 | Unit tests for pure functions (no LLM, no network) | 29 tests across 5 function groups |
| Layer 2 | Integration tests with mock LLM callables | 5 tests exercising the full evaluation-reflect-format pipeline |
| Layer 3 | Live end-to-end runs logged to `reflexion_agent/tests/layer3_*.log` | 2 runs: simple (`hello.py`) and complex (Porsche financial analysis) |

Layer 3 artifacts:
- `layer3_hello_world_run.log` — 19-second simple task; score=1.00 on attempt 1
- `layer3_porsche_analysis_run.log` — 159-second research task; score=0.75 on attempt 1
- `layer3_porsche_analysis_output.md` — 209-line analysis report produced by the agent

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
