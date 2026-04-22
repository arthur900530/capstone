"""
Backend for the Agent.

Supports two modes controlled by environment:
  - Mock mode (default): simulates agent behavior with realistic SSE streaming.
  - Real agent mode: runs the OpenHands agent in Docker, streaming live events.

Set MODEL, API_KEY, and BASE_URL in .env to enable the real agent.

Run:  uvicorn server:app --reload --port 8000
"""

from __future__ import annotations

import csv
import os
import sys
import asyncio
import json
import logging
import random
import re
import shutil
import tempfile
import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import dotenv
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from skills_ingestor.mm_train import MMSkillTrainer

dotenv.load_dotenv()

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in ("1", "true", "yes")

# ---------------------------------------------------------------------------
# Real-agent feature flag
# ---------------------------------------------------------------------------
REAL_AGENT_ENABLED = True
ENABLE_BROWSER_LIVE = _env_bool("ENABLE_BROWSER_LIVE", "true")

_agent_import_error: str | None = None
if REAL_AGENT_ENABLED:
    try:
        from reflexion_agent.agent import runtime as _agent_runtime
        from reflexion_agent.agent import build_workspace as _build_workspace
        from openhands.sdk.event import (
            ActionEvent,
            ObservationEvent,
            MessageEvent,
            AgentErrorEvent,
        )
        from openhands.sdk.event.conversation_error import ConversationErrorEvent
    except ImportError as exc:
        _agent_import_error = str(exc)
        REAL_AGENT_ENABLED = False

if REAL_AGENT_ENABLED:
    logger.info("Real agent mode ENABLED (model=%s)", os.getenv("MODEL"))
elif _agent_import_error:
    logger.warning("Real agent mode DISABLED — import error: %s", _agent_import_error)
else:
    logger.info("Real agent mode DISABLED — MODEL/API_KEY env vars not set")

from contextlib import asynccontextmanager

from config import AGENT_MODEL
from db.engine import engine
from db.seed import seed_from_filesystem
from routers.skills import router as skills_router
from routers.marketplace import router as marketplace_router
from routers.submissions import router as submissions_router
from routers.employees import router as employees_router


# ---------------------------------------------------------------------------
# Shared DockerWorkspace
# ---------------------------------------------------------------------------
# A single DockerWorkspace is started at server boot with its bind mount
# pointing at a neutral scratch directory on the host (``_SHARED_WS["host_dir"]``).
# Sessions never bind-mount their own directories; instead, at session-swap
# time we (1) sync the current owner's changes back to their original
# ``mount_dir`` on the host, (2) wipe the shared bind mount, and (3) copy
# the incoming session's files in. Within a single session, no copying
# happens between turns — the container and its /workspace contents are
# reused as-is, so every turn after the first is instant.
#
# The tradeoffs (spelled out so the next reader isn't surprised):
#   - Only one agent runs at a time; ``_SHARED_WS["lock"]`` serializes them.
#   - The user's ``mount_dir`` on disk is not live: changes are synced back
#     after each turn of the owning session, and again on eviction.
#   - Hidden top-level dirs (``.agents``, ``.openhands``) are excluded from
#     sync-back to avoid polluting the user's project with agent-internal
#     scaffolding. They still live inside /workspace during the run.

_SHARED_WS: dict[str, Any] = {
    "workspace": None,       # DockerWorkspace instance (entered via __enter__)
    "host_dir": None,        # str: host path bind-mounted at /workspace
    "lock": None,            # asyncio.Lock — serializes session access
    "current_owner": None,   # dict or None — see _prime_shared_workspace
}


@asynccontextmanager
async def lifespan(application):
    """Start DB engine, seed skills, and warm the shared DockerWorkspace."""
    from routers.skills import set_db_available
    from routers.employees import set_db_available as set_emp_db
    try:
        from alembic.config import Config
        from alembic import command
        alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "alembic.ini"))
        await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
        await seed_from_filesystem()
        set_db_available(True)
        set_emp_db(True)
        logger.info("Database initialized and seeded.")
    except Exception as exc:
        set_db_available(False)
        set_emp_db(False)
        logger.warning("DB init skipped — falling back to in-memory skills: %s", exc)

    # Warm the shared DockerWorkspace once, before accepting requests.
    if REAL_AGENT_ENABLED:
        host_dir = tempfile.mkdtemp(prefix="shared_ws_")
        logger.info("Starting shared DockerWorkspace (host_dir=%s) …", host_dir)
        workspace = None
        last_exc: Exception | None = None
        # Retry a few times: a freshly-chosen host port may race with another
        # container / process coming up on the same port. On each retry
        # _find_port picks a new one.
        for attempt in range(1, 4):
            try:
                workspace = await asyncio.to_thread(_start_shared_workspace, host_dir)
                break
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Shared DockerWorkspace start attempt %d/3 failed: %s",
                    attempt, exc,
                )
        if workspace is not None:
            _SHARED_WS["host_dir"] = host_dir
            _SHARED_WS["workspace"] = workspace
            _SHARED_WS["lock"] = asyncio.Lock()
            _SHARED_WS["current_owner"] = None
            logger.info("Shared DockerWorkspace ready — bind mount %s:/workspace", host_dir)
        else:
            logger.error(
                "Failed to start shared DockerWorkspace after 3 attempts; real agent disabled. "
                "Check for stale containers: `docker ps -a | rg openhands/agent-server`. "
                "Last error: %s",
                last_exc,
            )
            shutil.rmtree(host_dir, ignore_errors=True)
            _SHARED_WS["workspace"] = None
            _SHARED_WS["host_dir"] = None
            _SHARED_WS["lock"] = None

    yield

    if _SHARED_WS.get("workspace") is not None:
        try:
            await asyncio.to_thread(_evict_current_owner_sync)
            await asyncio.to_thread(
                _SHARED_WS["workspace"].__exit__, None, None, None
            )
        except Exception:
            logger.exception("Error while tearing down shared DockerWorkspace")
        finally:
            host_dir = _SHARED_WS.get("host_dir")
            if host_dir and os.path.isdir(host_dir):
                shutil.rmtree(host_dir, ignore_errors=True)
            _SHARED_WS["workspace"] = None
            _SHARED_WS["host_dir"] = None

    try:
        await engine.dispose()
    except Exception:
        pass


def _start_shared_workspace(host_dir: str):
    """Synchronous helper: build the workspace and enter its context."""
    ws = _build_workspace(mount_host_dir=host_dir)
    return ws.__enter__()


def _workspace_novnc_port() -> int | None:
    workspace = _SHARED_WS.get("workspace")
    if workspace is None:
        return None
    return getattr(workspace, "novnc_host_port", None)


app = FastAPI(title="Digital Employee Platform API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(skills_router)
app.include_router(marketplace_router)
app.include_router(submissions_router)
app.include_router(employees_router)


_chats: dict[str, dict] = {}
_upload_dirs: dict[str, str] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Registry of agent profiles surfaced by /api/agents and consumed by
# _resolve_agent. The ``model`` field here is a historical/display value;
# the reflexion runtime always calls ``config.AGENT_MODEL``, and callers
# stamp that real model onto the returned profile (see _resolve_agent).
_AGENTS: dict[str, dict] = {
    "agent-gpt5.4-full": {
        "id": "agent-gpt5.4-full",
        "name": "Equity Research Analyst",
        "model": "openai/gpt-5.4",
        "skills": ["web_search", "edgar_search", "parse_html", "retrieve_info"],
    },
    "agent-gpt5.4-web": {
        "id": "agent-gpt5.4-web",
        "name": "Market Intelligence Associate",
        "model": "openai/gpt-5.4",
        "skills": ["web_search", "parse_html", "retrieve_info"],
    },
    "agent-conversational": {
        "id": "agent-conversational",
        "name": "Financial Advisor Assistant",
        "model": "openai/gpt-5.4",
        "skills": [],
    },
}

_DEFAULT_TASK_AGENT = "agent-gpt5.4-full"
_DEFAULT_CHAT_AGENT = "agent-conversational"


def _resolve_agent(model: str | None, is_task: bool = True) -> dict:
    """Pick the best matching agent profile and stamp it with the REAL model
    that the runtime will actually call.

    The `_AGENTS` registry carries historical/display model strings, but the
    reflexion runtime always uses ``config.AGENT_MODEL``. To keep the UI
    honest we clone the selected profile and overwrite its ``model`` field
    with ``AGENT_MODEL`` before returning.
    """
    if model:
        for agent in _AGENTS.values():
            if agent["model"] == model and (bool(agent["skills"]) == is_task):
                return {**agent, "model": AGENT_MODEL}
    default_id = _DEFAULT_TASK_AGENT if is_task else _DEFAULT_CHAT_AGENT
    base = _AGENTS.get(default_id)
    if base is None:
        raise HTTPException(
            status_code=500,
            detail=f"Default agent '{default_id}' is not registered.",
        )
    return {**base, "model": AGENT_MODEL}


_SKILLS_DIR = os.path.join(os.path.dirname(__file__), "skills")


def _load_skills_from_disk() -> dict[str, dict]:
    """Scan ./skills/ and return a dict of skill objects keyed by id."""
    skills: dict[str, dict] = {}
    if not os.path.isdir(_SKILLS_DIR):
        return skills
    for skill in os.listdir(_SKILLS_DIR):
        skill_path = os.path.join(_SKILLS_DIR, skill)
        skill_md = os.path.join(skill_path, "SKILL.md")
        if not os.path.isdir(skill_path) or not os.path.isfile(skill_md):
            continue
        fs = []
        for _root, _dirs, filenames in os.walk(skill_path):
            for fname in filenames:
                # Capture only the file structure relative to that skill
                fpath_relative = os.path.relpath(_root, skill_path)
                fpath_relative = os.path.join(fpath_relative, fname)
                fpath = os.path.join(_root, fname)
                fs.append({"name": fpath_relative, "size": os.path.getsize(fpath), "type": mimetypes.guess_type(fpath)[0]})
        skill_type = "user" if skill.startswith("user_") else "builtin"
        definition = open(skill_md).read()
        fm = re.search(r'^name:\s*["\']?([^\n"\']+)["\']?', definition, re.MULTILINE)
        if fm:
            display_name = fm.group(1).strip()
        elif skill_type == "user":
            display_name = "_".join(skill.split("_")[1:-1]).replace("_", " ").title()
        else:
            display_name = " ".join(word.capitalize() for word in skill.split("-"))
        skills[skill] = {
            "id": skill,
            "name": display_name,
            "description": "Placeholder description for the skill",
            "type": skill_type,
            "files": fs,
            "definition": definition,
            "created_at": os.path.getctime(skill_md),
            "updated_at": os.path.getmtime(skill_md),
        }
    return skills



def _load_file_contents_from_disk() -> dict[str, dict[str, str]]:
    """Scan ./skills/ and return a dict of file contents keyed by skill id and file path."""
    file_contents: dict[str, dict[str, str]] = {}
    for skill in _SKILLS.values():
        if skill["id"] not in file_contents:
            file_contents[skill["id"]] = {}
        for file in skill["files"]:
            fpath = os.path.join(_SKILLS_DIR, skill["id"], file["name"])
            file_contents[skill["id"]][file["name"]] = open(fpath).read()
    return file_contents


_SKILLS: dict[str, dict] = _load_skills_from_disk()
_FILE_CONTENTS: dict[str, dict[str, str]] = _load_file_contents_from_disk()
        

_COMPANY_PATTERNS = re.compile(
    r"\b(Apple|Google|Alphabet|Microsoft|Tesla|Amazon|Meta|Facebook|Netflix|Nvidia"
    r"|AMD|Intel|IBM|Oracle|Salesforce|Adobe|Uber|Lyft|Snap|Twitter|X Corp"
    r"|JPMorgan|Goldman Sachs|Morgan Stanley|Bank of America|Citigroup"
    r"|Berkshire Hathaway|Visa|Mastercard|PayPal|Square|Block"
    r"|Pfizer|Moderna|Johnson & Johnson|UnitedHealth"
    r"|Coca-Cola|PepsiCo|McDonald's|Walmart|Costco|Target)\b",
    re.IGNORECASE,
)


def _generate_chat_name(question: str) -> str:
    """Derive a short chat title from the first user message."""
    company = _COMPANY_PATTERNS.search(question)
    q = question.strip().rstrip("?!.")

    if company:
        name = company.group(0)
        lower = q.lower()
        if "revenue" in lower or "earnings" in lower:
            return f"{name} Revenue & Earnings"
        if "stock" in lower or "share price" in lower or "market cap" in lower:
            return f"{name} Stock Analysis"
        if "10-k" in lower or "10-q" in lower or "sec" in lower or "filing" in lower:
            return f"{name} SEC Filing Review"
        if "dividend" in lower:
            return f"{name} Dividend Info"
        return f"{name} Financial Overview"

    words = q.split()
    if len(words) <= 6:
        return q[:50]
    return " ".join(words[:6])[:50]


def _upsert_chat(
    session_id: str,
    question: str,
    role: str = "user",
    agent_id: str | None = None,
    files: list[dict] | None = None,
) -> dict:
    """Create a chat entry on first message, or append to existing one."""
    now = _now_iso()
    if session_id not in _chats:
        _chats[session_id] = {
            "id": session_id,
            "name": _generate_chat_name(question),
            "agent_id": agent_id,
            "created_at": now,
            "updated_at": now,
            "files": [],
            "messages": [],
        }
    chat = _chats[session_id]
    chat["updated_at"] = now
    if files:
        chat["files"].extend(files)
    chat["messages"].append({"role": role, "type": "user", "content": question, "timestamp": now})
    return chat


def _append_event(session_id: str, event_type: str, data: dict):
    """Persist an SSE event so the full trajectory can be restored later."""
    if session_id not in _chats:
        return
    msg = {"role": "assistant", "type": event_type, "timestamp": _now_iso()}
    msg.update(data)
    _chats[session_id]["messages"].append(msg)
    _chats[session_id]["updated_at"] = _now_iso()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sse(event_type: str, data: dict[str, Any]) -> dict:
    return {"event": event_type, "data": json.dumps(data)}


# ---------------------------------------------------------------------------
# Mock data pools — randomly sampled to keep responses varied
# ---------------------------------------------------------------------------

_TOOL_SEQUENCES = [
    [
        {"tool": "web_search", "detail": "searching: {query_short}"},
        {"tool": "parse_html", "detail": "Reading financial article…"},
        {"tool": "retrieve_info", "detail": "Extracting key figures from parsed documents"},
        {"tool": "submit_result", "detail": "Submitting answer"},
    ],
    [
        {"tool": "edgar_search", "detail": "Searching SEC EDGAR for {query_short}"},
        {"tool": "parse_html", "detail": "Parsing SEC filing document…"},
        {"tool": "web_search", "detail": "Cross-referencing with recent news"},
        {"tool": "retrieve_info", "detail": "Analyzing collected data"},
        {"tool": "submit_result", "detail": "Submitting answer"},
    ],
    [
        {"tool": "web_search", "detail": "searching: {query_short}"},
        {"tool": "web_search", "detail": "searching: related financial data"},
        {"tool": "parse_html", "detail": "Reading earnings report…"},
        {"tool": "retrieve_info", "detail": "Synthesizing information from sources"},
        {"tool": "submit_result", "detail": "Submitting answer"},
    ],
]

_TOOL_RESULTS = [
    "Found 5 relevant results from financial news sources covering the latest earnings data and analyst estimates.",
    "Successfully parsed SEC filing (38 pages). Key financial tables extracted.",
    "Retrieved quarterly revenue figures: Q1 $12.3B, Q2 $13.1B, Q3 $14.0B, Q4 $15.2B. Year-over-year growth of 11.4%.",
    "Analysis complete. Identified 3 key data points with supporting evidence from multiple sources.",
    "Cross-referenced data across 4 sources. Figures are consistent within ±2% margin.",
    "Extracted balance sheet data: Total assets $320B, total liabilities $198B, shareholders' equity $122B.",
]

_REASONING_TEXTS = [
    "The user is asking about specific financial metrics. I need to find the most recent filings and cross-reference with analyst reports to provide an accurate answer. Let me start by searching for the latest available data.",
    "Based on the SEC filing data, I can see the company's revenue trend over the past four quarters. I should verify these numbers against the earnings press release and check for any restatements or one-time charges that might affect the figures.",
    "I've gathered data from multiple sources. The key figures are consistent. I need to synthesize this into a clear, concise answer with the most relevant data points highlighted.",
    "Looking at the financial statements, I notice the operating margin has improved significantly. Let me cross-check this against industry benchmarks and recent analyst commentary to provide context.",
]

_SELF_EVAL_CRITIQUES = {
    "low": [
        "The answer provides a general direction but lacks specific numerical data. The sources are somewhat dated (6+ months old) and may not reflect the most current figures. A more thorough search of recent filings would improve accuracy.",
        "While the answer identifies the correct trend, the specific figures cited could not be fully verified against primary sources. Additional cross-referencing with SEC filings is recommended.",
    ],
    "high": [
        "The answer is well-supported by multiple authoritative sources including recent SEC filings and earnings reports. The specific figures cited are consistent across sources and appear accurate.",
        "Strong answer backed by primary financial data. The figures are sourced from official filings and cross-verified with analyst estimates. The response correctly addresses the user's specific question.",
    ],
}

_REFLECTIONS = [
    "In the previous attempt, I relied too heavily on secondary sources. I should directly consult SEC EDGAR filings for the most authoritative data. Additionally, I should pay closer attention to the specific time period the user is asking about and ensure my figures match that period exactly.",
    "My prior answer was too broad. I need to focus on the specific metric requested and provide a precise number with its source. I should also check for any recent amendments or restatements that might affect the figures.",
    "The previous trial's confidence was low because I couldn't verify the figures from a primary source. This time I should start with the official SEC filing, extract the exact numbers, and then supplement with analyst commentary for context.",
]

_MOCK_ANSWERS = [
    "Based on the most recent 10-K filing, **Apple Inc. reported total net revenue of $383.3 billion** for fiscal year 2023 (ended September 30, 2023), representing a decrease of approximately 2.8% compared to fiscal year 2022 revenue of $394.3 billion.\n\nThe breakdown by segment:\n- **iPhone**: $200.6B (52.3% of total)\n- **Services**: $85.2B (22.2%)\n- **Mac**: $29.4B (7.7%)\n- **iPad**: $28.3B (7.4%)\n- **Wearables, Home & Accessories**: $39.8B (10.4%)",
    "**Microsoft's market capitalization reached approximately $3.1 trillion** as of late 2024, making it one of the most valuable publicly traded companies globally.\n\nKey metrics from recent filings:\n- **Revenue (FY2024)**: $245.1B (+15.7% YoY)\n- **Net Income**: $88.1B\n- **Operating Margin**: 44.6%\n- **P/E Ratio**: ~36x forward earnings",
    "According to the latest quarterly earnings report, **Tesla delivered 1.81 million vehicles** in 2023, with Q4 deliveries of approximately 484,507 units.\n\n- **Total Revenue (2023)**: $96.8B\n- **Automotive Gross Margin**: 18.2%\n- **Free Cash Flow**: $4.4B\n- **Energy Storage Deployments**: 14.7 GWh (+125% YoY)",
    "Based on available financial data, the company reported **earnings per share (EPS) of $6.13** for the most recent fiscal year, exceeding analyst consensus estimates of $5.89.\n\nNotable highlights:\n- Revenue grew **8.3% year-over-year**\n- Operating expenses decreased by 2.1%\n- Free cash flow improved to $12.4B\n- The board authorized a new $15B share repurchase program",
]

_CHAT_RESPONSES = [
    "I'm your financial analyst agent. I can look up company financials, SEC filings, market data, and more — just give me a task and I'll get to work.",
    "Sure, I'd be happy to help! I specialize in financial analysis — I can search SEC EDGAR filings, pull recent financial data, and analyze company metrics. What would you like me to work on?",
    "That's a great question! While I focus primarily on financial data and analysis, I can have a general conversation too. Is there a particular company or financial metric you'd like me to look into?",
    "Hello! I'm your financial analyst agent. I use a multi-trial reflexion approach to ensure high-quality answers backed by real financial data. Feel free to ask me anything about company financials, market trends, or SEC filings.",
]


# ---------------------------------------------------------------------------
# Mock streaming generators
# ---------------------------------------------------------------------------

async def _stream_task(question: str, session_id: str, max_trials: int, confidence_threshold: float, agent: dict):
    yield _sse("session", {"session_id": session_id})
    yield _sse("agent", agent)
    await asyncio.sleep(0.2)

    yield _sse("status", {"message": f"Agent starting work — model: {agent['model']}"})
    await asyncio.sleep(0.4)

    query_short = question[:60] + ("…" if len(question) > 60 else "")

    num_trials = random.choice([1, 1, 2]) if max_trials >= 2 else 1
    num_trials = min(num_trials, max_trials)

    for trial in range(1, num_trials + 1):
        is_last_trial = trial == num_trials

        evt = {"trial": trial, "max_trials": max_trials}
        yield _sse("trial_start", evt)
        _append_event(session_id, "trial_start", evt)
        await asyncio.sleep(0.3)

        tool_seq = random.choice(_TOOL_SEQUENCES)
        for turn, tool_info in enumerate(tool_seq, start=1):
            detail = tool_info["detail"].format(query_short=query_short)
            evt = {"turn": turn, "tool": tool_info["tool"], "detail": detail}
            yield _sse("tool_call", evt)
            _append_event(session_id, "tool_call", evt)
            await asyncio.sleep(random.uniform(0.3, 0.8))

            evt = {"text": random.choice(_TOOL_RESULTS)}
            yield _sse("tool_result", evt)
            _append_event(session_id, "tool_result", evt)
            await asyncio.sleep(random.uniform(0.1, 0.3))

        # --- Mock file_edit events ---
        mock_turn = len(tool_seq) + 1
        fe_create = {
            "turn": mock_turn,
            "command": "create",
            "path": "/workspace/testing_workdir/analysis.py",
            "file_text": (
                "import pandas as pd\n"
                "import numpy as np\n"
                "\n"
                "\n"
                "def load_data(filepath: str) -> pd.DataFrame:\n"
                '    """Load and validate financial data from CSV."""\n'
                "    df = pd.read_csv(filepath)\n"
                '    required = ["date", "open", "high", "low", "close", "volume"]\n'
                "    missing = [c for c in required if c not in df.columns]\n"
                "    if missing:\n"
                '        raise ValueError(f"Missing columns: {missing}")\n'
                "    return df\n"
                "\n"
                "\n"
                "def compute_returns(df: pd.DataFrame) -> pd.Series:\n"
                '    """Calculate daily log returns."""\n'
                '    return np.log(df["close"] / df["close"].shift(1)).dropna()\n'
            ),
        }
        yield _sse("file_edit", fe_create)
        _append_event(session_id, "file_edit", fe_create)
        await asyncio.sleep(0.6)

        fe_edit = {
            "turn": mock_turn + 1,
            "command": "str_replace",
            "path": "/workspace/testing_workdir/analysis.py",
            "old_str": (
                "def compute_returns(df: pd.DataFrame) -> pd.Series:\n"
                '    """Calculate daily log returns."""\n'
                '    return np.log(df["close"] / df["close"].shift(1)).dropna()'
            ),
            "new_str": (
                "def compute_returns(df: pd.DataFrame, method: str = \"log\") -> pd.Series:\n"
                '    """Calculate daily returns.\n'
                "\n"
                "    Args:\n"
                "        df: DataFrame with 'close' column.\n"
                '        method: "log" for log returns, "simple" for arithmetic returns.\n'
                '    """\n'
                '    close = df["close"]\n'
                '    if method == "log":\n'
                "        return np.log(close / close.shift(1)).dropna()\n"
                "    return (close / close.shift(1) - 1).dropna()"
            ),
        }
        yield _sse("file_edit", fe_edit)
        _append_event(session_id, "file_edit", fe_edit)
        await asyncio.sleep(0.5)

        evt = {"text": random.choice(_REASONING_TEXTS)}
        yield _sse("reasoning", evt)
        _append_event(session_id, "reasoning", evt)
        await asyncio.sleep(0.3)

        yield _sse("status", {"message": "Reviewing my work..."})
        await asyncio.sleep(0.5)

        if is_last_trial:
            score = random.uniform(0.72, 0.95)
            critique = random.choice(_SELF_EVAL_CRITIQUES["high"])
        else:
            score = random.uniform(0.25, confidence_threshold - 0.05)
            critique = random.choice(_SELF_EVAL_CRITIQUES["low"])

        evt = {
            "is_confident": is_last_trial,
            "confidence_score": round(score, 2),
            "critique": critique,
        }
        yield _sse("self_eval", evt)
        _append_event(session_id, "self_eval", evt)
        await asyncio.sleep(0.3)

        if not is_last_trial:
            yield _sse("status", {"message": "Not confident enough — rethinking approach..."})
            await asyncio.sleep(0.4)

            evt = {"text": random.choice(_REFLECTIONS)}
            yield _sse("reflection", evt)
            _append_event(session_id, "reflection", evt)
            await asyncio.sleep(0.5)

    evt = {"text": random.choice(_MOCK_ANSWERS)}
    yield _sse("answer", evt)
    _append_event(session_id, "answer", evt)
    await asyncio.sleep(0.1)

    yield _sse("done", {"message": "Complete"})


async def _stream_conversation(question: str, session_id: str, agent: dict):
    yield _sse("session", {"session_id": session_id})
    yield _sse("agent", agent)
    await asyncio.sleep(0.2)

    response_text = random.choice(_CHAT_RESPONSES)
    evt = {"text": response_text}
    yield _sse("chat_response", evt)
    _append_event(session_id, "chat_response", evt)
    await asyncio.sleep(0.1)

    yield _sse("done", {"message": "Complete"})


# ---------------------------------------------------------------------------
# Real agent streaming (enabled when REAL_AGENT_ENABLED is True)
# ---------------------------------------------------------------------------

_turn_counter: dict[str, int] = {}


def _extract_text(obj: Any) -> str:
    """Safely extract plain text from SDK content types.

    Handles: str, TextContent (has .text), Sequence[TextContent], Observation
    (has .content which may itself be str or list), and arbitrary objects.
    """
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    # Single TextContent-like object
    if hasattr(obj, "text") and isinstance(getattr(obj, "text"), str):
        return obj.text
    # Sequence of TextContent-like objects (Sequence[TextContent])
    if isinstance(obj, (list, tuple)):
        parts = []
        for item in obj:
            if hasattr(item, "text") and isinstance(getattr(item, "text"), str):
                parts.append(item.text)
            elif isinstance(item, str):
                parts.append(item)
        if parts:
            return " ".join(parts)
    # Last resort — but avoid repr of SDK objects
    return ""


def _parse_tool_args(tc: Any) -> tuple[str, dict]:
    """Extract (args_string, args_dict) from a MessageToolCall.

    MessageToolCall uses OpenAI format: tc.function.name / tc.function.arguments
    where arguments is a JSON-encoded string.
    """
    fn = getattr(tc, "function", None)
    args_str = (getattr(fn, "arguments", None) or "") if fn else ""
    try:
        args_dict = json.loads(args_str) if args_str else {}
    except (json.JSONDecodeError, TypeError):
        args_dict = {}
    return args_str, args_dict


def _map_event_to_sse(event: Any, session_id: str) -> dict | None:
    """Translate an OpenHands Event into the SSE dict format the frontend expects.

    Returns None for events that have no meaningful SSE representation.
    """
    try:
        # --- Agent chose to call a tool ---
        if isinstance(event, ActionEvent):
            if getattr(event, "tool_call", None):
                tool_name = getattr(event, "tool_name", None) or "unknown"
                _, args_dict = _parse_tool_args(event.tool_call)

                # The "finish" tool signals task completion — emit its
                # message as the final answer instead of a tool_call row.
                if tool_name.lower() in ("finish", "finishtool"):
                    finish_text = (
                        args_dict.get("message", "")
                        or args_dict.get("outputs", "")
                        or args_dict.get("text", "")
                    )
                    # Also pull from thought if the args were empty
                    if not finish_text:
                        finish_text = _extract_text(getattr(event, "thought", None))
                    if finish_text:
                        return _sse("answer", {"text": finish_text})
                    return None

                _turn_counter.setdefault(session_id, 0)
                _turn_counter[session_id] += 1

                # For terminal/bash actions, predict which files this command
                # will write so the matching ObservationEvent can read them
                # off the workspace and emit file_edit payloads.
                if tool_name.lower() in _TERMINAL_TOOL_NAMES:
                    predicted = _extract_bash_output_paths(
                        str(args_dict.get("command", ""))
                    )
                    _pending_bash_writes.setdefault(session_id, []).append(predicted)

                # Emit a richer event for file_editor tool calls
                if tool_name.lower() in ("file_editor", "fileeditortool"):
                    raw_path = args_dict.get("path", "")
                    # Strip Docker workspace prefix → relative path
                    if raw_path.startswith("/workspace/"):
                        raw_path = raw_path[len("/workspace/"):]
                    return _sse("file_edit", {
                        "turn": _turn_counter[session_id],
                        "command": args_dict.get("command", ""),
                        "path": raw_path,
                        "file_text": args_dict.get("file_text"),
                        "old_str": args_dict.get("old_str"),
                        "new_str": args_dict.get("new_str"),
                        "insert_line": args_dict.get("insert_line"),
                    })

                detail = str(
                    args_dict.get("command", args_dict.get("query", args_dict.get("path", "")))
                )[:120]

                return _sse("tool_call", {
                    "turn": _turn_counter[session_id],
                    "tool": tool_name,
                    "detail": detail or f"Calling {tool_name}",
                })

            # thought is Sequence[TextContent]
            thought_text = _extract_text(getattr(event, "thought", None))
            if thought_text:
                return _sse("reasoning", {"text": thought_text})

            reasoning = getattr(event, "reasoning_content", None)
            if reasoning and isinstance(reasoning, str):
                return _sse("reasoning", {"text": reasoning})

            return None

        # --- Tool execution result ---
        if isinstance(event, ObservationEvent):
            obs_tool = getattr(event, "tool_name", None) or ""
            obs = getattr(event, "observation", None)
            if obs is not None:
                raw = getattr(obs, "content", None) or getattr(obs, "text", None)
                content = _extract_text(raw) or str(obs)
            else:
                content = str(event)

            # The finish tool's observation carries the agent's final message
            if obs_tool.lower() in ("finish", "finishtool") and content.strip():
                return _sse("answer", {"text": content})

            return _sse("tool_result", {"text": content[:2000]})

        # --- Agent's text message (often the final answer) ---
        if isinstance(event, MessageEvent):
            text = _extract_text(getattr(event, "extended_content", None))
            if not text:
                text = getattr(event, "reasoning_content", None) or ""
            if not text:
                text = _extract_text(getattr(event, "content", None))
            if not text:
                message = getattr(event, "message", None)
                text = _extract_text(getattr(message, "content", None))
            if text:
                return _sse("answer", {"text": text})
            return None

        # --- Errors ---
        if isinstance(event, AgentErrorEvent):
            return _sse("error", {"message": getattr(event, "error", str(event))})

        if isinstance(event, ConversationErrorEvent):
            code = getattr(event, "code", None) or "ConversationError"
            detail = getattr(event, "detail", None) or getattr(event, "message", None) or str(event)
            logger.error("ConversationErrorEvent: code=%s detail=%s", code, detail)
            return _sse("error", {"message": f"{code}: {detail}"})

    except Exception:
        logger.exception("Failed to map event to SSE: %s", type(event).__name__)

    return None


def _validate_mount_dir(mount_dir: str | None) -> str | None:
    """Reject mount_dir paths that escape the user's home or /tmp."""
    if not mount_dir:
        return None
    resolved = os.path.realpath(mount_dir)
    home = os.path.expanduser("~")
    allowed_prefixes = (home + os.sep, tempfile.gettempdir() + os.sep)
    if not resolved.startswith(allowed_prefixes):
        raise HTTPException(
            status_code=400,
            detail="mount_dir must be under your home directory or /tmp",
        )
    return resolved


def _resolve_workspace(session_id: str, mount_dir: str | None) -> tuple[str | None, str | None]:
    """Determine the effective mount directory and any staging dir to clean up.

    If files were uploaded for this session, they live in a staging directory.
    - If ``mount_dir`` is also set, copy uploaded files into it and use ``mount_dir``.
    - Otherwise, use the staging directory itself as the mount.

    Returns (effective_mount_dir, staging_dir_to_cleanup_or_None).
    """
    mount_dir = _validate_mount_dir(mount_dir)
    staging = _upload_dirs.pop(session_id, None)

    if staging and mount_dir:
        for name in os.listdir(staging):
            src = os.path.join(staging, name)
            dst = os.path.join(mount_dir, name)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                shutil.copy2(src, dst)
        return mount_dir, staging

    if staging:
        return staging, staging

    return mount_dir, None


def _copy_dir_contents(src_dir: str, dst_dir: str) -> None:
    """Copy top-level entries from src_dir into dst_dir (merge / overwrite files)."""
    if not os.path.isdir(src_dir):
        return
    for name in os.listdir(src_dir):
        src = os.path.join(src_dir, name)
        dst = os.path.join(dst_dir, name)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)


# Top-level entries excluded when syncing back the shared workspace to the
# user's real mount_dir. These are agent-internal scaffolding (skill packs,
# task tracker files, conversation journals, …) that should not pollute
# the user's project directory.
_SYNC_BACK_EXCLUDE_TOPLEVEL: set[str] = {".agents", ".openhands"}


def _sync_dir_contents_for_export(src_dir: str, dst_dir: str) -> None:
    """Copy src_dir → dst_dir, skipping agent-internal scaffolding dirs.

    Used to flush /workspace back to the user's original ``mount_dir`` after
    a run. Hidden dotfiles are kept (users may intentionally create them),
    but the well-known agent-internal top-level dirs are excluded so the
    user's tree stays clean.
    """
    if not os.path.isdir(src_dir) or not dst_dir:
        return
    os.makedirs(dst_dir, exist_ok=True)
    for name in os.listdir(src_dir):
        if name in _SYNC_BACK_EXCLUDE_TOPLEVEL:
            continue
        src = os.path.join(src_dir, name)
        dst = os.path.join(dst_dir, name)
        if os.path.isdir(src):
            shutil.copytree(src, dst, dirs_exist_ok=True)
        else:
            shutil.copy2(src, dst)


def _clear_dir_contents(path: str) -> None:
    """Remove everything inside ``path`` but keep the directory itself."""
    if not path or not os.path.isdir(path):
        return
    for name in os.listdir(path):
        full = os.path.join(path, name)
        try:
            if os.path.isdir(full) and not os.path.islink(full):
                shutil.rmtree(full)
            else:
                os.unlink(full)
        except OSError:
            logger.warning("Failed to remove %s while clearing %s", full, path)


def _owner_key(
    session_id: str,
    mount_dir: str | None,
    skill_ids: list[str] | None,
) -> tuple[str, str | None, tuple[str, ...]]:
    """Stable identity for 'the session + workspace config currently in /workspace'."""
    return (session_id, mount_dir, tuple(sorted(skill_ids or [])))


def _evict_current_owner_sync() -> None:
    """Sync-back + cleanup for the current owner. Caller must hold the lock.

    - If the owner set a ``sync_target`` (the user's real mount_dir), copy
      the current /workspace contents back into it, skipping agent-internal
      dirs.
    - Remove any temp ``cleanup_dirs`` the owner accumulated (skill staging,
      upload staging).
    - Clear ``_SHARED_WS["current_owner"]`` so the next prime runs a full swap.
    """
    owner = _SHARED_WS.get("current_owner")
    if not owner:
        return

    host_dir = _SHARED_WS.get("host_dir")
    sync_target = owner.get("sync_target")
    if host_dir and sync_target:
        try:
            _sync_dir_contents_for_export(host_dir, sync_target)
            logger.info(
                "Synced shared workspace back to mount_dir=%s (session=%s)",
                sync_target, owner.get("session_id"),
            )
        except Exception:
            logger.exception(
                "Sync-back failed for session=%s → %s",
                owner.get("session_id"), sync_target,
            )

    for path in owner.get("cleanup_dirs") or []:
        if path and os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)

    _SHARED_WS["current_owner"] = None


def _prime_shared_workspace_sync(
    session_id: str,
    effective_mount: str | None,
    sync_target: str | None,
    cleanup_dirs: list[str],
    key: tuple,
) -> None:
    """Make /workspace reflect ``effective_mount``. Caller must hold the lock.

    Fast path: if the incoming ``key`` matches the current owner, do nothing —
    the session is continuing and /workspace already holds its state.

    Slow path: evict the current owner (sync-back + cleanup), wipe the shared
    bind mount, copy ``effective_mount`` contents in, and record this session
    as the new owner.
    """
    current = _SHARED_WS.get("current_owner")
    if current and current.get("key") == key:
        # Same session + mount + skills as last turn — reuse as-is.
        for path in cleanup_dirs or []:
            if path and os.path.isdir(path) and path not in (current.get("cleanup_dirs") or []):
                shutil.rmtree(path, ignore_errors=True)
        return

    _evict_current_owner_sync()

    host_dir = _SHARED_WS["host_dir"]
    _clear_dir_contents(host_dir)
    if effective_mount and os.path.isdir(effective_mount):
        _copy_dir_contents(effective_mount, host_dir)

    _SHARED_WS["current_owner"] = {
        "key": key,
        "session_id": session_id,
        "sync_target": sync_target,
        "cleanup_dirs": list(cleanup_dirs or []),
    }
    logger.info(
        "Primed shared workspace: session=%s mount=%s skills_cached=%s",
        session_id, sync_target, bool(cleanup_dirs),
    )


def _sync_current_owner_back_sync() -> None:
    """Copy /workspace contents back to the owner's sync target (no eviction).

    Called after each turn so the user sees their files on disk without
    having to wait for session eviction. Caller must hold the lock.
    """
    owner = _SHARED_WS.get("current_owner")
    if not owner:
        return
    host_dir = _SHARED_WS.get("host_dir")
    sync_target = owner.get("sync_target")
    if not (host_dir and sync_target):
        return
    try:
        _sync_dir_contents_for_export(host_dir, sync_target)
    except Exception:
        logger.exception(
            "Post-turn sync-back failed for session=%s → %s",
            owner.get("session_id"), sync_target,
        )


def _try_get_skill_from_db(skill_id: str) -> dict | None:
    """Try to fetch skill materialization data from DB. Returns None if DB unavailable."""
    from routers.skills import _db_available
    if not _db_available:
        return None
    try:
        import asyncio
        from db import async_session
        from services.skill_service import get_skill_for_materialization

        async def _fetch():
            async with async_session() as session:
                return await get_skill_for_materialization(session, skill_id)

        loop = asyncio.get_event_loop()
        if loop.is_running():
            # We're in an async context — use to_thread with a new loop
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(lambda: asyncio.run(_fetch())).result(timeout=5)
        return asyncio.run(_fetch())
    except Exception:
        return None


def _validate_skills_for_runtime(skill_ids: list[str]) -> None:
    """Ensure each skill can be materialized under workspace/skills/."""
    for sid in skill_ids:
        # Check DB first, then in-memory
        db_skill = _try_get_skill_from_db(sid)
        if db_skill:
            continue
        if sid not in _SKILLS:
            raise HTTPException(status_code=400, detail=f"Unknown skill_id: {sid}")
        skill = _SKILLS[sid]
        by_name = _FILE_CONTENTS.get(sid, {})
        for meta in skill.get("files") or []:
            rel = meta["name"].replace("\\", "/")
            if rel == "SKILL.md" or rel.endswith("/SKILL.md"):
                continue
            if rel in by_name:
                continue
            if skill.get("type") == "builtin":
                disk_path = os.path.join(_SKILLS_DIR, sid, rel)
                if os.path.isfile(disk_path):
                    continue
            raise HTTPException(
                status_code=400,
                detail=f"Skill {sid} file {rel} has no retrievable content",
            )


def _materialize_skill_package(skills_root: str, skill_id: str) -> None:
    """Write one skill package (SKILL.md + auxiliary files) under skills_root/skill_id/."""
    # Try DB first for marketplace skills
    db_data = _try_get_skill_from_db(skill_id)
    if db_data:
        pkg = os.path.join(skills_root, skill_id)
        os.makedirs(pkg, exist_ok=True)
        with open(os.path.join(pkg, "SKILL.md"), "w", encoding="utf-8") as f:
            f.write(db_data.get("definition", ""))
        for rel_path, content in db_data.get("files", {}).items():
            if rel_path == "SKILL.md" or rel_path.endswith("/SKILL.md"):
                continue
            dest = os.path.realpath(os.path.join(pkg, rel_path))
            if not dest.startswith(os.path.realpath(pkg) + os.sep):
                continue  # skip path traversal attempts
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "w", encoding="utf-8") as f:
                f.write(content or "")
        return

    # Fallback to in-memory
    skill = _SKILLS[skill_id]
    pkg = os.path.join(skills_root, skill_id)
    os.makedirs(pkg, exist_ok=True)
    definition = skill.get("definition") or ""
    with open(os.path.join(pkg, "SKILL.md"), "w", encoding="utf-8") as f:
        f.write(definition)
    by_name = _FILE_CONTENTS.get(skill_id, {})
    pkg_real = os.path.realpath(pkg)
    for meta in skill.get("files") or []:
        rel = meta["name"].replace("\\", "/")
        if rel == "SKILL.md" or rel.endswith("/SKILL.md"):
            continue
        dest = os.path.realpath(os.path.join(pkg, rel))
        if not dest.startswith(pkg_real + os.sep):
            continue  # skip path traversal attempts
        dest_parent = os.path.dirname(dest)
        if dest_parent:
            os.makedirs(dest_parent, exist_ok=True)
        if rel in by_name:
            text = by_name[rel]
        else:
            skill_dir_real = os.path.realpath(os.path.join(_SKILLS_DIR, skill_id))
            disk_path = os.path.realpath(os.path.join(_SKILLS_DIR, skill_id, rel))
            if not disk_path.startswith(skill_dir_real + os.sep):
                continue
            with open(disk_path, encoding="utf-8") as f:
                text = f.read()
        with open(dest, "w", encoding="utf-8") as f:
            f.write(text)


def _resolve_workspace_for_runtime(
    session_id: str,
    mount_dir: str | None,
    skill_ids: list[str] | None,
) -> tuple[str | None, list[str]]:
    """Resolve Docker mount path and directories to remove after the run.

    When ``skill_ids`` is non-empty, builds a temp workspace: copies ``mount_dir``
    and upload staging into it, replaces ``skills/`` with only the selected packages,
    and returns that path plus cleanup list (temp root and staging if any).
    """
    if not skill_ids:
        effective, staging = _resolve_workspace(session_id, mount_dir)
        cleanup: list[str] = [staging] if staging else []
        return effective, cleanup

    staging = _upload_dirs.pop(session_id, None)
    root = tempfile.mkdtemp(prefix="agent_workspace_")
    workspace = os.path.join(root, "ws")
    os.makedirs(workspace, exist_ok=True)

    try:
        if mount_dir and os.path.isdir(mount_dir):
            _copy_dir_contents(mount_dir, workspace)
        if staging:
            _copy_dir_contents(staging, workspace)

        # OpenHands loads project skills from .agents/skills/ (and legacy .openhands/*).
        # Replace those trees so the request sees only the selected skill packages.
        for rel in (
            os.path.join(".agents", "skills"),
            os.path.join(".openhands", "skills"),
            os.path.join(".openhands", "microagents"),
        ):
            p = os.path.join(workspace, rel)
            if os.path.isdir(p):
                shutil.rmtree(p)
        skills_dir = os.path.join(workspace, ".agents", "skills")
        os.makedirs(skills_dir, exist_ok=True)
        for sid in skill_ids:
            _materialize_skill_package(skills_dir, sid)
    except Exception:
        if staging:
            _upload_dirs[session_id] = staging
        shutil.rmtree(root, ignore_errors=True)
        raise

    cleanup = [root]
    if staging:
        cleanup.append(staging)
    return workspace, cleanup


# ---------------------------------------------------------------------------
# Terminal-write detection (auto-open canvas for files dropped by bash)
# ---------------------------------------------------------------------------
#
# Strategy: instead of polling the workspace, we statically parse each
# terminal tool invocation, predict which paths the command will write, and
# read+emit those files when the matching observation event comes back.
# This mirrors how file_editor surfaces its writes — purely event-driven.

# Files we know how to render in the canvas. Mirrors the frontend allowlist
# in EditorCanvas.jsx (`isCanvasPreviewable`). Files outside this set still
# show up in the workspace tree, just don't auto-open.
_PREVIEWABLE_EXTS: set[str] = {
    ".md", ".markdown", ".mdown", ".mkd",
    ".txt", ".log", ".csv", ".tsv",
    ".pdf",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg", ".ico",
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".json", ".yml", ".yaml", ".toml", ".ini", ".cfg",
    ".sh", ".bash", ".zsh",
    ".css", ".scss", ".less", ".html", ".htm", ".xml",
    ".sql", ".rs", ".go", ".java", ".kt", ".swift",
    ".c", ".cc", ".cpp", ".h", ".hpp", ".rb", ".lua", ".r", ".php", ".pl",
}

# Agent-internal artifacts that should never auto-open the canvas even if
# bash happens to create one (TASKS.json, reflexion memory, OpenHands
# event journals, …). They remain visible in the workspace tree.
_AUTO_OPEN_IGNORED_BASENAMES: set[str] = {
    "TASKS.json",
    "TASKS.md",
    "reflexion_memory.json",
    "base_state.json",
}
_AUTO_OPEN_IGNORED_SEGMENTS: tuple[str, ...] = (
    "subagents",
    "events",
    "conversations",
)
_AUTO_OPEN_IGNORED_BASENAME_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^event-\d{5}-[0-9a-fA-F\-]{8,}\.json$"),
)


def _should_skip_auto_open(rel_path: str) -> bool:
    base = os.path.basename(rel_path)
    if base in _AUTO_OPEN_IGNORED_BASENAMES:
        return True
    if any(p.match(base) for p in _AUTO_OPEN_IGNORED_BASENAME_PATTERNS):
        return True
    parts = rel_path.replace("\\", "/").split("/")
    return any(seg in _AUTO_OPEN_IGNORED_SEGMENTS for seg in parts[:-1])


# Per-session FIFO of [paths] predicted by each pending terminal action.
# Pushed when an ActionEvent for the terminal tool is observed, popped when
# the matching ObservationEvent comes back so we can read the actual files.
_pending_bash_writes: dict[str, list[list[str]]] = {}

# Tools whose action/observation we treat as "bash-like".
_TERMINAL_TOOL_NAMES: set[str] = {
    "terminal", "bash", "execute_bash", "shell", "executebash",
}

# Path char class: anything that isn't whitespace, quoting, redirection or
# subshell punctuation. Covers most realistic POSIX paths.
_PATH_CHARS = r"[^\s'\"`;&|<>()]+"

# >, >>, &>, &>>, 1>, 2>, 1>>, 2>> followed by a (optionally quoted) path.
_REDIRECT_RE = re.compile(rf"(?:[12]?&?>>?|&>>?)\s*(['\"]?)({_PATH_CHARS})\1")
# `tee [-a] file...`
_TEE_RE = re.compile(rf"\btee\s+(?:-a\s+)?(['\"]?)({_PATH_CHARS})\1")
# `touch f1 f2 ...` — capture the run of args.
_TOUCH_RE = re.compile(rf"\btouch\s+((?:{_PATH_CHARS}\s*)+)")
# `cp/mv/install [-flags] src dst` — last arg is the destination.
_CPMV_RE = re.compile(
    rf"\b(?:cp|mv|install)\s+(?:-[A-Za-z]+\s+)*{_PATH_CHARS}\s+({_PATH_CHARS})"
)
# `pandoc … -o file`
_PANDOC_RE = re.compile(rf"\bpandoc\b[^;&|]*?-o\s+(['\"]?)({_PATH_CHARS})\1")


def _extract_bash_output_paths(command: str) -> list[str]:
    """Best-effort: return workspace-relative paths a shell command will write."""
    if not command:
        return []
    # Strip $(…) and `…` subshells so paths inside them don't get picked up
    # as outputs of the parent command.
    cleaned = re.sub(r"\$\([^()]*\)|`[^`]*`", "", command)

    raw_paths: list[str] = []
    for rx in (_REDIRECT_RE, _TEE_RE, _PANDOC_RE):
        for m in rx.finditer(cleaned):
            raw_paths.append(m.group(2))
    for m in _TOUCH_RE.finditer(cleaned):
        raw_paths.extend(p.strip("'\"") for p in m.group(1).split())
    for m in _CPMV_RE.finditer(cleaned):
        raw_paths.append(m.group(1))

    out: list[str] = []
    seen: set[str] = set()
    for raw in raw_paths:
        p = raw.strip().strip("'\"")
        if not p or p in {"/dev/null", "/dev/stderr", "/dev/stdout"}:
            continue
        # Normalize to workspace-relative paths; the agent runs with cwd at
        # /workspace inside the container, which == host_dir on the host.
        if p.startswith("/workspace/"):
            p = p[len("/workspace/"):]
        elif p.startswith("/"):
            continue  # absolute path outside the workspace, ignore
        p = p.lstrip("./")
        if not p or p in seen:
            continue
        seen.add(p)
        out.append(p)
    return out


def _build_terminal_file_edits(session_id: str, host_dir: str) -> list[dict]:
    """Pop the next pending bash-write batch and emit file_edit payloads."""
    fifo = _pending_bash_writes.get(session_id)
    if not fifo:
        return []
    paths = fifo.pop(0)
    payloads: list[dict] = []
    for rel in paths:
        if _should_skip_auto_open(rel):
            continue
        ext = os.path.splitext(rel)[1].lower()
        if ext not in _PREVIEWABLE_EXTS:
            continue
        full = os.path.join(host_dir, rel)
        if not os.path.isfile(full):
            continue  # command may have failed, or path didn't resolve
        file_text: str | None = None
        if _is_text_file(full):
            try:
                with open(full, "r", encoding="utf-8", errors="replace") as f:
                    file_text = f.read(500_000)
            except OSError:
                file_text = None
        _turn_counter.setdefault(session_id, 0)
        _turn_counter[session_id] += 1
        payloads.append({
            "turn": _turn_counter[session_id],
            "command": "create",
            "path": rel,
            "file_text": file_text,
            "old_str": None,
            "new_str": None,
            "insert_line": None,
        })
    return payloads


async def _stream_real_task(
    question: str,
    session_id: str,
    agent_info: dict,
    mount_dir: str | None = None,
    use_reflexion: bool = False,
    skill_ids: list[str] | None = None,
):
    """Run the real OpenHands agent against the shared DockerWorkspace.

    The container is started once at app boot (see ``lifespan``). Here we:
      1. Resolve the request's source workspace (user mount_dir ± skills).
      2. Under the shared lock, prime /workspace (noop if this session already
         owns it; full wipe + copy-in otherwise).
      3. Run the agent against the shared workspace, streaming events.
      4. Sync /workspace back to the user's mount_dir so the UI sees results.
    """
    if _SHARED_WS.get("workspace") is None:
        yield _sse("error", {"message": "Shared workspace is not available."})
        yield _sse("done", {"message": "Complete"})
        return

    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    effective_mount, cleanup_dirs = _resolve_workspace_for_runtime(
        session_id, mount_dir, skill_ids
    )
    if skill_ids:
        logger.info(
            "Request-scoped workspace=%s skill_ids=%s",
            effective_mount,
            skill_ids,
        )

    # Where sync-back writes. Only the user's declared mount_dir is a valid
    # sync target; skills-only or staging-only runs don't write back anywhere.
    sync_target = _validate_mount_dir(mount_dir)
    owner_key = _owner_key(session_id, sync_target, skill_ids)
    host_dir = _SHARED_WS["host_dir"]

    _turn_counter[session_id] = 0
    answer_emitted = {"value": False}

    def _callback(event):
        mapped = _map_event_to_sse(event, session_id)
        if mapped:
            if mapped.get("event") == "answer":
                answer_emitted["value"] = True
            loop.call_soon_threadsafe(queue.put_nowait, mapped)

        # When a terminal/bash observation comes back, read the predicted
        # output files off the workspace and surface them as file_edit
        # events so the canvas auto-opens just like file_editor writes.
        try:
            if isinstance(event, ObservationEvent):
                obs_tool = (getattr(event, "tool_name", None) or "").lower()
                if obs_tool in _TERMINAL_TOOL_NAMES:
                    for payload in _build_terminal_file_edits(session_id, host_dir):
                        loop.call_soon_threadsafe(
                            queue.put_nowait, _sse("file_edit", payload)
                        )
        except Exception:
            logger.exception("Failed to emit terminal-driven file_edit events")

    def _run_agent():
        error = None
        try:
            final_answer = _agent_runtime(
                repo_dir=host_dir,
                instruction=question,
                mount_dir=host_dir,
                event_callback=_callback,
                use_reflexion=use_reflexion,
                workspace=_SHARED_WS["workspace"],
            )
            if final_answer and not answer_emitted["value"]:
                answer_emitted["value"] = True
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    _sse("answer", {"text": final_answer}),
                )
        except Exception as exc:
            error = str(exc)
            logger.exception("Agent runtime failed")
        finally:
            if error:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    _sse("error", {"message": error}),
                )
            loop.call_soon_threadsafe(queue.put_nowait, None)

    yield _sse("session", {"session_id": session_id})
    yield _sse("agent", agent_info)
    yield _sse("status", {"message": f"Agent starting work — model: {agent_info.get('model', 'unknown')}"})

    lock: asyncio.Lock = _SHARED_WS["lock"]
    async with lock:
        # Prime /workspace: fast path if the same session/mount is continuing,
        # full swap otherwise (sync out previous owner, wipe, copy in).
        try:
            await asyncio.to_thread(
                _prime_shared_workspace_sync,
                session_id,
                effective_mount,
                sync_target,
                cleanup_dirs,
                owner_key,
            )
        except Exception as exc:
            logger.exception("Failed to prime shared workspace")
            yield _sse("error", {"message": f"workspace prime failed: {exc}"})
            yield _sse("done", {"message": "Complete"})
            return

        _pending_bash_writes[session_id] = []

        loop.run_in_executor(None, _run_agent)

        got_answer = False
        last_tool_text: str | None = None

        while True:
            item = await queue.get()
            if item is None:
                break
            event_type = item["event"]
            data = json.loads(item["data"])
            _append_event(session_id, event_type, data)

            yield item

            if event_type == "answer":
                got_answer = True
            elif event_type == "tool_result":
                last_tool_text = data.get("text")

        # Flush this turn's changes back to the user's mount_dir (if any).
        # The owner stays "this session" — next turn in the same session takes
        # the fast path and avoids any copying.
        try:
            await asyncio.to_thread(_sync_current_owner_back_sync)
        except Exception:
            logger.exception("Post-turn sync-back failed")

    if not got_answer and last_tool_text:
        evt = {"text": last_tool_text}
        yield _sse("answer", evt)
        _append_event(session_id, "answer", evt)

    _turn_counter.pop(session_id, None)
    _pending_bash_writes.pop(session_id, None)
    yield _sse("done", {"message": "Complete"})


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

class FileMetadata(BaseModel):
    name: str
    size: int | None = None
    type: str | None = None


class ChatRequest(BaseModel):
    question: str
    session_id: str | None = None
    model: str | None = None
    max_trials: int = 3
    confidence_threshold: float = 0.7
    use_reflexion: bool = False
    files: list[FileMetadata] | None = None
    mount_dir: str | None = None
    skill_ids: list[str] | None = None


@app.post("/api/upload")
async def upload_files(
    files: list[UploadFile] = File(...),
    session_id: str | None = None,
):
    """Save uploaded files to a staging directory for later Docker mounting."""
    sid = session_id or str(uuid.uuid4())
    staging = tempfile.mkdtemp(prefix="agent_uploads_")
    saved: list[dict] = []

    for upload in files:
        safe_name = os.path.basename(upload.filename) or f"upload_{uuid.uuid4().hex}"
        dest = os.path.join(staging, safe_name)
        content = await upload.read()
        with open(dest, "wb") as f:
            f.write(content)
        saved.append({
            "name": safe_name,
            "size": len(content),
            "type": upload.content_type,
        })

    _upload_dirs[sid] = staging
    logger.info("Staged %d files for session %s at %s", len(saved), sid, staging)
    return {"session_id": sid, "upload_dir": staging, "files": saved}


@app.post("/api/chat")
async def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    agent = _resolve_agent(req.model)

    file_dicts = [f.model_dump(exclude_none=True) for f in req.files] if req.files else None
    _upsert_chat(session_id, req.question, role="user", agent_id=agent["id"], files=file_dicts)

    skill_ids = req.skill_ids if req.skill_ids else None
    if skill_ids:
        _validate_skills_for_runtime(skill_ids)

    if REAL_AGENT_ENABLED:
        gen = _stream_real_task(
            req.question,
            session_id,
            agent,
            mount_dir=req.mount_dir,
            use_reflexion=req.use_reflexion,
            skill_ids=skill_ids,
        )
    else:
        gen = _stream_task(
            req.question,
            session_id,
            req.max_trials,
            req.confidence_threshold,
            agent,
        )

    return EventSourceResponse(gen)


@app.get("/api/browser/live")
async def browser_live_info(session_id: str | None = None):
    """Return connection info for the agent's live browser view.

    The agent-server container runs Chromium inside Xvfb and serves a
    noVNC client on a bundled HTTP port (container ``8002``). We publish
    that port onto the host and let the frontend iframe it directly;
    ``session_id`` is accepted for API symmetry but the same browser
    is shared for all sessions on the shared workspace.
    """
    if not ENABLE_BROWSER_LIVE:
        raise HTTPException(status_code=503, detail="Live browser is disabled.")

    novnc_port = _workspace_novnc_port()
    if novnc_port is None:
        raise HTTPException(status_code=503, detail="Live browser is not ready yet.")

    return {
        "sessionId": session_id,
        "port": novnc_port,
        # ``vnc_lite.html`` (or ``vnc.html``) is shipped with noVNC and
        # auto-connects to the websockify endpoint on the same origin.
        # ``resize=scale`` makes the noVNC client scale the remote display
        # to fit the iframe (preserving aspect ratio). Using ``remote``
        # relies on the VM's RandR support and frequently leaves the view
        # clipped when the iframe is smaller than the native VM resolution,
        # which we don't want.
        "url": (
            f"http://127.0.0.1:{novnc_port}/vnc.html"
            "?autoconnect=1&resize=scale&reconnect=1&show_dot=1"
        ),
    }


@app.get("/api/chats")
async def list_chats():
    """Return all chats sorted by most recently updated, without full messages."""
    summaries = [
        {
            "id": c["id"],
            "name": c["name"],
            "agent_id": c.get("agent_id"),
            "created_at": c["created_at"],
            "updated_at": c["updated_at"],
            "message_count": len(c["messages"]),
        }
        for c in _chats.values()
    ]
    summaries.sort(key=lambda s: s["updated_at"], reverse=True)
    return summaries


@app.get("/api/chats/{chat_id}")
async def get_chat(chat_id: str):
    if chat_id not in _chats:
        raise HTTPException(status_code=404, detail="Chat not found")
    return _chats[chat_id]


@app.patch("/api/chats/{chat_id}")
async def rename_chat(chat_id: str, body: dict):
    if chat_id not in _chats:
        raise HTTPException(status_code=404, detail="Chat not found")
    if "name" in body:
        _chats[chat_id]["name"] = body["name"]
        _chats[chat_id]["updated_at"] = _now_iso()
    return _chats[chat_id]


@app.delete("/api/chats/{chat_id}")
async def delete_chat(chat_id: str):
    if chat_id not in _chats:
        raise HTTPException(status_code=404, detail="Chat not found")
    del _chats[chat_id]
    return {"ok": True}


@app.get("/api/agents")
async def list_agents():
    # Stamp the real model onto every profile so the UI's agent list matches
    # what the runtime will actually call (see _resolve_agent).
    return [{**agent, "model": AGENT_MODEL} for agent in _AGENTS.values()]


@app.get("/api/evaluations")
async def evaluations():
    return [
        {
            "run_id": "20250310_14-30-22_bench",
            "agent_id": "agent-claude-full",
            "timestamp": "2025-03-10 14:30:22",
            "task_success": {"passed": 16, "total": 20, "rate": 0.80},
            "step_success": {"passed": 142, "total": 168, "rate": 0.845},
            "category_success": {
                "Web Search": {"passed": 45, "total": 50, "rate": 0.90},
                "SEC Filing Retrieval": {"passed": 28, "total": 35, "rate": 0.80},
                "Numerical Reasoning": {"passed": 38, "total": 45, "rate": 0.844},
                "Data Synthesis": {"passed": 31, "total": 38, "rate": 0.816},
            },
            "latency": {
                "avg_ms": 3200,
                "p50_ms": 2800,
                "p95_ms": 6500,
                "p99_ms": 9200,
            },
            "hallucination": {
                "total_claims": 120,
                "hallucinated": 8,
                "rate": 0.067,
            },
        },
        {
            "run_id": "20250308_09-15-47_bench",
            "agent_id": "agent-gpt4o-web",
            "timestamp": "2025-03-08 09:15:47",
            "task_success": {"passed": 14, "total": 20, "rate": 0.70},
            "step_success": {"passed": 128, "total": 172, "rate": 0.744},
            "category_success": {
                "Web Search": {"passed": 42, "total": 50, "rate": 0.84},
                "SEC Filing Retrieval": {"passed": 22, "total": 35, "rate": 0.629},
                "Numerical Reasoning": {"passed": 35, "total": 45, "rate": 0.778},
                "Data Synthesis": {"passed": 29, "total": 42, "rate": 0.690},
            },
            "latency": {
                "avg_ms": 4100,
                "p50_ms": 3600,
                "p95_ms": 8200,
                "p99_ms": 11500,
            },
            "hallucination": {
                "total_claims": 115,
                "hallucinated": 14,
                "rate": 0.122,
            },
        },
        {
            "run_id": "20250305_18-02-11_bench",
            "agent_id": "agent-claude-lite",
            "timestamp": "2025-03-05 18:02:11",
            "task_success": {"passed": 15, "total": 20, "rate": 0.75},
            "step_success": {"passed": 135, "total": 170, "rate": 0.794},
            "category_success": {
                "Web Search": {"passed": 44, "total": 50, "rate": 0.88},
                "SEC Filing Retrieval": {"passed": 26, "total": 35, "rate": 0.743},
                "Numerical Reasoning": {"passed": 36, "total": 45, "rate": 0.80},
                "Data Synthesis": {"passed": 29, "total": 40, "rate": 0.725},
            },
            "latency": {
                "avg_ms": 3500,
                "p50_ms": 3000,
                "p95_ms": 7100,
                "p99_ms": 9800,
            },
            "hallucination": {
                "total_claims": 118,
                "hallucinated": 10,
                "rate": 0.085,
            },
        },
    ]


class SkillFileMetadata(BaseModel):
    name: str
    size: int | None = None
    type: str | None = None


class SkillCreate(BaseModel):
    name: str
    description: str = ""
    definition: str = ""
    files: list[SkillFileMetadata] | None = None


class SkillUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    definition: str | None = None


@app.get("/api/skills")
async def list_skills():
    skills = sorted(_SKILLS.values(), key=lambda s: str(s.get("created_at", "")))
    return skills


@app.get("/api/skills/{skill_id}")
async def get_skill(skill_id: str):
    if skill_id not in _SKILLS:
        raise HTTPException(status_code=404, detail="Skill not found")
    return _SKILLS[skill_id]


@app.post("/api/skills", status_code=201)
async def create_skill(body: SkillCreate):
    skill_id = f"user_{body.name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:6]}"
    now = _now_iso()
    file_dicts = [f.model_dump(exclude_none=True) for f in body.files] if body.files else []
    skill = {
        "id": skill_id,
        "name": body.name,
        "description": body.description,
        "type": "user",
        "files": file_dicts,
        "definition": body.definition,
        "created_at": now,
        "updated_at": now,
    }
    _SKILLS[skill_id] = skill
    skill_dir = os.path.join(_SKILLS_DIR, skill_id)
    os.makedirs(skill_dir, exist_ok=True)
    frontmatter = f'---\nname: "{body.name}"\ndescription: "{body.description}"\n---\n\n'
    with open(os.path.join(skill_dir, "SKILL.md"), "w") as f:
        f.write(frontmatter + body.definition)
    return skill


@app.patch("/api/skills/{skill_id}")
async def update_skill(skill_id: str, body: SkillUpdate):
    if skill_id not in _SKILLS:
        raise HTTPException(status_code=404, detail="Skill not found")
    skill = _SKILLS[skill_id]
    if body.name is not None:
        skill["name"] = body.name
    if body.description is not None:
        skill["description"] = body.description
    if body.definition is not None:
        skill["definition"] = body.definition
        skill_md = os.path.join(_SKILLS_DIR, skill_id, "SKILL.md")
        if os.path.isfile(skill_md):
            frontmatter = f'---\nname: "{skill["name"]}"\ndescription: "{skill["description"]}"\n---\n\n'
            with open(skill_md, "w") as f:
                f.write(frontmatter + body.definition)
    skill["updated_at"] = _now_iso()
    return skill


@app.post("/api/skills/{skill_id}/files")
async def add_skill_files(skill_id: str, files: list[SkillFileMetadata]):
    if skill_id not in _SKILLS:
        raise HTTPException(status_code=404, detail="Skill not found")
    skill = _SKILLS[skill_id]
    existing_names = {f["name"] for f in skill["files"]}
    for f in files:
        if f.name not in existing_names:
            skill["files"].append(f.model_dump(exclude_none=True))
            existing_names.add(f.name)
    skill["updated_at"] = _now_iso()
    return skill


@app.delete("/api/skills/{skill_id}/files/{filename}")
async def remove_skill_file(skill_id: str, filename: str):
    if skill_id not in _SKILLS:
        raise HTTPException(status_code=404, detail="Skill not found")
    skill = _SKILLS[skill_id]
    skill["files"] = [f for f in skill["files"] if f["name"] != filename]
    skill["updated_at"] = _now_iso()
    return skill


@app.delete("/api/skills/{skill_id}")
async def delete_skill(skill_id: str):
    if skill_id not in _SKILLS:
        raise HTTPException(status_code=404, detail="Skill not found")
    if _SKILLS[skill_id]["type"] == "builtin":
        raise HTTPException(status_code=403, detail="Cannot delete builtin skills")
    del _SKILLS[skill_id]
    skill_dir = os.path.join(_SKILLS_DIR, skill_id)
    if os.path.isdir(skill_dir):
        shutil.rmtree(skill_dir)
    return {"ok": True}


@app.get("/api/skills/{skill_id}/files/{filename:path}")
async def get_skill_file_content(skill_id: str, filename: str):
    if skill_id not in _SKILLS:
        raise HTTPException(status_code=404, detail="Skill not found")
    skill_files = _FILE_CONTENTS.get(skill_id, {})
    if filename in skill_files:
        return {"filename": filename, "content": skill_files[filename]}
    file_exists = any(f["name"] == filename for f in _SKILLS[skill_id].get("files", []))
    if file_exists:
        return {"filename": filename, "content": f"# {filename}\n\n(File content placeholder)"}
    raise HTTPException(status_code=404, detail="File not found")


@app.post("/api/skills/train")
async def train_skills(files: list[UploadFile] = File(...)):
    """Accept media uploads, run MMSkillTrainer, return newly created skills."""
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    tmp_dir = tempfile.mkdtemp(prefix="mm_train_")
    try:
        saved_paths: list[str] = []
        for upload in files:
            dest = os.path.join(tmp_dir, upload.filename)
            with open(dest, "wb") as f:
                content = await upload.read()
                f.write(content)
            saved_paths.append(dest)

        existing_ids = set(_SKILLS.keys())

        trainer = MMSkillTrainer()
        await asyncio.to_thread(trainer.train, saved_paths)

        refreshed = _load_skills_from_disk()
        new_skills = []
        for sid, skill in refreshed.items():
            if sid not in existing_ids:
                _SKILLS[sid] = skill
                new_skills.append(skill)
            else:
                _SKILLS[sid] = skill

        return new_skills
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


_SKILLSBENCH_ROOT = Path(__file__).resolve().parent / "skillsbench"
_SKILLSBENCH_RUNS = _SKILLSBENCH_ROOT / "experiments" / "skill-eval-runs"


@app.get("/api/agent-skills")
async def get_agent_skills():
    """Return agent→skills mapping from agent_skills.json, with display names resolved."""
    path = _SKILLSBENCH_ROOT / "agent_skills.json"
    if not path.is_file():
        return {}
    with open(path) as f:
        data = json.load(f)
    for agent_data in data.values():
        agent_data["skill_details"] = [
            {"id": sid, "name": _SKILLS.get(sid, {}).get("name", sid)}
            for sid in agent_data.get("skills", [])
        ]
    return data


@app.post("/api/skill-evals/run", status_code=202)
async def run_skill_eval(agent_id: str):
    """For each skill of the agent, run eval only if no existing result exists."""
    agent_skills_path = _SKILLSBENCH_ROOT / "agent_skills.json"
    if not agent_skills_path.is_file():
        raise HTTPException(status_code=404, detail="agent_skills.json not found")
    with open(agent_skills_path) as f:
        agent_skills_data = json.load(f)
    skill_ids = agent_skills_data.get(agent_id, {}).get("skills", [])

    # Collect skill names that already have eval results
    existing_names: set[str] = set()
    if _SKILLSBENCH_RUNS.is_dir():
        for run_dir in _SKILLSBENCH_RUNS.iterdir():
            summary = run_dir / "evaluation_summary.json"
            if summary.is_file():
                with open(summary) as f:
                    d = json.load(f)
                name = d.get("inputs", {}).get("selected_skill_name")
                if name:
                    existing_names.add(name)

    script = _SKILLSBENCH_ROOT / "experiments" / "skill_evaluation_framework.py"
    venv_bin = _SKILLSBENCH_ROOT / ".venv" / "bin"
    py_bin = str(venv_bin / "python") if (venv_bin / "python").exists() else "python3"
    env = {**os.environ, "PYTHONUNBUFFERED": "1", "PATH": f"{venv_bin}:{os.environ.get('PATH', '')}"}

    ran, skipped = [], []
    for skill_id in skill_ids:
        skill_name = _SKILLS.get(skill_id, {}).get("name", skill_id)
        if skill_name in existing_names:
            skipped.append(skill_id)
            continue
        asyncio.create_task(
            asyncio.create_subprocess_exec(
                py_bin, str(script),
                "--skills-dir", str(_SKILLS_DIR),
                "--skill", skill_id,
                "--tasks-dir", str(_SKILLSBENCH_ROOT / "tasks"),
                "--workspace-dir", str(_SKILLSBENCH_RUNS),
                "--threshold", "0.357",
                "--embedding-model", "openai/text-embedding-3-small",
                "--base-config", str(_SKILLSBENCH_ROOT / "experiments" / "configs" / "sanity-check.yaml"),
                "--agent-name", "codex",
                "--model-name", "openai/gpt-5.2-codex",
                "--run",
                env=env,
                cwd=str(_SKILLSBENCH_ROOT),
            )
        )
        ran.append(skill_id)
    return {"ok": True, "ran": ran, "skipped": skipped}


@app.get("/api/skill-evals")
async def list_skill_evals():
    """Return skill evaluation runs from skillsbench experiments/skill-eval-runs."""
    results: list[dict[str, Any]] = []
    if not _SKILLSBENCH_RUNS.is_dir():
        return results
    for run_dir in sorted(_SKILLSBENCH_RUNS.iterdir(), reverse=True):
        if not run_dir.is_dir():
            continue
        summary_path = run_dir / "evaluation_summary.json"
        csv_path = run_dir / "evaluation_summary.csv"
        if not summary_path.is_file():
            continue
        with open(summary_path, encoding="utf-8") as f:
            summary = json.load(f)
        trials: list[dict[str, str]] = []
        if csv_path.is_file():
            with open(csv_path, encoding="utf-8") as f:
                trials = list(csv.DictReader(f))
        ev = summary.get("evaluation") or {}
        ev_no = summary.get("evaluation_no_skills") or {}

        def _adjusted_pass_rate(e: dict[str, Any]) -> float | None:
            p = e.get("pass_rate")
            scored = e.get("n_scored_trials")
            total = e.get("n_trials")
            if p is None or scored is None or total in (None, 0):
                return p
            return round(float(p) * int(scored) / int(total), 4)

        results.append(
            {
                "run_name": run_dir.name,
                "skill_name": summary.get("inputs", {}).get("selected_skill_name", run_dir.name),
                "model_name": summary.get("inputs", {}).get("model_name"),
                "created_at": summary.get("created_at_utc"),
                "selected_tasks": summary.get("selection", {}).get("selected_task_names", []),
                "pass_rate": _adjusted_pass_rate(ev),
                "mean_reward": ev.get("mean_reward"),
                "n_trials": ev.get("n_trials"),
                "pass_rate_no_skills": _adjusted_pass_rate(ev_no),
                "mean_reward_no_skills": ev_no.get("mean_reward"),
                "trials": trials,
            }
        )
    return results


# ---------------------------------------------------------------------------
# Workspace browsing endpoints
# ---------------------------------------------------------------------------

_TEXT_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".md", ".txt",
    ".yml", ".yaml", ".toml", ".cfg", ".ini", ".env", ".sh", ".bash",
    ".css", ".html", ".htm", ".xml", ".sql", ".rs", ".go", ".java",
    ".c", ".cpp", ".h", ".hpp", ".rb", ".lua", ".r", ".csv", ".log",
    ".gitignore", ".dockerfile", ".makefile",
}


def _is_text_file(path: str) -> bool:
    """Heuristic: consider file as text if extension is known or file is small."""
    ext = os.path.splitext(path)[1].lower()
    name = os.path.basename(path).lower()
    if ext in _TEXT_EXTENSIONS or name in {"makefile", "dockerfile", ".gitignore", ".env"}:
        return True
    # For unknown extensions, try reading a small chunk
    if ext == "" or ext not in {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico",
                                  ".pdf", ".zip", ".tar", ".gz", ".exe", ".bin",
                                  ".so", ".dll", ".whl", ".pyc", ".class"}:
        try:
            with open(path, "rb") as f:
                chunk = f.read(512)
            chunk.decode("utf-8")
            return True
        except (UnicodeDecodeError, OSError):
            return False
    return False


def _build_tree(root: str, rel: str = "") -> list[dict]:
    """Recursively build a JSON-friendly directory tree."""
    full = os.path.join(root, rel) if rel else root
    entries: list[dict] = []
    try:
        items = sorted(os.listdir(full))
    except PermissionError:
        return entries

    for name in items:
        if name.startswith("."):
            continue  # skip hidden files/dirs
        child_full = os.path.join(full, name)
        child_rel = os.path.join(rel, name) if rel else name
        if os.path.isdir(child_full):
            entries.append({
                "name": name,
                "path": child_rel,
                "type": "directory",
                "children": _build_tree(root, child_rel),
            })
        else:
            try:
                size = os.path.getsize(child_full)
            except OSError:
                size = 0
            entries.append({
                "name": name,
                "path": child_rel,
                "type": "file",
                "size": size,
            })
    return entries


def _safe_resolve(base: str, requested: str) -> str:
    """Resolve requested path and ensure it stays inside base. Raise 403 on traversal."""
    base_resolved = os.path.realpath(base)
    target = os.path.realpath(os.path.join(base_resolved, requested))
    if not target.startswith(base_resolved):
        raise HTTPException(status_code=403, detail="Path traversal blocked")
    return target


@app.get("/api/workspace/tree")
async def workspace_tree(path: str):
    """Return recursive file/directory tree for a given root path."""
    if not path or not os.path.isdir(path):
        raise HTTPException(status_code=400, detail="Invalid directory path")
    tree = _build_tree(path)
    return {"root": path, "tree": tree}


def _resolve_workspace_path(root: str, path: str) -> str:
    """Resolve ``path`` under ``root``; fall back to the shared host_dir.

    During an agent turn the agent writes into the shared DockerWorkspace
    bind-mount (``_SHARED_WS["host_dir"]``). Sync-back to the user's
    ``mount_dir`` only runs after the turn finishes, so files (especially
    binaries like PDFs/images that we can't embed in SSE) are temporarily
    invisible under ``root``. Treating the shared dir as a fallback makes
    those files reachable immediately.
    """
    if not root or not os.path.isdir(root):
        raise HTTPException(status_code=400, detail="Invalid root directory")
    full_path = _safe_resolve(root, path)
    if os.path.isfile(full_path):
        return full_path
    shared = _SHARED_WS.get("host_dir")
    if shared and os.path.isdir(shared):
        fallback = _safe_resolve(shared, path)
        if os.path.isfile(fallback):
            return fallback
    raise HTTPException(status_code=404, detail="File not found")


@app.get("/api/workspace/file")
async def workspace_file(root: str, path: str):
    """Return text content of a file inside a workspace root."""
    full_path = _resolve_workspace_path(root, path)
    if not _is_text_file(full_path):
        raise HTTPException(status_code=415, detail="Binary file — cannot display")
    try:
        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read(500_000)  # cap at 500KB
    except OSError as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"path": path, "content": content}


@app.get("/api/workspace/raw")
async def workspace_raw(root: str, path: str):
    """Stream a file's bytes as-is (used for PDFs, images, etc.)."""
    full_path = _resolve_workspace_path(root, path)

    media_type, _ = mimetypes.guess_type(full_path)
    if media_type is None:
        ext = os.path.splitext(full_path)[1].lower()
        if ext == ".pdf":
            media_type = "application/pdf"
        else:
            media_type = "application/octet-stream"

    headers = {"Content-Disposition": f'inline; filename="{os.path.basename(full_path)}"'}
    return FileResponse(full_path, media_type=media_type, headers=headers)


async def _run_native_picker(*args: str) -> tuple[int, str, str]:
    """Run a subprocess and capture stdout/stderr as text."""
    proc = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout_b, stderr_b = await proc.communicate()
    return (
        proc.returncode if proc.returncode is not None else 0,
        stdout_b.decode("utf-8", "replace"),
        stderr_b.decode("utf-8", "replace"),
    )


@app.post("/api/workspace/pick-directory")
async def pick_workspace_directory():
    """Open the host OS's native folder picker and return the selected path.

    Intended for local dev setups where the backend runs on the same machine
    as the user. For remote/headless deployments this returns a 501 and the
    frontend should fall back to typing a path manually.
    """
    plat = sys.platform

    try:
        if plat == "darwin":
            script = (
                'try\n'
                '    tell application "System Events" to activate\n'
                '    set theFolder to choose folder with prompt '
                '"Select workspace folder"\n'
                '    POSIX path of theFolder\n'
                'on error number -128\n'
                '    return ""\n'
                'end try'
            )
            code, out, err = await _run_native_picker("osascript", "-e", script)
            if code != 0:
                raise HTTPException(
                    status_code=500,
                    detail=err.strip() or "osascript failed",
                )
            path = out.strip().rstrip("/")
            return {
                "path": path or None,
                "cancelled": not path,
                "platform": "macOS",
            }

        if plat.startswith("linux"):
            if shutil.which("zenity"):
                code, out, err = await _run_native_picker(
                    "zenity",
                    "--file-selection",
                    "--directory",
                    "--title=Select workspace folder",
                )
                if code == 1:
                    return {"path": None, "cancelled": True, "platform": "Linux"}
                if code != 0:
                    raise HTTPException(
                        status_code=500,
                        detail=err.strip() or "zenity failed",
                    )
                return {
                    "path": out.strip() or None,
                    "cancelled": False,
                    "platform": "Linux",
                }
            if shutil.which("kdialog"):
                code, out, err = await _run_native_picker(
                    "kdialog",
                    "--getexistingdirectory",
                    os.path.expanduser("~"),
                    "--title",
                    "Select workspace folder",
                )
                if code != 0:
                    return {"path": None, "cancelled": True, "platform": "Linux"}
                return {
                    "path": out.strip() or None,
                    "cancelled": False,
                    "platform": "Linux",
                }
            raise HTTPException(
                status_code=501,
                detail="No native folder picker available on this host "
                "(install 'zenity' or 'kdialog')",
            )

        if plat in ("win32", "cygwin"):
            ps_script = (
                "Add-Type -AssemblyName System.Windows.Forms | Out-Null; "
                "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
                "$f.Description = 'Select workspace folder'; "
                "$f.ShowNewFolderButton = $true; "
                "if ($f.ShowDialog() -eq "
                "[System.Windows.Forms.DialogResult]::OK) "
                "{ Write-Output $f.SelectedPath }"
            )
            code, out, err = await _run_native_picker(
                "powershell",
                "-NoProfile",
                "-STA",
                "-Command",
                ps_script,
            )
            if code != 0:
                raise HTTPException(
                    status_code=500,
                    detail=err.strip() or "powershell failed",
                )
            path = out.strip()
            return {
                "path": path or None,
                "cancelled": not path,
                "platform": "Windows",
            }

        raise HTTPException(
            status_code=501,
            detail=f"Unsupported platform for native folder picker: {plat}",
        )
    except HTTPException:
        raise
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=501,
            detail=f"Native folder picker binary not found: {e}",
        ) from e
    except Exception as e:  # noqa: BLE001
        logger.exception("Native folder picker failed")
        raise HTTPException(status_code=500, detail=str(e)) from e


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "real_agent_enabled": REAL_AGENT_ENABLED,
    }
