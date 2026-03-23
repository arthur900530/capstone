"""
Mock backend for frontend development.

Simulates the real Reflexion Finance Agent API with realistic SSE streaming,
tool calls, self-evaluation, reflection loops, and evaluation data.

Run:  uvicorn server:app --reload --port 8000
"""

from __future__ import annotations

import os
import asyncio
import json
import random
import re
import shutil
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile, File
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


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_agent(model: str | None, is_task: bool) -> dict:
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
                fs.append({"name": fname})
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


_SKILLS: dict[str, dict] = _load_skills_from_disk()
        

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
    skills = sorted(_SKILLS.values(), key=lambda s: s["created_at"])
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


_FILE_CONTENTS: dict[str, dict[str, str]] = {
    "web_search": {
        "SKILL.md": (
            "---\n"
            "name: web-search\n"
            "description: >-\n"
            "  Search the web for real-time financial data, news articles, and market\n"
            "  information using targeted queries.\n"
            "---\n\n"
            "# Web Search\n\n"
            "## Overview\n\n"
            "This skill searches the web for financial information using targeted queries.\n"
            "It supports multiple search engines and returns structured results with\n"
            "titles, URLs, and snippets.\n\n"
            "## Usage\n\n"
            "```python\n"
            "results = web_search(\"Apple Q4 2024 earnings report\")\n"
            "for r in results:\n"
            "    print(r['title'], r['url'])\n"
            "```\n\n"
            "## Parameters\n\n"
            "| Parameter | Type | Default | Description |\n"
            "|-----------|------|---------|-------------|\n"
            "| `query` | `str` | required | Search query string |\n"
            "| `max_results` | `int` | `5` | Maximum results to return |\n\n"
            "## Best Practices\n\n"
            "- Use specific financial terms in queries\n"
            "- Include company ticker symbols when possible\n"
            "- Combine with `parse_html` to extract full content from results\n"
        ),
        "LICENSE": (
            "MIT License\n\n"
            "Copyright (c) 2025 Reflexion Finance Agent\n\n"
            "Permission is hereby granted, free of charge, to any person obtaining a copy\n"
            "of this software and associated documentation files (the \"Software\"), to deal\n"
            "in the Software without restriction, including without limitation the rights\n"
            "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell\n"
            "copies of the Software, and to permit persons to whom the Software is\n"
            "furnished to do so, subject to the following conditions:\n\n"
            "The above copyright notice and this permission notice shall be included in all\n"
            "copies or substantial portions of the Software.\n\n"
            "THE SOFTWARE IS PROVIDED \"AS IS\", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\n"
            "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\n"
            "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.\n"
        ),
        "search_config.json": (
            '{\n'
            '  "engine": "google",\n'
            '  "timeout_ms": 5000,\n'
            '  "max_retries": 3,\n'
            '  "rate_limit_rps": 10,\n'
            '  "safe_search": true,\n'
            '  "default_max_results": 5,\n'
            '  "financial_domains_boost": [\n'
            '    "sec.gov",\n'
            '    "finance.yahoo.com",\n'
            '    "reuters.com",\n'
            '    "bloomberg.com",\n'
            '    "wsj.com"\n'
            '  ]\n'
            '}\n'
        ),
        "query_templates.yaml": (
            "templates:\n"
            "  earnings:\n"
            '    pattern: "{company} {quarter} {year} earnings report"\n'
            '    example: "Apple Q4 2024 earnings report"\n\n'
            "  sec_filing:\n"
            '    pattern: "{company} {filing_type} SEC filing {year}"\n'
            '    example: "Tesla 10-K SEC filing 2024"\n\n'
            "  stock_price:\n"
            '    pattern: "{company} stock price today market cap"\n'
            '    example: "Microsoft stock price today market cap"\n\n'
            "  financial_news:\n"
            '    pattern: "{company} latest financial news {topic}"\n'
            '    example: "Nvidia latest financial news AI revenue"\n'
        ),
        "examples.md": (
            "# Web Search Examples\n\n"
            "## Basic Search\n\n"
            "```python\n"
            "results = web_search(\"Apple revenue 2024\")\n"
            "# Returns 5 results from financial news sources\n"
            "```\n\n"
            "## Targeted Search\n\n"
            "```python\n"
            "results = web_search(\"AAPL 10-K SEC filing 2024\", max_results=3)\n"
            "# Returns top 3 results focused on SEC filings\n"
            "```\n\n"
            "## Combined with Parse HTML\n\n"
            "```python\n"
            "results = web_search(\"Tesla Q4 earnings\")\n"
            "for r in results:\n"
            "    content = parse_html(r['url'])\n"
            "    print(content['text'][:200])\n"
            "```\n"
        ),
    },
    "edgar_search": {
        "SKILL.md": (
            "---\n"
            "name: edgar-search\n"
            "description: >-\n"
            "  Query the SEC EDGAR database to retrieve official company filings\n"
            "  including 10-K, 10-Q, 8-K, and proxy statements.\n"
            "---\n\n"
            "# SEC Filing Search\n\n"
            "## Overview\n\n"
            "This skill queries the SEC EDGAR full-text search system to retrieve\n"
            "official company filings. It supports all major filing types and returns\n"
            "structured metadata with direct download links.\n\n"
            "## Supported Filing Types\n\n"
            "| Type | Description |\n"
            "|------|-------------|\n"
            "| 10-K | Annual report |\n"
            "| 10-Q | Quarterly report |\n"
            "| 8-K  | Current report (material events) |\n"
            "| DEF 14A | Proxy statement |\n"
            "| S-1  | Registration statement (IPO) |\n\n"
            "## Usage\n\n"
            "```python\n"
            "filings = edgar_search(\"Apple\", filing_type=\"10-K\", limit=3)\n"
            "```\n\n"
            "## Additional Resources\n\n"
            "- For complete EDGAR API reference, see [reference.md](reference.md)\n"
            "- For CIK validation, run `scripts/validate_cik.py`\n"
        ),
        "LICENSE": (
            "MIT License\n\n"
            "Copyright (c) 2025 Reflexion Finance Agent\n\n"
            "Permission is hereby granted, free of charge, to any person obtaining a copy\n"
            "of this software and associated documentation files (the \"Software\"), to deal\n"
            "in the Software without restriction, including without limitation the rights\n"
            "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell\n"
            "copies of the Software, and to permit persons to whom the Software is\n"
            "furnished to do so, subject to the following conditions:\n\n"
            "The above copyright notice and this permission notice shall be included in all\n"
            "copies or substantial portions of the Software.\n"
        ),
        "reference.md": (
            "# EDGAR API Reference\n\n"
            "## Base URL\n\n"
            "```\n"
            "https://efts.sec.gov/LATEST/search-index\n"
            "```\n\n"
            "## Authentication\n\n"
            "EDGAR EFTS requires a valid `User-Agent` header with contact information:\n\n"
            "```\n"
            "User-Agent: CompanyName admin@company.com\n"
            "```\n\n"
            "## Rate Limits\n\n"
            "- Maximum 10 requests per second\n"
            "- Respect `Retry-After` headers on 429 responses\n\n"
            "## Endpoints\n\n"
            "### Full-Text Search\n\n"
            "```\n"
            "GET /efts/search-index?q={query}&dateRange=custom&startdt={start}&enddt={end}&forms={type}\n"
            "```\n\n"
            "### Company Filings\n\n"
            "```\n"
            "GET /cgi-bin/browse-edgar?action=getcompany&CIK={cik}&type={form_type}&dateb=&owner=include&count={count}\n"
            "```\n"
        ),
        "edgar_api_config.json": (
            '{\n'
            '  "base_url": "https://efts.sec.gov/LATEST",\n'
            '  "user_agent": "ReflexionAgent research@example.com",\n'
            '  "rate_limit_rps": 10,\n'
            '  "timeout_ms": 10000,\n'
            '  "max_retries": 2\n'
            '}\n'
        ),
        "filing_types.csv": (
            "code,name,description\n"
            "10-K,Annual Report,Comprehensive annual financial report\n"
            "10-Q,Quarterly Report,Quarterly financial report\n"
            "8-K,Current Report,Report of material events or corporate changes\n"
            "DEF 14A,Proxy Statement,Definitive proxy statement\n"
            "S-1,Registration,Registration statement for new securities\n"
            "20-F,Foreign Annual,Annual report for foreign private issuers\n"
            "6-K,Foreign Current,Current report for foreign private issuers\n"
        ),
        "cik_lookup_cache.json": (
            '{\n'
            '  "AAPL": "0000320193",\n'
            '  "MSFT": "0000789019",\n'
            '  "GOOGL": "0001652044",\n'
            '  "AMZN": "0001018724",\n'
            '  "TSLA": "0001318605",\n'
            '  "META": "0001326801",\n'
            '  "NVDA": "0001045810",\n'
            '  "JPM": "0000019617",\n'
            '  "V": "0001403161"\n'
            '}\n'
        ),
        "scripts/validate_cik.py": (
            "#!/usr/bin/env python3\n"
            '"""Validate a CIK number against SEC EDGAR."""\n\n'
            "import sys\n"
            "import requests\n\n\n"
            "def validate_cik(cik: str) -> bool:\n"
            '    url = f"https://data.sec.gov/submissions/CIK{cik.zfill(10)}.json"\n'
            "    headers = {\"User-Agent\": \"ReflexionAgent research@example.com\"}\n"
            "    resp = requests.get(url, headers=headers, timeout=10)\n"
            "    if resp.status_code == 200:\n"
            "        data = resp.json()\n"
            '        print(f"Valid CIK: {cik} -> {data[\'name\']}")\n'
            "        return True\n"
            '    print(f"Invalid CIK: {cik} (HTTP {resp.status_code})")\n'
            "    return False\n\n\n"
            'if __name__ == "__main__":\n'
            "    if len(sys.argv) != 2:\n"
            '        print("Usage: python validate_cik.py <CIK>")\n'
            "        sys.exit(1)\n"
            "    valid = validate_cik(sys.argv[1])\n"
            "    sys.exit(0 if valid else 1)\n"
        ),
    },
    "parse_html": {
        "SKILL.md": (
            "---\n"
            "name: parse-html\n"
            "description: >-\n"
            "  Extract and clean readable text content from HTML pages, including\n"
            "  financial tables, earnings reports, and news articles.\n"
            "---\n\n"
            "# Parse HTML\n\n"
            "## Overview\n\n"
            "Fetches a URL and extracts clean, readable text. Optionally extracts\n"
            "HTML tables as structured data for financial analysis.\n\n"
            "## Usage\n\n"
            "```python\n"
            "result = parse_html(\"https://example.com/earnings\")\n"
            "print(result['text'][:500])\n"
            "print(result['tables'])  # List of extracted tables\n"
            "```\n\n"
            "## Parameters\n\n"
            "| Parameter | Type | Default | Description |\n"
            "|-----------|------|---------|-------------|\n"
            "| `url` | `str` | required | URL to fetch and parse |\n"
            "| `extract_tables` | `bool` | `True` | Extract HTML tables |\n"
        ),
        "LICENSE": (
            "MIT License\n\n"
            "Copyright (c) 2025 Reflexion Finance Agent\n\n"
            "Permission is hereby granted, free of charge, to any person obtaining a copy\n"
            "of this software and associated documentation files (the \"Software\"), to deal\n"
            "in the Software without restriction, including without limitation the rights\n"
            "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell\n"
            "copies of the Software.\n"
        ),
        "parser_rules.json": (
            '{\n'
            '  "strip_tags": ["script", "style", "nav", "footer", "header", "aside"],\n'
            '  "max_text_length": 5000,\n'
            '  "table_extraction": {\n'
            '    "enabled": true,\n'
            '    "min_rows": 2,\n'
            '    "min_cols": 2,\n'
            '    "detect_headers": true\n'
            '  },\n'
            '  "financial_patterns": {\n'
            '    "currency": "\\\\$[\\\\d,]+\\\\.?\\\\d*",\n'
            '    "percentage": "\\\\d+\\\\.?\\\\d*%",\n'
            '    "date": "\\\\d{4}-\\\\d{2}-\\\\d{2}"\n'
            '  }\n'
            '}\n'
        ),
        "examples.md": (
            "# Parse HTML Examples\n\n"
            "## Extract Article Text\n\n"
            "```python\n"
            "result = parse_html(\"https://reuters.com/article/apple-earnings\")\n"
            "print(result['text'])\n"
            "```\n\n"
            "## Extract Financial Tables\n\n"
            "```python\n"
            "result = parse_html(\"https://sec.gov/filing/10-K\", extract_tables=True)\n"
            "for table in result['tables']:\n"
            "    print(table['headers'])\n"
            "    for row in table['rows']:\n"
            "        print(row)\n"
            "```\n"
        ),
    },
    "retrieve_info": {
        "SKILL.md": (
            "---\n"
            "name: retrieve-info\n"
            "description: >-\n"
            "  Analyze and synthesize information from previously collected documents\n"
            "  to extract specific financial data points and insights.\n"
            "---\n\n"
            "# Retrieve Information\n\n"
            "## Overview\n\n"
            "This skill analyzes documents collected during the research phase\n"
            "and synthesizes answers to specific financial queries. It uses\n"
            "semantic search over the document store and LLM-based synthesis.\n\n"
            "## Usage\n\n"
            "```python\n"
            "result = retrieve_info(\"What was Apple's revenue in Q4 2024?\")\n"
            "print(result['answer'])\n"
            "print(result['confidence'])  # 0.0 to 1.0\n"
            "print(result['sources'])     # List of document IDs\n"
            "```\n\n"
            "## Best Practices\n\n"
            "- Ask specific, targeted questions\n"
            "- Specify document IDs when you know which sources to search\n"
            "- Check the confidence score before presenting results\n"
            "- For detailed quality standards, see [STANDARDS.md](STANDARDS.md)\n"
        ),
        "LICENSE": (
            "MIT License\n\n"
            "Copyright (c) 2025 Reflexion Finance Agent\n\n"
            "Permission is hereby granted, free of charge, to any person obtaining a copy\n"
            "of this software and associated documentation files (the \"Software\"), to deal\n"
            "in the Software without restriction, including without limitation the rights\n"
            "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell\n"
            "copies of the Software.\n"
        ),
        "STANDARDS.md": (
            "# Information Retrieval Quality Standards\n\n"
            "## Confidence Thresholds\n\n"
            "| Level | Score | Action |\n"
            "|-------|-------|--------|\n"
            "| High  | >= 0.8 | Present directly |\n"
            "| Medium | 0.5-0.8 | Present with caveat |\n"
            "| Low   | < 0.5 | Flag for manual review |\n\n"
            "## Source Requirements\n\n"
            "- At least 2 independent sources for financial claims\n"
            "- Primary sources (SEC filings) preferred over secondary\n"
            "- Data must be from within the last 12 months\n\n"
            "## Accuracy Checks\n\n"
            "- Cross-reference numerical data across sources\n"
            "- Flag discrepancies > 5% between sources\n"
            "- Verify units (millions vs billions, USD vs other)\n"
        ),
    },
}


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


@app.get("/api/health")
async def health():
    return {"status": "ok"}
