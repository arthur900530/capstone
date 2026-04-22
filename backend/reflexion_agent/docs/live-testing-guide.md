# Live Testing Guide — Reflexion Agent (Layer 3)

This guide walks through every step required to run a live end-to-end test of
the Reflexion pipeline against a real LLM and a real local workspace.  It
captures the exact hurdles we hit during the first successful runs so future
engineers do not have to rediscover them.

For the live browser work, note one important runtime detail: in the current
`browser-use` / OpenHands stack, Docker-safe Chromium flags like `--no-sandbox`
are built into the browser profile, while custom CDP flags must be passed via
the browser tool's explicit `args` config (for example
`--remote-debugging-port=9222`) rather than a `CHROME_DOCKER_ARGS` environment
override.

---

## 1. Terminology

| Term | Meaning |
|------|---------|
| **Layer 1** | Pure unit tests — no LLM, no Docker, deterministic |
| **Layer 2** | Integration tests with mock LLM callables — no Docker |
| **Layer 3** | Live end-to-end runs — real LLM API + `LocalWorkspace` |
| **Trial** | One agent conversation from start to `finish()` |
| **Reflexion loop** | Retrying failed trials with a self-reflection injected |

---

## 2. Prerequisites

### 2.1 Python environment

All commands are run from the `capstone_frontend/backend/` directory.

```bash
cd "capstone_frontend/backend"
```

The project uses the shared Anaconda environment.  Verify your Python path:

```bash
which python   # should resolve to /opt/anaconda3/bin/python or similar
python --version   # must be 3.12+
```

Install dependencies (one-time):

```bash
pip install openhands-sdk litellm python-dotenv pytest
```

### 2.2 `config.py`

`config.py` is gitignored because it holds live API keys.  Create it by copying
the example file:

```bash
cp config.py.example config.py
```

Then open `config.py` and fill in your values:

```python
BASE_URL = "https://openrouter.ai/api/v1"      # or any OpenAI-compatible endpoint
API_KEY  = "sk-or-v1-..."                       # your OpenRouter or provider key
AGENT_MODEL = "openrouter/minimax/minimax-m2.7" # model used by the agent
SKILL_MODEL = "google/gemini-2.5-flash"         # model used for skill extraction
```

> **Note:** Both `BASE_URL` and `API_KEY` must be present.  If either is
> missing or blank, `_make_llm_call()` in `agent.py` will raise a
> `ValueError` at startup.

### 2.3 Docker

The OpenHands SDK executes the agent inside a managed environment.  Docker must
be running **before** you start a live test.

1. **Start Docker Desktop** on your Mac (click the whale icon in the menu bar,
   wait for the status to show "Docker Desktop is running").

2. **Pull the agent server image** (one-time, ~1–2 GB download):

   ```bash
   docker pull ghcr.io/openhands/agent-server:latest-python
   ```

   Verify the image is present:

   ```bash
   docker images | grep agent-server
   ```

   You should see a line like:

   ```
   ghcr.io/openhands/agent-server   latest-python   abc123...   ...
   ```

> **Important:** The pull command must be run in your **Mac's system
> terminal** (Terminal.app or iTerm2), not inside the IDE's integrated
> terminal, because the IDE terminal may not share Docker Desktop's
> socket context.  Once the image is pulled you can use either terminal
> for subsequent runs.

### 2.4 Scratch workspace

Each live run needs a fresh directory for the agent to write files into.
Create a reusable scratch location:

```bash
mkdir -p /tmp/reflexion-test-workspace
```

To start a run with a completely clean slate, wipe and recreate it:

```bash
rm -rf /tmp/reflexion-test-workspace && mkdir /tmp/reflexion-test-workspace
```

---

## 3. SDK version note — `LocalWorkspace` vs `DockerWorkspace`

The original `agent.py` imported `DockerWorkspace` from `openhands.workspace`.
**This module no longer exists in `openhands-sdk` v1.15+.**

The fix (already applied to the current `agent.py`) switches to:

```python
from openhands.sdk.workspace import LocalWorkspace
```

and uses:

```python
working_dir = abs_mount if mount_dir else repo_dir or "."
with LocalWorkspace(working_dir=working_dir) as workspace:
    ...
```

`LocalWorkspace` runs the agent process directly on the host machine using the
current Python interpreter.  Docker is still required for full isolation if the
SDK uses it internally, but the explicit `DockerWorkspace` wrapper is gone.

If you ever see:

```
ModuleNotFoundError: No module named 'openhands.workspace'
```

check `agent.py` line 21 — ensure the import reads `openhands.sdk.workspace`,
not `openhands.workspace`.

---

## 4. Running the unit and integration tests first (Layers 1 & 2)

Always verify the fast tests pass before spending time on a live run:

```bash
cd "capstone_frontend/backend"
PYTHONPATH=. pytest reflexion_agent/tests/test_reflexion_fixes.py -v
```

Expected output: **34 passed** in under one second.  If any fail, fix them
before proceeding — a broken unit test means the live run will also fail.

---

## 5. Running a live test (Layer 3)

### 5.1 Basic command pattern

```bash
cd "capstone_frontend/backend"

LOGLEVEL=DEBUG \
ENABLE_REFLEXION=true \
REFLEXION_SCORE_THRESHOLD=0.75 \
MAX_REFLEXION_ATTEMPTS=3 \
PYTHONPATH=. \
python -c "
import logging, sys

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)-8s %(name)s: %(message)s',
    stream=sys.stdout,
)

from reflexion_agent.agent import runtime
runtime(
    repo_dir='/tmp/reflexion-test-workspace',
    instruction='YOUR TASK HERE',
    mount_dir='/tmp/reflexion-test-workspace',
    use_reflexion=True,
)
" 2>&1 | tee reflexion_agent/tests/my_run.log
```

Replace `YOUR TASK HERE` with the task string.  The `tee` command streams
output to the terminal in real time **and** saves it to a log file.

### 5.2 Key environment variables

| Variable | Value in tests | Effect |
|----------|---------------|--------|
| `LOGLEVEL=DEBUG` | `DEBUG` | Enables verbose `[trajectory]`, `[evaluator]`, `[reflexion gate]` log lines |
| `ENABLE_REFLEXION` | `true` | Activates the retry loop; without this reflexion is skipped regardless of score |
| `REFLEXION_SCORE_THRESHOLD` | `0.75`–`0.95` | Score below which a non-success trial is retried. Raise to `0.95` to make reflexion trigger more easily |
| `MAX_REFLEXION_ATTEMPTS` | `3`–`4` | Maximum number of trials before giving up |
| `PYTHONPATH=.` | `.` | Required so that `from reflexion_agent.agent import runtime` resolves correctly |

### 5.3 Reading the log output

A successful single-trial run ends with lines like:

```
INFO  reflexion_agent.agent: [trajectory] Serialized 16 events — message=0 action=7 observation=7 error=0 other=2
INFO  reflexion_agent.evaluator: [evaluator] Sending trajectory (4967 chars) to judge ...
INFO  reflexion_agent.evaluator: [evaluator] Parsed result: success=True score=1.00 failing_step=None
INFO  reflexion_agent.agent: Attempt 1 result: success=True score=1.00 threshold=0.75 task=05e0740a
INFO  reflexion_agent.agent: [reflexion gate] Stopping — judge marked success=True (attempt=1 ...)
```

A run that triggers the reflexion path shows:

```
INFO  reflexion_agent.agent: Attempt 1 result: success=False score=0.40 threshold=0.75 task=...
INFO  reflexion_agent.agent: [reflexion] Generating reflection for attempt 1 ...
INFO  reflexion_agent.reflector: [reflector] Input critique: "The agent failed to ..."
INFO  reflexion_agent.agent: [reflexion] Injecting reflection into attempt 2 prompt
INFO  reflexion_agent.agent: Attempt 2 result: success=True score=0.90 threshold=0.75 task=...
INFO  reflexion_agent.agent: [reflexion gate] Stopping — judge marked success=True (attempt=2 ...)
```

### 5.4 Confirming which fixes fired

| Log signature | Fix verified |
|--------------|-------------|
| `[trajectory] Serialized N events` | Fix 3 — `_serialize_trajectory` |
| `[evaluator] Parsed result: success=True score=1.00` | Fix 2 — labeled-line parsing |
| `[reflexion gate] Stopping — judge marked success=True` | Fix 5 — success-flag gate |
| `score=0.XX threshold=0.75` and loop exits early | Fix 1 — score gate |
| `[reflexion] Generating reflection` | Fix 6 — `generate_reflection` called |
| `[reflexion] Injecting reflection into attempt N prompt` | Fix 7 — numbered reflections injected |

---

## 6. Completed live runs (reference)

### Run 1 — Hello World (`layer3_hello_world_run.log`)

```
Task:       Create a Python file called hello.py that prints "Hello, World!"
Duration:   19 seconds
Trials:     1
Result:     success=True, score=1.00
Fixes hit:  1, 2, 3, 5
```

### Run 2 — Porsche Analysis (`layer3_porsche_analysis_run.log`)

```
Task:       Research Porsche's 2025 financial plan and write a detailed analysis
Duration:   159 seconds
Trials:     1
Result:     success=True, score=0.75
Fixes hit:  1, 2, 3, 4 (indirectly), 5
Notes:      Score landed exactly at the threshold (0.75).  Score gate stopped
            the loop; success=True prevented reflexion from triggering.
Artifact:   layer3_porsche_analysis_output.md
```

### Run 3 — Data Pipeline (`not saved as separate log`)

```
Task:       Generate a CSV with 20 employee rows, compute HR stats, write hr_report.md
Duration:   55 seconds
Trials:     1
Result:     success=True, score=1.00
```

### Run 4 — Red-Black Tree (`layer3_rbtree_run.log`)

```
Task:       Implement a full Red-Black Tree (insert, delete, search) from scratch;
            all 23 pytest tests must pass
Duration:   43+ minutes (trial terminated at ~6.7M token context limit)
Trials:     1 (never reached finish())
Result:     Trial stalled — evaluator never ran
Notes:      The agent correctly implemented insertion and search but had two
            deletion-fixup bugs.  It spent the entire trial debugging them,
            correctly identified the root cause ("delete_fixup: NIL.color 1→0"),
            but ran out of per-conversation token budget before applying the fix.
            The two-line fix was applied manually; 23/23 tests then passed.
Artifacts:  layer3_rbtree_run.log, layer3_rbtree_output.py,
            layer3_rbtree_test_suite.py, layer3_rbtree_run_summary.md
```

---

## 7. Why reflexion is hard to trigger against a frontier model

The reflexion loop fires **only when both conditions are true**:

```
success == False   AND   score < REFLEXION_SCORE_THRESHOLD
```

A frontier-class LLM (e.g. Claude 3.5 Sonnet, GPT-4o, Gemini 2.5) tends to:

1. Solve well-defined tasks correctly in one pass.
2. When tests fail, loop internally (edit → run → fix) until they pass, *all
   within the same trial*, then call `finish()` with a passing implementation.

As a result the evaluator always sees a clean success and reflexion never fires.

### 7.1 Strategies that do NOT reliably trigger reflexion

- Tasks with clear specifications (the model reads the spec and implements it)
- Debugging tasks where bugs are labeled (model spots them by inspection)
- Algorithmic tasks with specific test vectors (model runs the tests and fixes
  failures within a single trial)

### 7.2 Strategies more likely to trigger reflexion

| Strategy | Reasoning |
|----------|-----------|
| Raise `REFLEXION_SCORE_THRESHOLD` to `0.90`–`0.95` | Forces reflexion when the agent partially succeeds |
| Tasks requiring real-time external data (web, stock prices) | Agent cannot verify claims; evaluator may give low score |
| Tasks where the first-attempt output must match an exact format checked by a validator script pre-seeded in the workspace | Any formatting deviation causes a test failure the model submits without fixing |
| Multi-agent coordination tasks where one agent must produce output consumed by another | Mismatched interfaces surface only at integration time |

### 7.3 The correct way to verify the reflexion path without relying on a live failure

Run the **Layer 2 integration tests**, which inject mock LLM responses:

```bash
PYTHONPATH=. pytest reflexion_agent/tests/test_reflexion_fixes.py \
    -v -k "Layer2" -s 2>&1
```

These deterministically exercise every branch of the loop (score gate exit,
score gate continue, reflection injection, accumulation of numbered reflections)
without needing a real LLM or Docker.

---

## 8. Saving run artifacts

By convention, all Layer 3 artifacts live in `reflexion_agent/tests/`:

| File naming pattern | Contents |
|---------------------|----------|
| `layer3_<name>_run.log` | Full terminal output (captured with `tee`) |
| `layer3_<name>_output.*` | Files produced by the agent (reports, scripts, etc.) |
| `layer3_<name>_run_summary.md` | Human-readable post-run analysis |

Log files are **gitignored** (they can be hundreds of megabytes for long runs).
Output artifacts and summary markdown files are committed so reviewers can
inspect results without re-running.

To add a new gitignore rule:

```bash
echo "reflexion_agent/tests/*.log" >> .gitignore
```

---

## 9. Common errors and fixes

### `ModuleNotFoundError: No module named 'openhands.workspace'`

**Cause:** `agent.py` still imports the old `DockerWorkspace` path.

**Fix:**
```python
# Change line 21 of agent.py from:
from openhands.workspace import DockerWorkspace
# to:
from openhands.sdk.workspace import LocalWorkspace
```

Also update `conftest.py` to stub the new path:

```python
try:
    from openhands.sdk.workspace import LocalWorkspace
except (ImportError, ModuleNotFoundError):
    _create_stub_module("openhands.sdk.workspace", LocalWorkspace=None)
```

---

### `ModuleNotFoundError: No module named 'config'`

**Cause:** `config.py` does not exist or Python is not run from the right
directory.

**Fix:** Ensure `config.py` exists (copy from `config.py.example`) and that
`PYTHONPATH=.` is set so Python can find it:

```bash
PYTHONPATH=. python -c "from reflexion_agent.agent import runtime"
```

---

### `AssertionError` or `ImportError` in unit tests after changing `agent.py`

**Cause:** `conftest.py` stubs may be out of sync with the new import paths.

**Fix:** Open `reflexion_agent/tests/conftest.py` and verify that every
`_create_stub_module(...)` call matches the import paths currently used in
`agent.py`.

---

### Live run hangs indefinitely with no output

**Cause:** Docker Desktop is not running, or the agent server image was not
pulled.

**Fix:**
1. Start Docker Desktop and wait for "Docker Desktop is running".
2. Pull the image: `docker pull ghcr.io/openhands/agent-server:latest-python`
3. Re-run the test.

---

### Live run finishes but `[reflexion gate]` log line never appears

**Cause:** `ENABLE_REFLEXION` is not set to `true`, or `use_reflexion=False`
was passed to `runtime()`.

**Fix:** Add `ENABLE_REFLEXION=true` to the environment and `use_reflexion=True`
to the `runtime()` call, or set them in your `.env` file at
`capstone_frontend/backend/.env`.

---

### Score is always `1.00` and reflexion never triggers

**Cause:** The task is too easy for the model.  See §7.

**Fix:** Raise `REFLEXION_SCORE_THRESHOLD` to `0.90` and use a task that
involves real-time data or strict format verification.  Alternatively, run
Layer 2 tests to exercise the reflexion path deterministically.

---

## 10. Quick-reference cheat sheet

```bash
# ── Prerequisite checks ──────────────────────────────────────────────────
docker info | head -5                          # confirm Docker is running
docker images | grep agent-server              # confirm image is pulled
ls capstone_frontend/backend/config.py         # confirm config exists

# ── Wipe workspace ───────────────────────────────────────────────────────
rm -rf /tmp/reflexion-test-workspace && mkdir /tmp/reflexion-test-workspace

# ── Fast tests (always run before a live test) ───────────────────────────
cd capstone_frontend/backend
PYTHONPATH=. pytest reflexion_agent/tests/test_reflexion_fixes.py -v

# ── Live run template ────────────────────────────────────────────────────
LOGLEVEL=DEBUG \
ENABLE_REFLEXION=true \
REFLEXION_SCORE_THRESHOLD=0.75 \
MAX_REFLEXION_ATTEMPTS=3 \
PYTHONPATH=. \
python -c "
import logging, sys
logging.basicConfig(level=logging.DEBUG,
    format='%(asctime)s %(levelname)-8s %(name)s: %(message)s',
    stream=sys.stdout)
from reflexion_agent.agent import runtime
runtime(
    repo_dir='/tmp/reflexion-test-workspace',
    instruction='YOUR TASK HERE',
    mount_dir='/tmp/reflexion-test-workspace',
    use_reflexion=True,
)
" 2>&1 | tee reflexion_agent/tests/my_run.log

# ── Exercise reflexion path deterministically (no LLM needed) ────────────
PYTHONPATH=. pytest reflexion_agent/tests/test_reflexion_fixes.py \
    -v -k "Layer2" -s
```
