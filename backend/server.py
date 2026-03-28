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
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from skills_ingestor.mm_train import MMSkillTrainer

dotenv.load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Real-agent feature flag
# ---------------------------------------------------------------------------
REAL_AGENT_ENABLED = True

_agent_import_error: str | None = None
if REAL_AGENT_ENABLED:
    try:
        from reflexion_agent.agent import runtime as _agent_runtime
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

app = FastAPI(title="Mock Reflexion Finance Agent API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------

_AGENTS: dict[str, dict] = {
    "agent-claude-full": {
        "id": "agent-claude-full",
        "name": "Equity Research Analyst",
        "model": "anthropic/claude-sonnet-4-5-20250929",
        "skills": ["web_search", "edgar_search", "parse_html", "retrieve_info"],
    },
    "agent-gpt4o-web": {
        "id": "agent-gpt4o-web",
        "name": "Market Intelligence Associate",
        "model": "openai/gpt-4o",
        "skills": ["web_search", "parse_html", "retrieve_info"],
    },
    "agent-claude-lite": {
        "id": "agent-claude-lite",
        "name": "Portfolio Risk Analyst",
        "model": "anthropic/claude-sonnet-4-5-20250929",
        "skills": ["web_search", "edgar_search", "parse_html"],
    },
    "agent-conversational": {
        "id": "agent-conversational",
        "name": "Financial Advisor Assistant",
        "model": "anthropic/claude-sonnet-4-5-20250929",
        "skills": [],
    },
}

_DEFAULT_TASK_AGENT = "agent-claude-full"
_DEFAULT_CHAT_AGENT = "agent-conversational"

_chats: dict[str, dict] = {}
_upload_dirs: dict[str, str] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_agent(model: str | None, is_task: bool = True) -> dict:
    """Pick the best matching agent for a given model string and query type."""
    if model:
        for agent in _AGENTS.values():
            if agent["model"] == model and (bool(agent["skills"]) == is_task):
                return agent
    return _AGENTS[_DEFAULT_TASK_AGENT if is_task else _DEFAULT_CHAT_AGENT]


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
        skills[skill] = {
            "id": skill,
            "name": " ".join(word.capitalize() for word in skill.split("-")),
            "description": "Placeholder description for the skill",
            "type": "builtin",
            "files": fs,
            "definition": open(skill_md).read(),
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


# _TASK_KEYWORDS = [
#     "revenue", "earnings", "stock", "market cap", "profit", "SEC",
#     "filing", "10-K", "10-Q", "annual report", "quarterly",
#     "dividend", "balance sheet", "cash flow", "EPS", "P/E",
#     "share price", "financial", "fiscal", "EBITDA", "debt",
#     "net income", "gross margin", "operating", "valuation",
#     "IPO", "acquisition", "merger", "GDP", "inflation",
# ]


# def _is_task(question: str) -> bool:
#     """Determine whether the query requires the agent to work (use tools) vs just chat."""
#     q = question.lower()
#     return any(kw in q for kw in _TASK_KEYWORDS)


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

                detail = str(
                    args_dict.get("command", args_dict.get("query", args_dict.get("path", "")))
                )[:120]

                _turn_counter.setdefault(session_id, 0)
                _turn_counter[session_id] += 1

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
            if text:
                return _sse("answer", {"text": text})
            return None

        # --- Errors ---
        if isinstance(event, AgentErrorEvent):
            return _sse("error", {"message": getattr(event, "error", str(event))})

        if isinstance(event, ConversationErrorEvent):
            msg = getattr(event, "message", None) or getattr(event, "error", None) or str(event)
            return _sse("error", {"message": msg})

    except Exception:
        logger.exception("Failed to map event to SSE: %s", type(event).__name__)

    return None


def _resolve_workspace(session_id: str, mount_dir: str | None) -> tuple[str | None, str | None]:
    """Determine the effective mount directory and any staging dir to clean up.

    If files were uploaded for this session, they live in a staging directory.
    - If ``mount_dir`` is also set, copy uploaded files into it and use ``mount_dir``.
    - Otherwise, use the staging directory itself as the mount.

    Returns (effective_mount_dir, staging_dir_to_cleanup_or_None).
    """
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


async def _stream_real_task(
    question: str,
    session_id: str,
    agent_info: dict,
    mount_dir: str | None = None,
):
    """Run the real OpenHands agent in a background thread, streaming events as SSE."""
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()

    effective_mount, staging_to_clean = _resolve_workspace(session_id, mount_dir)

    _turn_counter[session_id] = 0

    def _callback(event):
        mapped = _map_event_to_sse(event, session_id)
        if mapped:
            loop.call_soon_threadsafe(queue.put_nowait, mapped)

    def _run_agent():
        error = None
        try:
            _agent_runtime(
                repo_dir=effective_mount or "",
                instruction=question,
                mount_dir=effective_mount,
                event_callback=_callback,
            )
        except Exception as exc:
            error = str(exc)
            logger.exception("Agent runtime failed")
        finally:
            if staging_to_clean:
                shutil.rmtree(staging_to_clean, ignore_errors=True)
            if error:
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    _sse("error", {"message": error}),
                )
            loop.call_soon_threadsafe(queue.put_nowait, None)

    yield _sse("session", {"session_id": session_id})
    yield _sse("agent", agent_info)
    yield _sse("status", {"message": f"Agent starting work — model: {agent_info.get('model', 'unknown')}"})

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

    if not got_answer and last_tool_text:
        evt = {"text": last_tool_text}
        yield _sse("answer", evt)
        _append_event(session_id, "answer", evt)

    _turn_counter.pop(session_id, None)
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
    files: list[FileMetadata] | None = None
    mount_dir: str | None = None


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
        dest = os.path.join(staging, upload.filename)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        content = await upload.read()
        with open(dest, "wb") as f:
            f.write(content)
        saved.append({
            "name": upload.filename,
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

    if REAL_AGENT_ENABLED:
        gen = _stream_real_task(req.question, session_id, agent, mount_dir=req.mount_dir)
    else:
        gen = _stream_conversation(req.question, session_id, agent)

    return EventSourceResponse(gen)


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
    return list(_AGENTS.values())


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


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "real_agent_enabled": REAL_AGENT_ENABLED,
    }
