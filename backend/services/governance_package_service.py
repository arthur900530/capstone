"""Generate financial-services governance packages for digital employees."""

from __future__ import annotations

import html
import ast
import json
import logging
from datetime import datetime, timezone
from typing import Any

import config

logger = logging.getLogger(__name__)

POLICY_REFERENCES = [
    {
        "name": "Federal Reserve SR 11-7: Supervisory Guidance on Model Risk Management",
        "url": "https://www.federalreserve.gov/boarddocs/srletters/2011/sr1107a1.pdf",
        "summary": "Primary U.S. banking model-risk guidance for model development, validation, use, governance, controls, and ongoing monitoring.",
    },
    {
        "name": "OCC Bulletin 2011-12: Sound Practices for Model Risk Management",
        "url": "https://occ.gov/news-issuances/bulletins/2011/bulletin-2011-12a.pdf",
        "summary": "OCC model-risk guidance issued with SR 11-7 for banks supervised by the OCC.",
    },
    {
        "name": "NIST AI Risk Management Framework 1.0",
        "url": "https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-ai-rmf-10",
        "summary": "AI-specific risk-management framework organized around Govern, Map, Measure, and Manage functions.",
    },
]

SECTION_KEYS = (
    "system_overview",
    "intended_use",
    "data_inputs",
    "evaluation_summary",
    "risk_summary",
    "controls_summary",
    "monitoring_plan",
    "limitations",
    "approval_notes",
)

GOVERNANCE_PROMPT = (
    "You draft financial-services AI governance documentation. Use only the "
    "facts in the supplied JSON. Do not invent compliance, validation, approval, "
    "data-source, or performance claims. If a fact is missing, write "
    "'Not specified'. Do not state that the system complies with SR 11-7, OCC "
    "2011-12, or NIST AI RMF; say the document is aligned to those reference "
    "frameworks for review. Return strict JSON with string values for: "
    + ", ".join(SECTION_KEYS)
    + "."
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "Not specified"


def _risk_tier(employee: dict, metrics: dict) -> dict:
    aggregate = metrics.get("aggregate") or {}
    score = 0
    reasons: list[str] = []

    tasks = int(aggregate.get("tasks") or 0)
    avg_score = float(aggregate.get("avg_task_score") or 0.0)
    avg_rating = float(aggregate.get("avg_user_rating") or 0.0)
    tool_mix = aggregate.get("tool_mix") or []
    files = employee.get("files") or []

    if tasks == 0:
        score += 2
        reasons.append("No completed task evidence is available yet.")
    elif avg_score and avg_score < 0.75:
        score += 2
        reasons.append(f"Average task score is {_pct(avg_score)}, below the 75% review threshold.")
    elif avg_score and avg_score < 0.9:
        score += 1
        reasons.append(f"Average task score is {_pct(avg_score)}, which warrants monitoring.")

    if aggregate.get("unannotated_tasks"):
        score += 1
        reasons.append(f"{aggregate.get('unannotated_tasks')} task(s) lack trajectory annotations.")

    if avg_rating and avg_rating < 3.5:
        score += 1
        reasons.append(f"Average user rating is {avg_rating:.2f}/5.")

    if files:
        score += 1
        reasons.append(f"{len(files)} project file(s) are attached and should be reviewed for data sensitivity.")

    if any(str(tool).lower() in {"browser", "web_search", "file_editor"} for tool, _ in tool_mix):
        score += 1
        reasons.append("The employee uses external browsing or file-editing tools.")

    if employee.get("useReflexion"):
        reasons.append("Reflexion is enabled, adding automated retry and self-evaluation behavior.")

    if score >= 4:
        tier = "High"
    elif score >= 2:
        tier = "Medium"
    else:
        tier = "Low"

    if not reasons:
        reasons.append("Available evidence does not trigger elevated review thresholds.")

    return {"tier": tier, "score": score, "reasons": reasons}


def build_governance_context(employee: dict, metrics: dict) -> dict:
    aggregate = metrics.get("aggregate") or {}
    recent = metrics.get("recent") or []
    return {
        "document_type": "Financial Services AI Governance Package",
        "generated_at": _now_iso(),
        "employee": {
            "id": employee.get("id"),
            "name": employee.get("name") or "Not specified",
            "position": employee.get("position") or "Not specified",
            "description": employee.get("description") or "Not specified",
            "system_prompt_present": bool((employee.get("task") or "").strip()),
            "model": employee.get("model") or "Not specified",
            "plugins": employee.get("pluginIds") or [],
            "skills": employee.get("skillIds") or [],
            "project_files": [
                {
                    "name": f.get("name") or f.get("filename") or "Unnamed file",
                    "mime": f.get("mime") or f.get("type") or "Not specified",
                    "size": f.get("size") or "Not specified",
                }
                for f in (employee.get("files") or [])
            ],
            "use_reflexion": bool(employee.get("useReflexion")),
            "max_trials": employee.get("maxTrials"),
            "confidence_threshold": employee.get("confidenceThreshold"),
            "created_at": employee.get("createdAt") or "Not specified",
            "last_active_at": employee.get("lastActiveAt") or "Not specified",
        },
        "evaluation": {
            "source": metrics.get("source") or "Not specified",
            "tasks": aggregate.get("tasks", 0),
            "avg_task_score": aggregate.get("avg_task_score", 0.0),
            "avg_leaf_rate": aggregate.get("avg_leaf_rate", 0.0),
            "avg_user_rating": aggregate.get("avg_user_rating", 0.0),
            "rated_tasks": aggregate.get("rated_tasks", 0),
            "annotated_tasks": aggregate.get("annotated_tasks", 0),
            "unannotated_tasks": aggregate.get("unannotated_tasks", 0),
            "avg_tool_calls": aggregate.get("avg_tool_calls", 0.0),
            "avg_trials": aggregate.get("avg_trials", 0.0),
            "reflexion_rate": aggregate.get("reflexion_rate", 0.0),
            "tool_mix": aggregate.get("tool_mix") or [],
            "recent_task_count": len(recent),
        },
        "risk": _risk_tier(employee, metrics),
        "controls": [
            "Human review required before production financial-services use.",
            "Use only approved data sources and document any customer-impacting use case.",
            "Retain evaluation evidence, task traces, user ratings, and generated package versions for audit review.",
            "Revalidate after material prompt, model, tool, skill, or data-source changes.",
            "Escalate High risk tier packages to model-risk or governance reviewers before deployment.",
        ],
        "policy_references": POLICY_REFERENCES,
    }


def _template_draft(context: dict) -> dict:
    employee = context["employee"]
    evaluation = context["evaluation"]
    risk = context["risk"]
    return {
        "system_overview": (
            f"{employee['name']} is a digital employee for {employee['position']}. "
            f"The configured model is {employee['model']}; the system prompt is "
            f"{'present' if employee['system_prompt_present'] else 'not specified'}."
        ),
        "intended_use": employee.get("description") or "Not specified",
        "data_inputs": (
            f"{len(employee['project_files'])} project file(s) are attached. "
            "Specific production data sources must be reviewed before financial-services deployment."
        ),
        "evaluation_summary": (
            f"Evaluation evidence includes {evaluation['tasks']} task(s), "
            f"{evaluation['annotated_tasks']} annotated task(s), average task score "
            f"{_pct(evaluation['avg_task_score'])}, and average user rating "
            f"{evaluation['avg_user_rating'] or 'Not specified'}."
        ),
        "risk_summary": f"Current model-risk tier is {risk['tier']}: {' '.join(risk['reasons'])}",
        "controls_summary": " ".join(context["controls"]),
        "monitoring_plan": (
            "Monitor task outcomes, user ratings, trajectory annotations, tool usage, and material configuration changes."
        ),
        "limitations": (
            "This package is generated from available application evidence and is not an independent validation or legal compliance opinion."
        ),
        "approval_notes": "Not specified. Governance approval should be recorded by an authorized reviewer.",
    }


def _resolve_model_for_base_url(model: str) -> str:
    base_url = getattr(config, "BASE_URL", "https://api.openai.com/v1")
    if "api.openai.com" not in (base_url or ""):
        return model
    raw = (model or "").strip()
    while raw.startswith("openai/"):
        raw = raw.split("/", 1)[1]
    return raw or "gpt-4o-mini"


def _text_from_llm_section(value: Any, fallback: str) -> str:
    """Collapse LLM JSON values to readable prose instead of Python repr text."""
    if value in (None, ""):
        return fallback
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return fallback
        if (
            (text.startswith("{") and text.endswith("}"))
            or (text.startswith("[") and text.endswith("]"))
        ):
            try:
                return _text_from_llm_section(ast.literal_eval(text), fallback)
            except (ValueError, SyntaxError):
                try:
                    return _text_from_llm_section(json.loads(text), fallback)
                except json.JSONDecodeError:
                    pass
        return text
    if isinstance(value, list):
        items = [str(item).strip() for item in value if str(item).strip()]
        return " ".join(items) or fallback
    if isinstance(value, dict):
        parts: list[str] = []
        if value.get("tier"):
            parts.append(f"Tier: {value['tier']}.")
        if value.get("score") is not None:
            parts.append(f"Score: {value['score']}.")
        reasons = value.get("reasons")
        if isinstance(reasons, list) and reasons:
            parts.append(" ".join(str(reason).strip() for reason in reasons if str(reason).strip()))
        for key, item in value.items():
            if key in {"tier", "score", "reasons"}:
                continue
            if item not in (None, "", [], {}):
                parts.append(f"{str(key).replace('_', ' ').title()}: {item}.")
        return " ".join(parts).strip() or fallback
    return str(value)


async def generate_governance_package(employee: dict, metrics: dict) -> dict:
    context = build_governance_context(employee, metrics)
    draft = _template_draft(context)
    llm = {
        "available": bool(getattr(config, "API_KEY", None)),
        "used": False,
        "model": getattr(config, "GOVERNANCE_MODEL", "openai/gpt-4o-mini"),
        "error": None,
    }

    api_key = getattr(config, "API_KEY", None)
    base_url = getattr(config, "BASE_URL", "https://api.openai.com/v1")
    governance_model = getattr(config, "GOVERNANCE_MODEL", "openai/gpt-4o-mini")

    if api_key:
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=30.0)
            resp = await client.chat.completions.create(
                model=_resolve_model_for_base_url(governance_model),
                messages=[
                    {"role": "system", "content": GOVERNANCE_PROMPT},
                    {"role": "user", "content": json.dumps(context, ensure_ascii=True)},
                ],
                temperature=0.2,
                max_tokens=1600,
                response_format={"type": "json_object"},
            )
            content = (resp.choices[0].message.content or "").strip()
            parsed = json.loads(content)
            draft = {
                key: _text_from_llm_section(parsed.get(key), draft[key] or "Not specified")
                for key in SECTION_KEYS
            }
            # These two sections are most likely to be returned as raw JSON by
            # an LLM. Keep them deterministic and prose-shaped in the product.
            draft["risk_summary"] = _template_draft(context)["risk_summary"]
            draft["controls_summary"] = _template_draft(context)["controls_summary"]
            llm["used"] = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Governance LLM draft failed; using template fallback: %s", exc)
            llm["error"] = "LLM draft failed; template fallback used."

    return {
        "context": context,
        "sections": draft,
        "llm": llm,
        "disclaimer": (
            "Generated governance documentation is a review aid for financial-services governance. "
            "It does not establish legal, regulatory, model-risk, or compliance approval."
        ),
    }


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else "Not specified"))


def _section(title: str, body: str) -> str:
    return f"<section><h2>{_esc(title)}</h2><p>{_esc(body)}</p></section>"


def render_governance_html(package: dict) -> str:
    context = package["context"]
    sections = package["sections"]
    employee = context["employee"]
    risk = context["risk"]
    refs = "\n".join(
        f'<li><a href="{_esc(ref["url"])}">{_esc(ref["name"])}</a><span>{_esc(ref["summary"])}</span></li>'
        for ref in context["policy_references"]
    )
    controls = "\n".join(f"<li>{_esc(control)}</li>" for control in context["controls"])
    risk_reasons = "\n".join(f"<li>{_esc(reason)}</li>" for reason in risk["reasons"])

    body = "\n".join(
        _section(key.replace("_", " ").title(), sections[key])
        for key in SECTION_KEYS
    )

    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>{_esc(employee["name"])} Governance Package</title>
  <style>
    body {{ color: #172026; font-family: Arial, sans-serif; line-height: 1.5; margin: 40px; }}
    h1 {{ color: #0f4c5c; font-size: 28px; margin-bottom: 4px; }}
    h2 {{ border-bottom: 1px solid #d8dee4; color: #1f2937; font-size: 18px; margin-top: 28px; padding-bottom: 6px; }}
    .meta, .notice {{ color: #536471; font-size: 12px; }}
    .badge {{ background: #e9f5f7; border: 1px solid #b9dce2; border-radius: 999px; color: #0f4c5c; display: inline-block; font-size: 12px; font-weight: 700; padding: 4px 10px; }}
    section, .panel {{ break-inside: avoid; }}
    a {{ color: #05687f; }}
    li {{ margin: 6px 0; }}
    li span {{ color: #536471; display: block; font-size: 12px; }}
  </style>
</head>
<body>
  <h1>Financial Services AI Governance Package</h1>
  <p class="meta">Generated {_esc(context["generated_at"])} for {_esc(employee["name"])} · {_esc(employee["position"])}</p>
  <p><span class="badge">Risk tier: {_esc(risk["tier"])}</span></p>
  <p class="notice">{_esc(package["disclaimer"])}</p>
  <div class="panel">
    <h2>Reference Governance Policies</h2>
    <ul>{refs}</ul>
  </div>
  {body}
  <div class="panel">
    <h2>Deterministic Risk Drivers</h2>
    <ul>{risk_reasons}</ul>
  </div>
  <div class="panel">
    <h2>Required Controls</h2>
    <ul>{controls}</ul>
  </div>
</body>
</html>"""


async def render_governance_pdf(package: dict) -> bytes:
    from playwright.async_api import async_playwright

    html_doc = render_governance_html(package)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.set_content(html_doc, wait_until="networkidle")
        pdf = await page.pdf(format="Letter", print_background=True)
        await browser.close()
        return pdf
