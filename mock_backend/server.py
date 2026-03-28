"""
Mock backend for frontend development.

Simulates the real Reflexion Finance Agent API with realistic SSE streaming,
tool calls, self-evaluation, reflection loops, and evaluation data.

Run:  uvicorn server:app --reload --port 8000
"""

from __future__ import annotations

import os
import asyncio
import csv as _csv
import json
import pathlib as _pathlib
import random
import re
import shutil
import tempfile
import mimetypes
import uuid
import yaml as _yaml
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv
load_dotenv()

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from mm_train import MMSkillTrainer

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
        "description": "Deep-dive equity research covering SEC filings, earnings calls, and competitive landscape analysis. Produces structured investment memos.",
        "model": "anthropic/claude-sonnet-4-5-20250929",
        "skills": ["web_search", "edgar_search", "parse_html", "retrieve_info"],
        "status": "active",
        "department": "Investment Research",
        "created_at": "2026-01-15T09:00:00Z",
        "tasks_completed": 342,
        "avg_response_time_sec": 14.2,
    },
    "agent-gpt4o-web": {
        "id": "agent-gpt4o-web",
        "name": "Market Intelligence Associate",
        "description": "Real-time market surveillance, competitor tracking, and trend analysis across public web sources. Delivers concise intelligence briefs.",
        "model": "openai/gpt-4o",
        "skills": ["web_search", "parse_html", "retrieve_info"],
        "status": "active",
        "department": "Strategy",
        "created_at": "2026-02-03T11:30:00Z",
        "tasks_completed": 218,
        "avg_response_time_sec": 11.8,
    },
    "agent-claude-lite": {
        "id": "agent-claude-lite",
        "name": "Portfolio Risk Analyst",
        "description": "Quantitative risk modeling, stress testing, and VaR calculations. Monitors portfolio exposure and flags concentration risks.",
        "model": "anthropic/claude-sonnet-4-5-20250929",
        "skills": ["web_search", "edgar_search", "parse_html"],
        "status": "active",
        "department": "Risk Management",
        "created_at": "2026-02-10T14:00:00Z",
        "tasks_completed": 156,
        "avg_response_time_sec": 9.5,
    },
    "agent-conversational": {
        "id": "agent-conversational",
        "name": "Financial Advisor Assistant",
        "description": "Client-facing conversational agent for portfolio inquiries, product explanations, and general financial guidance.",
        "model": "anthropic/claude-sonnet-4-5-20250929",
        "skills": [],
        "status": "active",
        "department": "Client Services",
        "created_at": "2026-02-20T08:00:00Z",
        "tasks_completed": 89,
        "avg_response_time_sec": 6.3,
    },
    "agent-compliance": {
        "id": "agent-compliance",
        "name": "Compliance Review Officer",
        "description": "Automated compliance screening for trade surveillance, KYC document review, and regulatory filing verification.",
        "model": "openai/gpt-4o",
        "skills": ["edgar_search", "parse_html", "retrieve_info"],
        "status": "active",
        "department": "Legal & Compliance",
        "created_at": "2026-03-01T10:00:00Z",
        "tasks_completed": 67,
        "avg_response_time_sec": 18.4,
    },
    "agent-data-engineer": {
        "id": "agent-data-engineer",
        "name": "Data Pipeline Engineer",
        "description": "Builds and maintains ETL workflows, data quality checks, and automated reporting dashboards from structured financial data.",
        "model": "openai/gpt-4o-mini",
        "skills": ["parse_html", "retrieve_info"],
        "status": "idle",
        "department": "Data Engineering",
        "created_at": "2026-03-10T16:00:00Z",
        "tasks_completed": 31,
        "avg_response_time_sec": 8.1,
    },
}

_DEFAULT_TASK_AGENT = "agent-claude-full"
_DEFAULT_CHAT_AGENT = "agent-conversational"

_chats: dict[str, dict] = {}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_agent(model: str | None, is_task: bool) -> dict:
    """Pick the best matching agent for a given model string and query type."""
    if model:
        for agent in _AGENTS.values():
            if agent["model"] == model and (bool(agent["skills"]) == is_task):
                return agent
    return _AGENTS[_DEFAULT_TASK_AGENT if is_task else _DEFAULT_CHAT_AGENT]


_SKILLS: dict[str, dict] = {}


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


_TASK_KEYWORDS = [
    "revenue", "earnings", "stock", "market cap", "profit", "SEC",
    "filing", "10-K", "10-Q", "annual report", "quarterly",
    "dividend", "balance sheet", "cash flow", "EPS", "P/E",
    "share price", "financial", "fiscal", "EBITDA", "debt",
    "net income", "gross margin", "operating", "valuation",
    "IPO", "acquisition", "merger", "GDP", "inflation",
]


def _is_task(question: str) -> bool:
    """Determine whether the query requires the agent to work (use tools) vs just chat."""
    q = question.lower()
    return any(kw in q for kw in _TASK_KEYWORDS)


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


@app.post("/api/chat")
async def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    is_task = _is_task(req.question)
    agent = _resolve_agent(req.model, is_task)

    file_dicts = [f.model_dump(exclude_none=True) for f in req.files] if req.files else None
    _upsert_chat(session_id, req.question, role="user", agent_id=agent["id"], files=file_dicts)

    if is_task:
        gen = _stream_task(req.question, session_id, req.max_trials, req.confidence_threshold, agent)
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
async def create_skill(body: SkillCreate, background_tasks: BackgroundTasks):
    skill_id = f"user_{body.name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:6]}"
    skill = {
        "id": skill_id,
        "name": body.name,
        "description": body.description,
        "type": "skill",
        "files": [f.model_dump(exclude_none=True) for f in body.files] if body.files else [],
        "definition": body.definition,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    print(f"\n[skill pipeline] Step 1/3 — Writing '{body.name}' to skills-pool (id: {skill_id})")
    try:
        folder_name = _write_skill_to_pool(skill)
        _load_skills_from_pool()
        print(f"[skill pipeline] Step 2/3 — SKILL.md written to skills-pool/{folder_name}/")
        background_tasks.add_task(_run_skill_eval, folder_name)
        print(f"[skill pipeline] Step 3/3 — Evaluation scheduled (runs in background)")
    except Exception as e:
        print(f"[skill pipeline] ERROR — {e}")
    return _SKILLS.get(skill_id, skill)


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
    del _SKILLS[skill_id]
    return {"ok": True}


@app.get("/api/skills/{skill_id}/files/{filename:path}")
async def get_skill_file_content(skill_id: str, filename: str):
    if skill_id not in _SKILLS:
        raise HTTPException(status_code=404, detail="Skill not found")
    folder_name = skill_id.replace("_", "-")
    fpath = _SKILLS_POOL_DIR / folder_name / filename
    if fpath.exists() and fpath.is_file():
        return {"filename": filename, "content": fpath.read_text(encoding="utf-8")}
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

        _load_skills_from_pool()
        new_skills = [s for sid, s in _SKILLS.items() if sid not in existing_ids]

        return new_skills
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Skillsbench integration — skills pool, evaluation pipeline, eval results
# ---------------------------------------------------------------------------

_SKILLSBENCH_ROOT = _pathlib.Path(__file__).parent.parent / "skillsbench_backend"
_SKILLSBENCH_RUNS = _SKILLSBENCH_ROOT / "experiments" / "skill-eval-runs"
_SKILLS_POOL_DIR = _SKILLSBENCH_ROOT / "skills-pool"


def _yaml_safe_load(text: str) -> dict:
    return _yaml.safe_load(text) or {}


def _write_skill_to_pool(skill: dict) -> str:
    """Write a skill to skillsbench/skills-pool as a SKILL.md file. Returns folder name."""
    folder_name = skill["id"].replace("_", "-")
    skill_dir = _SKILLS_POOL_DIR / folder_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_md = skill_dir / "SKILL.md"

    definition_block = ""
    if skill.get("definition"):
        definition_block = f"\n## Definition\n\n```python\n{skill['definition']}\n```\n"

    content = (
        f"---\n"
        f"name: \"{skill['name']}\"\n"
        f"description: \"{skill.get('description', '').replace(chr(34), chr(39))}\"\n"
        f"---\n\n"
        f"# {skill['name']}\n\n"
        f"## Description\n\n"
        f"{skill.get('description', '')}\n"
        f"{definition_block}"
    )
    skill_md.write_text(content, encoding="utf-8")
    return folder_name


def _load_skills_from_pool() -> None:
    """Load all skills from skillsbench/skills-pool into _SKILLS on startup."""
    if not _SKILLS_POOL_DIR.exists():
        return
    for skill_dir in sorted(_SKILLS_POOL_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md_path = skill_dir / "SKILL.md"
        if not skill_md_path.exists():
            continue

        folder_name = skill_dir.name
        skill_id = folder_name.replace("-", "_")
        if skill_id in _SKILLS:
            continue

        content = skill_md_path.read_text(encoding="utf-8")
        parts = content.split("---", 2)
        fm = _yaml_safe_load(parts[1]) if len(parts) >= 3 else {}
        name = str(fm.get("name", folder_name))
        description = str(fm.get("description", ""))
        body = parts[2].strip() if len(parts) >= 3 else content

        fs = []
        for _root, _dirs, filenames in os.walk(skill_dir):
            for fname in filenames:
                rel = os.path.relpath(os.path.join(_root, fname), skill_dir)
                full = os.path.join(_root, fname)
                fs.append({"name": rel, "size": os.path.getsize(full), "type": mimetypes.guess_type(full)[0]})

        now = _now_iso()
        _SKILLS[skill_id] = {
            "id": skill_id,
            "name": name,
            "description": description,
            "type": "skill",
            "files": fs,
            "definition": body,
            "created_at": now,
            "updated_at": now,
        }
        print(f"[pool] Loaded '{name}'")


_load_skills_from_pool()


# ---------------------------------------------------------------------------
# Skill evaluation pipeline — config (override via environment variables)
# ---------------------------------------------------------------------------

_EVAL_THRESHOLD = os.getenv("EVAL_THRESHOLD", "0.357")
_EVAL_EMBEDDING_MODEL = os.getenv("EVAL_EMBEDDING_MODEL", "openai/text-embedding-3-small")
_EVAL_BASE_CONFIG = os.getenv("EVAL_BASE_CONFIG", "experiments/configs/sanity-check.yaml")
_EVAL_AGENT_NAME = os.getenv("EVAL_AGENT_NAME", "codex")
_EVAL_MODEL_NAME = os.getenv("EVAL_MODEL_NAME", "openai/gpt-5.2-codex")


async def _run_skill_eval(folder_name: str) -> None:
    """Run skill_evaluation_framework.py for a newly added skill (background task)."""
    venv_bin = _SKILLSBENCH_ROOT / ".venv" / "bin"
    python = venv_bin / "python3"

    if not python.exists():
        print(
            f"[skill eval] SKIPPED — skillsbench venv not found at {venv_bin}. "
            f"Set up the venv to enable automatic evaluation:\n"
            f"  cd {_SKILLSBENCH_ROOT} && python3 -m venv .venv && .venv/bin/pip install -e ."
        )
        return

    framework = _SKILLSBENCH_ROOT / "experiments" / "skill_evaluation_framework.py"
    if not framework.exists():
        print(f"[skill eval] SKIPPED — framework script not found at {framework}")
        return

    cmd = [
        str(python),
        "experiments/skill_evaluation_framework.py",
        "--skills-pool", "skills-pool",
        "--skill", folder_name,
        "--tasks-dir", "tasks",
        "--threshold", _EVAL_THRESHOLD,
        "--embedding-model", _EVAL_EMBEDDING_MODEL,
        "--base-config", _EVAL_BASE_CONFIG,
        "--agent-name", _EVAL_AGENT_NAME,
        "--model-name", _EVAL_MODEL_NAME,
        "--run",
    ]

    env = os.environ.copy()
    env["PATH"] = str(venv_bin) + ":" + env.get("PATH", "")
    env["VIRTUAL_ENV"] = str(_SKILLSBENCH_ROOT / ".venv")

    log_dir = _SKILLSBENCH_ROOT / "experiments" / "skill-eval-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{folder_name}.log"
    print(f"[skill eval] Starting evaluation for '{folder_name}' — log: {log_path}")
    print(f"[skill eval] Using python: {python}")
    with open(log_path, "w") as log_f:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(_SKILLSBENCH_ROOT),
            env=env,
            stdout=log_f,
            stderr=asyncio.subprocess.STDOUT,
        )
        print(f"[skill eval] Process started (pid {proc.pid}) — running skill_evaluation_framework.py ...")
        await proc.wait()
        if proc.returncode == 0:
            print(f"[skill eval] '{folder_name}' evaluation completed successfully (exit 0)")
        else:
            print(f"[skill eval] '{folder_name}' evaluation finished with exit code {proc.returncode} — check {log_path}")


_DEMO_EVALS = [
    {
        "run_name": "mesh-analysis-2026-03-25-1830",
        "skill_name": "Mesh Analysis",
        "model_name": "openai/gpt-5.1",
        "created_at": "2026-03-25T18:30:00Z",
        "selected_tasks": ["surface-area-cube", "volume-sphere", "normals-tetrahedron", "manifold-check"],
        "pass_rate": 0.85,
        "mean_reward": 0.82,
        "n_trials": 4,
        "pass_rate_no_skills": 0.50,
        "mean_reward_no_skills": 0.45,
        "trials": [
            {"trial_name": "trial-1", "task_name": "surface-area-cube", "reward": "1.0", "duration_sec": "12.3", "n_input_tokens": "1850", "n_output_tokens": "420"},
            {"trial_name": "trial-2", "task_name": "volume-sphere", "reward": "1.0", "duration_sec": "8.7", "n_input_tokens": "1620", "n_output_tokens": "380"},
            {"trial_name": "trial-3", "task_name": "normals-tetrahedron", "reward": "0.5", "duration_sec": "15.1", "n_input_tokens": "2100", "n_output_tokens": "510"},
            {"trial_name": "trial-4", "task_name": "manifold-check", "reward": "1.0", "duration_sec": "9.4", "n_input_tokens": "1730", "n_output_tokens": "350"},
        ],
    },
    {
        "run_name": "algorithmic-art-2026-03-24-1415",
        "skill_name": "Algorithmic Art",
        "model_name": "openai/gpt-4o",
        "created_at": "2026-03-24T14:15:00Z",
        "selected_tasks": ["fractal-tree", "voronoi-diagram", "perlin-landscape", "mandelbrot-zoom", "lissajous-curves"],
        "pass_rate": 0.72,
        "mean_reward": 0.68,
        "n_trials": 5,
        "pass_rate_no_skills": 0.40,
        "mean_reward_no_skills": 0.35,
        "trials": [
            {"trial_name": "trial-1", "task_name": "fractal-tree", "reward": "1.0", "duration_sec": "22.5", "n_input_tokens": "3200", "n_output_tokens": "890"},
            {"trial_name": "trial-2", "task_name": "voronoi-diagram", "reward": "1.0", "duration_sec": "18.3", "n_input_tokens": "2900", "n_output_tokens": "750"},
            {"trial_name": "trial-3", "task_name": "perlin-landscape", "reward": "0.0", "duration_sec": "25.8", "n_input_tokens": "3500", "n_output_tokens": "1020"},
            {"trial_name": "trial-4", "task_name": "mandelbrot-zoom", "reward": "0.5", "duration_sec": "30.1", "n_input_tokens": "3800", "n_output_tokens": "1150"},
            {"trial_name": "trial-5", "task_name": "lissajous-curves", "reward": "1.0", "duration_sec": "14.7", "n_input_tokens": "2400", "n_output_tokens": "620"},
        ],
    },
    {
        "run_name": "excel-worksheet-mgmt-2026-03-23-0900",
        "skill_name": "Excel Worksheet Management",
        "model_name": "anthropic/claude-sonnet-4-5-20250929",
        "created_at": "2026-03-23T09:00:00Z",
        "selected_tasks": ["pivot-table", "vlookup-migration", "conditional-formatting"],
        "pass_rate": 0.93,
        "mean_reward": 0.91,
        "n_trials": 3,
        "pass_rate_no_skills": 0.67,
        "mean_reward_no_skills": 0.60,
        "trials": [
            {"trial_name": "trial-1", "task_name": "pivot-table", "reward": "1.0", "duration_sec": "10.2", "n_input_tokens": "1500", "n_output_tokens": "400"},
            {"trial_name": "trial-2", "task_name": "vlookup-migration", "reward": "1.0", "duration_sec": "13.8", "n_input_tokens": "1800", "n_output_tokens": "520"},
            {"trial_name": "trial-3", "task_name": "conditional-formatting", "reward": "0.8", "duration_sec": "11.5", "n_input_tokens": "1650", "n_output_tokens": "460"},
        ],
    },
    {
        "run_name": "email-drafting-2026-03-22-1100",
        "skill_name": "Email Drafting",
        "model_name": "openai/gpt-4o-mini",
        "created_at": "2026-03-22T11:00:00Z",
        "selected_tasks": ["formal-reply", "meeting-request", "follow-up", "complaint-response", "newsletter"],
        "pass_rate": 0.46,
        "mean_reward": 0.42,
        "n_trials": 5,
        "pass_rate_no_skills": 0.38,
        "mean_reward_no_skills": 0.35,
        "trials": [
            {"trial_name": "trial-1", "task_name": "formal-reply", "reward": "1.0", "duration_sec": "6.1", "n_input_tokens": "980", "n_output_tokens": "310"},
            {"trial_name": "trial-2", "task_name": "meeting-request", "reward": "0.5", "duration_sec": "5.4", "n_input_tokens": "870", "n_output_tokens": "280"},
            {"trial_name": "trial-3", "task_name": "follow-up", "reward": "0.0", "duration_sec": "7.2", "n_input_tokens": "1100", "n_output_tokens": "350"},
            {"trial_name": "trial-4", "task_name": "complaint-response", "reward": "0.0", "duration_sec": "8.9", "n_input_tokens": "1300", "n_output_tokens": "420"},
            {"trial_name": "trial-5", "task_name": "newsletter", "reward": "0.5", "duration_sec": "9.5", "n_input_tokens": "1400", "n_output_tokens": "480"},
        ],
    },
]


@app.get("/api/skill-evals")
async def list_skill_evals():
    """Return skill evaluation runs from the skillsbench experiments folder."""
    results = []
    if _SKILLSBENCH_RUNS.exists():
        for run_dir in sorted(_SKILLSBENCH_RUNS.iterdir(), reverse=True):
            if not run_dir.is_dir():
                continue
            summary_path = run_dir / "evaluation_summary.json"
            csv_path = run_dir / "evaluation_summary.csv"
            if not summary_path.exists():
                continue
            with open(summary_path) as f:
                summary = json.load(f)
            trials = []
            if csv_path.exists():
                with open(csv_path) as f:
                    trials = list(_csv.DictReader(f))
            ev = summary.get("evaluation") or {}
            ev_no = summary.get("evaluation_no_skills") or {}

            def _adjusted_pass_rate(e: dict) -> float | None:
                p, scored, total = e.get("pass_rate"), e.get("n_scored_trials"), e.get("n_trials")
                return round(p * scored / total, 4) if (p and scored and total) else p

            results.append({
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
            })
    if not results:
        return _DEMO_EVALS
    return results


_DEMO_AGENT_EVALS = [
    {
        "run_id": "eval-era-2026-03-26",
        "agent_id": "agent-claude-full",
        "timestamp": "2026-03-26T10:00:00Z",
        "task_success": {"rate": 0.85, "passed": 34, "total": 40},
        "step_success": {"rate": 0.91, "passed": 182, "total": 200},
        "category_success": {
            "Financial Analysis": {"rate": 0.92, "passed": 11, "total": 12},
            "Data Retrieval":    {"rate": 0.88, "passed": 7, "total": 8},
            "Report Generation": {"rate": 0.84, "passed": 8, "total": 10},
            "Risk Assessment":   {"rate": 0.80, "passed": 8, "total": 10},
        },
        "latency": {"avg_ms": 14200, "p50_ms": 12800, "p95_ms": 22400, "p99_ms": 28600},
        "hallucination": {"rate": 0.04, "hallucinated": 3, "total_claims": 75},
    },
    {
        "run_id": "eval-mia-2026-03-25",
        "agent_id": "agent-gpt4o-web",
        "timestamp": "2026-03-25T16:00:00Z",
        "task_success": {"rate": 0.73, "passed": 22, "total": 30},
        "step_success": {"rate": 0.80, "passed": 120, "total": 150},
        "category_success": {
            "Market Research":     {"rate": 0.82, "passed": 9, "total": 11},
            "Competitive Analysis": {"rate": 0.74, "passed": 6, "total": 8},
            "Trend Forecasting":   {"rate": 0.68, "passed": 4, "total": 6},
            "Data Synthesis":      {"rate": 0.60, "passed": 3, "total": 5},
        },
        "latency": {"avg_ms": 11800, "p50_ms": 10200, "p95_ms": 19500, "p99_ms": 24100},
        "hallucination": {"rate": 0.08, "hallucinated": 5, "total_claims": 62},
    },
    {
        "run_id": "eval-pra-2026-03-25",
        "agent_id": "agent-claude-lite",
        "timestamp": "2026-03-25T12:00:00Z",
        "task_success": {"rate": 0.80, "passed": 20, "total": 25},
        "step_success": {"rate": 0.86, "passed": 108, "total": 125},
        "category_success": {
            "Risk Modeling":         {"rate": 0.86, "passed": 6, "total": 7},
            "Portfolio Optimization": {"rate": 0.82, "passed": 5, "total": 6},
            "Stress Testing":        {"rate": 0.78, "passed": 5, "total": 6},
            "Regulatory Compliance":  {"rate": 0.67, "passed": 4, "total": 6},
        },
        "latency": {"avg_ms": 9500, "p50_ms": 8400, "p95_ms": 15800, "p99_ms": 19200},
        "hallucination": {"rate": 0.05, "hallucinated": 3, "total_claims": 60},
    },
    {
        "run_id": "eval-faa-2026-03-24",
        "agent_id": "agent-conversational",
        "timestamp": "2026-03-24T18:00:00Z",
        "task_success": {"rate": 0.65, "passed": 13, "total": 20},
        "step_success": {"rate": 0.72, "passed": 72, "total": 100},
        "category_success": {
            "Client Communication": {"rate": 0.78, "passed": 7, "total": 9},
            "Product Explanation":  {"rate": 0.72, "passed": 4, "total": 5},
            "Compliance Guidance":  {"rate": 0.50, "passed": 1, "total": 2},
            "General Q&A":          {"rate": 0.25, "passed": 1, "total": 4},
        },
        "latency": {"avg_ms": 6300, "p50_ms": 5500, "p95_ms": 10200, "p99_ms": 13800},
        "hallucination": {"rate": 0.11, "hallucinated": 7, "total_claims": 64},
    },
    {
        "run_id": "eval-cro-2026-03-26",
        "agent_id": "agent-compliance",
        "timestamp": "2026-03-26T08:00:00Z",
        "task_success": {"rate": 0.80, "passed": 16, "total": 20},
        "step_success": {"rate": 0.88, "passed": 88, "total": 100},
        "category_success": {
            "Trade Surveillance":  {"rate": 0.88, "passed": 7, "total": 8},
            "KYC Review":          {"rate": 0.82, "passed": 4, "total": 5},
            "Regulatory Filing":   {"rate": 0.80, "passed": 3, "total": 4},
            "Policy Interpretation": {"rate": 0.67, "passed": 2, "total": 3},
        },
        "latency": {"avg_ms": 18400, "p50_ms": 16200, "p95_ms": 28500, "p99_ms": 34100},
        "hallucination": {"rate": 0.03, "hallucinated": 2, "total_claims": 58},
    },
    {
        "run_id": "eval-dpe-2026-03-25",
        "agent_id": "agent-data-engineer",
        "timestamp": "2026-03-25T20:00:00Z",
        "task_success": {"rate": 0.55, "passed": 8, "total": 15},
        "step_success": {"rate": 0.62, "passed": 47, "total": 75},
        "category_success": {
            "ETL Design":    {"rate": 0.65, "passed": 3, "total": 5},
            "Data Quality":  {"rate": 0.60, "passed": 2, "total": 3},
            "SQL Generation": {"rate": 0.50, "passed": 2, "total": 4},
            "Schema Mapping": {"rate": 0.33, "passed": 1, "total": 3},
        },
        "latency": {"avg_ms": 8100, "p50_ms": 7200, "p95_ms": 13400, "p99_ms": 16800},
        "hallucination": {"rate": 0.14, "hallucinated": 8, "total_claims": 57},
    },
]


@app.get("/api/evaluations")
async def evaluations():
    """Return agent-centric evaluation data."""
    return _DEMO_AGENT_EVALS


@app.get("/api/health")
async def health():
    return {"status": "ok"}
