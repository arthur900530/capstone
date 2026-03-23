"""
Mock backend for frontend development.

Simulates the real Reflexion Finance Agent API with realistic SSE streaming,
tool calls, self-evaluation, reflection loops, and evaluation data.

Run:  uvicorn server:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import csv as _csv
import json
import os
import pathlib as _pathlib
import random
import re
import uuid
import yaml as _yaml
from datetime import datetime, timezone
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

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


_SKILLS: dict[str, dict] = {
    "web_search": {
        "id": "web_search",
        "name": "Web Search",
        "description": "Search the web for real-time financial data, news articles, and market information using targeted queries.",
        "type": "builtin",
        "files": [
            {"name": "SKILL.md", "size": 2840, "type": "text/markdown"},
            {"name": "LICENSE", "size": 1065, "type": "text/plain"},
            {"name": "search_config.json", "size": 1240, "type": "application/json"},
            {"name": "query_templates.yaml", "size": 3420, "type": "application/x-yaml"},
            {"name": "examples.md", "size": 1580, "type": "text/markdown"},
        ],
        "definition": (
            "def web_search(query: str, max_results: int = 5) -> list[dict]:\n"
            '    """Search the web for financial information.\n\n'
            "    Args:\n"
            "        query: Search query string\n"
            "        max_results: Maximum number of results to return\n\n"
            "    Returns:\n"
            '        List of search results with title, url, and snippet\n    """\n'
            "    results = search_engine.query(query, limit=max_results)\n"
            "    return [\n"
            "        {\n"
            '            "title": r.title,\n'
            '            "url": r.url,\n'
            '            "snippet": r.snippet,\n'
            "        }\n"
            "        for r in results\n"
            "    ]\n"
        ),
        "created_at": "2025-01-15T10:00:00+00:00",
        "updated_at": "2025-01-15T10:00:00+00:00",
    },
    "edgar_search": {
        "id": "edgar_search",
        "name": "SEC Filing Search",
        "description": "Query the SEC EDGAR database to retrieve official company filings including 10-K, 10-Q, 8-K, and proxy statements.",
        "type": "builtin",
        "files": [
            {"name": "SKILL.md", "size": 3150, "type": "text/markdown"},
            {"name": "LICENSE", "size": 1065, "type": "text/plain"},
            {"name": "reference.md", "size": 4200, "type": "text/markdown"},
            {"name": "edgar_api_config.json", "size": 890, "type": "application/json"},
            {"name": "filing_types.csv", "size": 2100, "type": "text/csv"},
            {"name": "cik_lookup_cache.json", "size": 45200, "type": "application/json"},
            {"name": "scripts/validate_cik.py", "size": 1820, "type": "text/x-python"},
        ],
        "definition": (
            "def edgar_search(company: str, filing_type: str = '10-K', limit: int = 3) -> list[dict]:\n"
            '    """Search SEC EDGAR for company filings.\n\n'
            "    Args:\n"
            "        company: Company name or CIK number\n"
            "        filing_type: Type of filing (10-K, 10-Q, 8-K, etc.)\n"
            "        limit: Maximum filings to return\n\n"
            "    Returns:\n"
            '        List of filing metadata with download URLs\n    """\n'
            "    filings = edgar_client.search(\n"
            "        company=company,\n"
            "        form_type=filing_type,\n"
            "        count=limit,\n"
            "    )\n"
            "    return [\n"
            "        {\n"
            '            "filing_date": f.date,\n'
            '            "form_type": f.form_type,\n'
            '            "url": f.document_url,\n'
            '            "description": f.description,\n'
            "        }\n"
            "        for f in filings\n"
            "    ]\n"
        ),
        "created_at": "2025-01-15T10:00:00+00:00",
        "updated_at": "2025-01-15T10:00:00+00:00",
    },
    "parse_html": {
        "id": "parse_html",
        "name": "Parse HTML",
        "description": "Extract and clean readable text content from HTML pages, including financial tables, earnings reports, and news articles.",
        "type": "builtin",
        "files": [
            {"name": "SKILL.md", "size": 2210, "type": "text/markdown"},
            {"name": "LICENSE", "size": 1065, "type": "text/plain"},
            {"name": "parser_rules.json", "size": 5600, "type": "application/json"},
            {"name": "examples.md", "size": 980, "type": "text/markdown"},
        ],
        "definition": (
            "def parse_html(url: str, extract_tables: bool = True) -> dict:\n"
            '    """Fetch and parse an HTML page into structured content.\n\n'
            "    Args:\n"
            "        url: The URL to fetch and parse\n"
            "        extract_tables: Whether to extract HTML tables as structured data\n\n"
            "    Returns:\n"
            '        Dict with text content and optionally extracted tables\n    """\n'
            "    response = http_client.get(url)\n"
            "    soup = BeautifulSoup(response.text, 'html.parser')\n"
            "    text = soup.get_text(separator='\\n', strip=True)\n"
            "    result = {'text': text[:5000]}\n"
            "    if extract_tables:\n"
            "        result['tables'] = extract_html_tables(soup)\n"
            "    return result\n"
        ),
        "created_at": "2025-01-15T10:00:00+00:00",
        "updated_at": "2025-01-15T10:00:00+00:00",
    },
    "retrieve_info": {
        "id": "retrieve_info",
        "name": "Retrieve Information",
        "description": "Analyze and synthesize information from previously collected documents to extract specific financial data points and insights.",
        "type": "builtin",
        "files": [
            {"name": "SKILL.md", "size": 2960, "type": "text/markdown"},
            {"name": "LICENSE", "size": 1065, "type": "text/plain"},
            {"name": "STANDARDS.md", "size": 1740, "type": "text/markdown"},
        ],
        "definition": (
            "def retrieve_info(query: str, documents: list[str] | None = None) -> dict:\n"
            '    """Retrieve and synthesize information from collected documents.\n\n'
            "    Args:\n"
            "        query: What information to extract\n"
            "        documents: Optional list of document IDs to search within\n\n"
            "    Returns:\n"
            '        Dict with extracted info, sources, and confidence\n    """\n'
            "    context = document_store.search(query, doc_ids=documents)\n"
            "    synthesis = llm.synthesize(\n"
            "        query=query,\n"
            "        context=context,\n"
            "        instruction='Extract precise financial data with sources',\n"
            "    )\n"
            "    return {\n"
            "        'answer': synthesis.text,\n"
            "        'sources': [s.id for s in synthesis.sources],\n"
            "        'confidence': synthesis.confidence,\n"
            "    }\n"
        ),
        "created_at": "2025-01-15T10:00:00+00:00",
        "updated_at": "2025-01-15T10:00:00+00:00",
    },
}


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
async def create_skill(body: SkillCreate, background_tasks: BackgroundTasks):
    skill_id = f"user_{body.name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:6]}"
    skill = {
        "id": skill_id,
        "name": body.name,
        "description": body.description,
        "type": "user",
        "files": [f.model_dump(exclude_none=True) for f in body.files] if body.files else [],
        "definition": body.definition,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    print(f"\n[skill pipeline] Step 1/3 — Writing '{body.name}' to skills-pool (id: {skill_id})")
    try:
        folder_name = _write_skill_to_pool(skill)  # pool is source of truth
        _load_skills_from_pool()                    # sync cache from pool
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


_SKILLSBENCH_ROOT = _pathlib.Path(__file__).parent.parent.parent / "skillsbench"
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
    """Load all skills from skillsbench/skills-pool into _SKILLS on startup.

    - Provides persistence: user-created skills survive server restarts
      because they were already written to the pool on creation.
    - Makes pool skills (e.g. mesh-analysis, azure-bgp) visible in the
      frontend Skills tab without any frontend changes.
    - Skips builtin skills already registered in _SKILLS (e.g. web_search).
    """
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
            continue  # builtin already registered — don't overwrite

        content = skill_md_path.read_text(encoding="utf-8")
        parts = content.split("---", 2)
        fm = _yaml_safe_load(parts[1]) if len(parts) >= 3 else {}
        name = str(fm.get("name", folder_name))
        description = str(fm.get("description", ""))
        body = parts[2].strip() if len(parts) >= 3 else content

        skill_type = "user" if folder_name.startswith("user-") else "pool"
        now = _now_iso()
        _SKILLS[skill_id] = {
            "id": skill_id,
            "name": name,
            "description": description,
            "type": skill_type,
            "files": [],
            "definition": body,
            "created_at": now,
            "updated_at": now,
        }
        print(f"[pool] Loaded '{name}' ({skill_type})")


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
    """Run skill_evaluation_framework.py for a newly added skill (background task).

    Uses the skillsbench .venv python and prepends its bin/ to PATH so that
    harbor (installed there) is resolvable by the framework's subprocess calls.
    Logs to skillsbench/experiments/skill-eval-logs/<folder_name>.log.
    """
    venv_bin = _SKILLSBENCH_ROOT / ".venv" / "bin"
    python = str(venv_bin / "python3")

    cmd = [
        python,
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

    # Inherit the current environment but put the skillsbench venv bin first
    # so that `harbor` (and any other venv tools) are found by the framework.
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


@app.get("/api/skill-evals")
async def list_skill_evals():
    """Return skill evaluation runs from the skillsbench experiments folder."""
    results = []
    if not _SKILLSBENCH_RUNS.exists():
        return results
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
            """pass_rate from JSON excludes errored trials; scale back by n_scored/n_trials."""
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
    return results


@app.get("/api/health")
async def health():
    return {"status": "ok"}
