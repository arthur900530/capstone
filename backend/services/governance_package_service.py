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
    "system_metadata",
    "agent_activity",
    "evaluation_outputs",
    "risk_classifications",
    "data_inputs",
    "committee_review_focus",
    "monitoring_plan",
    "limitations",
    "approval_notes",
)

COMMITTEE_REVIEW_FOCUS = [
    "What business decision or workflow will this digital employee support?",
    "Who can be affected by the employee's outputs, including customers, analysts, or downstream control owners?",
    "What data sources are approved for this use case, and are any customer or confidential data elements involved?",
    "What independent validation, challenge, or human review is required before production use?",
    "What usage boundaries, monitoring, and escalation procedures should be required after approval?",
]

GOVERNANCE_PROMPT = (
    "You draft financial-services AI governance documentation. Use only the "
    "facts in the supplied JSON. Do not invent compliance, validation, approval, "
    "data-source, or performance claims. If a fact is missing, write "
    "'Not specified'. Do not state that the system complies with SR 11-7, OCC "
    "2011-12, or NIST AI RMF; say the document is assembled for committee "
    "review against those reference frameworks. Do not assign a model-risk "
    "tier or make an approval recommendation. Return strict JSON where every "
    "key maps to an array of concise bullet strings for: "
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


def _format_tool_mix(tool_mix: list) -> list[str]:
    if not tool_mix:
        return ["No tools recorded"]
    return [f"{tool}: {count}" for tool, count in tool_mix]


def _recent_task_summaries(recent: list[dict]) -> list[dict]:
    summaries: list[dict] = []
    for run in recent[:10]:
        tool_histogram = run.get("tool_histogram") or {}
        annotations = run.get("trajectory_annotations") or {}
        root_annotation = annotations.get("root") if isinstance(annotations, dict) else {}
        raw_events = run.get("raw_events") or []
        action_sequence = []
        for event in raw_events:
            if not isinstance(event, dict):
                continue
            label = event.get("tool") or event.get("type") or event.get("role")
            if label:
                action_sequence.append(str(label))
            if len(action_sequence) >= 8:
                break
        summaries.append({
            "prompt": run.get("prompt_preview") or "Not specified",
            "started_at": run.get("started_at") or "Not specified",
            "duration_ms": run.get("duration_ms") or 0,
            "tool_calls": run.get("n_tool_calls") or 0,
            "trials": run.get("n_trials") or 1,
            "reflections": run.get("n_reflections") or 0,
            "tools": _format_tool_mix(list(tool_histogram.items())),
            "action_sequence": action_sequence or ["No persisted action trace"],
            "task_score": run.get("task_score"),
            "user_rating": run.get("user_rating"),
            "annotated": bool(run.get("annotated")),
            "review_status": (
                root_annotation.get("status")
                if isinstance(root_annotation, dict)
                else None
            ),
        })
    return summaries


def _risk_classifications(employee: dict, metrics: dict, evaluation_runs: list[dict]) -> list[dict]:
    aggregate = metrics.get("aggregate") or {}
    tool_mix = aggregate.get("tool_mix") or []
    project_files = employee.get("files") or []
    classifications = [
        {
            "category": "Use-case and impact",
            "classification": "Committee determination required",
            "evidence": [
                f"Role: {employee.get('position') or 'Not specified'}",
                f"Intended use: {employee.get('description') or 'Not specified'}",
                "Business decision, customer impact, and exposure level must be confirmed by reviewers.",
            ],
        },
        {
            "category": "Data and confidentiality",
            "classification": "Review required" if project_files else "Not specified",
            "evidence": [
                f"Project files attached: {len(project_files)}",
                "Reviewers should determine whether customer, confidential, MNPI, or regulated data is in scope.",
            ],
        },
        {
            "category": "Tooling and external access",
            "classification": "Review required" if tool_mix else "Insufficient activity evidence",
            "evidence": [
                "Observed tools: " + "; ".join(_format_tool_mix(tool_mix)),
                "Reviewers should assess browser, file-editing, retrieval, and execution permissions before deployment.",
            ],
        },
        {
            "category": "Evaluation evidence",
            "classification": "Evidence available" if aggregate.get("tasks") else "Insufficient activity evidence",
            "evidence": [
                f"Employee task count: {aggregate.get('tasks', 0)}",
                f"Average task score: {_pct(aggregate.get('avg_task_score'))}",
                f"Unannotated tasks: {aggregate.get('unannotated_tasks', 0)}",
                f"Evaluation Lab runs available: {len(evaluation_runs)}",
            ],
        },
        {
            "category": "Operational oversight",
            "classification": "Review required",
            "evidence": [
                f"Reflexion enabled: {bool(employee.get('useReflexion'))}",
                f"Max trials: {employee.get('maxTrials') or 'Not specified'}",
                f"Confidence threshold: {employee.get('confidenceThreshold') or 'Not specified'}",
                "Reviewers should define human-in-the-loop, monitoring, escalation, and rollback expectations.",
            ],
        },
    ]
    return classifications


def _evaluation_lab_summary(evaluation_runs: list[dict]) -> list[str]:
    bullets: list[str] = []
    for run in evaluation_runs[:5]:
        task_success = run.get("task_success") or {}
        step_success = run.get("step_success") or {}
        hallucination = run.get("hallucination") or {}
        latency = run.get("latency") or {}
        bullets.append(
            f"{run.get('agent_id') or 'Unknown agent'} run {run.get('run_id') or 'unknown'}: "
            f"task success {_pct(task_success.get('rate'))} "
            f"({task_success.get('passed', 0)}/{task_success.get('total', 0)}), "
            f"step success {_pct(step_success.get('rate'))}, "
            f"hallucination rate {_pct(hallucination.get('rate'))}, "
            f"average latency {latency.get('avg_ms', 'Not specified')}ms."
        )
    return bullets or ["No Evaluation Lab benchmark runs available."]


def build_governance_context(
    employee: dict,
    metrics: dict,
    evaluation_runs: list[dict] | None = None,
) -> dict:
    aggregate = metrics.get("aggregate") or {}
    recent = metrics.get("recent") or []
    evaluation_runs = evaluation_runs or []
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
            "recent_tasks": _recent_task_summaries(recent),
            "evaluation_lab_runs": evaluation_runs,
            "evaluation_lab_summary": _evaluation_lab_summary(evaluation_runs),
        },
        "risk_classifications": _risk_classifications(employee, metrics, evaluation_runs),
        "committee_review_focus": COMMITTEE_REVIEW_FOCUS,
        "policy_references": POLICY_REFERENCES,
    }


def _template_draft(context: dict) -> dict:
    employee = context["employee"]
    evaluation = context["evaluation"]
    risk_classifications = context["risk_classifications"]
    return {
        "system_overview": [
            f"{employee['name']} is a digital employee for {employee['position']}.",
            f"Configured model: {employee['model']}.",
            f"System prompt present: {employee['system_prompt_present']}.",
            "This package is assembled for BNY governance committee review, not as an approval decision.",
        ],
        "intended_use": [
            f"Stated employee description: {employee.get('description') or 'Not specified'}.",
            "Committee reviewers should confirm the business decision, workflow, customer impact, and deployment boundary.",
        ],
        "system_metadata": [
            f"Employee ID: {employee.get('id') or 'Not specified'}.",
            f"Plugins: {', '.join(employee.get('plugins') or []) or 'None configured'}.",
            f"Skills: {', '.join(employee.get('skills') or []) or 'None configured'}.",
            f"Reflexion enabled: {employee.get('use_reflexion')}.",
            f"Max trials: {employee.get('max_trials') or 'Not specified'}.",
            f"Confidence threshold: {employee.get('confidence_threshold') or 'Not specified'}.",
            f"Created at: {employee.get('created_at')}.",
            f"Last active at: {employee.get('last_active_at')}.",
        ],
        "agent_activity": [
            f"Recent task count included in this package: {evaluation['recent_task_count']}.",
            f"Average tool calls per task: {evaluation['avg_tool_calls']}.",
            f"Observed tool mix: {'; '.join(_format_tool_mix(evaluation.get('tool_mix') or []))}.",
            *[
                f"Recent task: {task['prompt']} | tools {task['tool_calls']} | trials {task['trials']} | duration {task['duration_ms']}ms | actions: {', '.join(task['action_sequence'])} | review status: {task.get('review_status') or 'Not specified'}."
                for task in evaluation.get("recent_tasks", [])[:5]
            ],
        ],
        "evaluation_outputs": [
            f"Employee task metric source: {evaluation['source']}.",
            f"Tasks observed for this employee: {evaluation['tasks']}.",
            f"Average task score: {_pct(evaluation['avg_task_score'])}.",
            f"Average leaf rate: {_pct(evaluation['avg_leaf_rate'])}.",
            f"Average user rating: {evaluation['avg_user_rating'] or 'Not specified'} across {evaluation['rated_tasks']} rated task(s).",
            f"Annotated tasks: {evaluation['annotated_tasks']}; unannotated tasks: {evaluation['unannotated_tasks']}.",
            *evaluation.get("evaluation_lab_summary", []),
        ],
        "risk_classifications": [
            f"{item['category']} — {item['classification']}: {' '.join(item['evidence'])}"
            for item in risk_classifications
        ],
        "data_inputs": [
            f"Project files attached: {len(employee['project_files'])}.",
            *[
                f"{file['name']} ({file['mime']}, {file['size']} bytes)"
                for file in employee["project_files"]
            ],
            "Committee reviewers should confirm approved data sources, sensitivity, retention, and access controls.",
        ],
        "committee_review_focus": context["committee_review_focus"],
        "monitoring_plan": [
            "Monitor task outcomes, user ratings, trajectory annotations, tool usage, and material configuration changes.",
            "Define owner review cadence, exception escalation, rollback criteria, and reapproval triggers before deployment.",
            "Require committee review after material changes to model, prompt, tools, skills, data sources, or intended use.",
        ],
        "limitations": [
            "This package is generated from available application evidence and is not an independent validation or legal compliance opinion.",
            "The report does not approve deployment and does not claim compliance with SR 11-7, OCC 2011-12, or NIST AI RMF.",
            "Risk classifications are review prompts based on available evidence; final classification belongs to qualified BNY reviewers.",
        ],
        "approval_notes": ["Not specified. Governance approval should be recorded by an authorized reviewer."],
    }


def evaluation_summary_items(context: dict) -> dict:
    evaluation = context.get("evaluation") or {}
    return {
        "Source": evaluation.get("source") or "Not specified",
        "Tasks": evaluation.get("tasks", 0),
        "Average task score": _pct(evaluation.get("avg_task_score")),
        "Average leaf rate": _pct(evaluation.get("avg_leaf_rate")),
        "Average user rating": evaluation.get("avg_user_rating") or "Not specified",
        "Rated tasks": evaluation.get("rated_tasks", 0),
        "Annotated tasks": evaluation.get("annotated_tasks", 0),
        "Unannotated tasks": evaluation.get("unannotated_tasks", 0),
        "Average tool calls": evaluation.get("avg_tool_calls", 0.0),
        "Average trials": evaluation.get("avg_trials", 0.0),
        "Reflexion rate": _pct(evaluation.get("reflexion_rate")),
        "Tool mix": [
            f"{tool}: {count}"
            for tool, count in (evaluation.get("tool_mix") or [])
        ] or ["No tools recorded"],
        "Recent task count": evaluation.get("recent_task_count", 0),
    }


def _bullets_from_section(value: Any, fallback: list[str] | str) -> list[str]:
    """Normalize generated, cached, or LLM-returned section bodies to bullets."""
    fallback_items = fallback if isinstance(fallback, list) else [fallback]
    fallback_items = [str(item).strip() for item in fallback_items if str(item).strip()]
    if value in (None, "", [], {}):
        return fallback_items or ["Not specified"]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return fallback_items or ["Not specified"]
        if (
            (text.startswith("{") and text.endswith("}"))
            or (text.startswith("[") and text.endswith("]"))
        ):
            for parser in (json.loads, ast.literal_eval):
                try:
                    return _bullets_from_section(parser(text), fallback_items)
                except (ValueError, SyntaxError, json.JSONDecodeError):
                    continue
        lines = [
            line.strip(" \t-*•")
            for line in text.splitlines()
            if line.strip(" \t-*•")
        ]
        return lines or [text]
    if isinstance(value, list):
        bullets: list[str] = []
        for item in value:
            if isinstance(item, dict):
                for key, nested in item.items():
                    nested_text = "; ".join(_bullets_from_section(nested, []))
                    if nested_text:
                        bullets.append(f"{str(key).replace('_', ' ').title()}: {nested_text}")
            elif isinstance(item, list):
                bullets.extend(_bullets_from_section(item, []))
            else:
                text = str(item).strip()
                if text:
                    bullets.append(text)
        return bullets or fallback_items or ["Not specified"]
    if isinstance(value, dict):
        bullets = []
        for key, item in value.items():
            if item in (None, "", [], {}):
                continue
            item_text = "; ".join(_bullets_from_section(item, []))
            if item_text:
                bullets.append(f"{str(key).replace('_', ' ').title()}: {item_text}")
        return bullets or fallback_items or ["Not specified"]
    return [str(value)]


def normalize_governance_package(package: dict) -> dict:
    """Normalize older cached packages to the current UI-friendly shape."""
    context = package.get("context") or {}
    context.setdefault("committee_review_focus", COMMITTEE_REVIEW_FOCUS)
    sections = package.setdefault("sections", {})
    if isinstance(sections.get("evaluation_summary"), str):
        sections["evaluation_summary"] = evaluation_summary_items(context)
    sections.pop("risk_summary", None)
    sections.pop("controls_summary", None)
    sections.pop("evaluation_summary", None)
    sections.setdefault(
        "committee_review_focus",
        context.get("committee_review_focus") or COMMITTEE_REVIEW_FOCUS,
    )
    defaults = _template_draft(context) if context.get("employee") and context.get("evaluation") else {}
    for key in SECTION_KEYS:
        sections[key] = _bullets_from_section(
            sections.get(key),
            defaults.get(key, ["Not specified"]),
        )
    return package


def _resolve_model_for_base_url(model: str) -> str:
    base_url = getattr(config, "BASE_URL", "https://api.openai.com/v1")
    if "api.openai.com" not in (base_url or ""):
        return model
    raw = (model or "").strip()
    while raw.startswith("openai/"):
        raw = raw.split("/", 1)[1]
    return raw or "gpt-4o-mini"


def _text_from_llm_section(value: Any, fallback: str | list[str]) -> list[str]:
    """Backward-compatible alias for tests and older callers."""
    return _bullets_from_section(value, fallback)


async def generate_governance_package(
    employee: dict,
    metrics: dict,
    evaluation_runs: list[dict] | None = None,
) -> dict:
    context = build_governance_context(employee, metrics, evaluation_runs)
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
                key: _bullets_from_section(parsed.get(key), draft[key])
                for key in SECTION_KEYS
            }
            # Review focus and approval notes are human governance fields, not
            # model conclusions. Keep them deterministic in the product.
            draft["committee_review_focus"] = _template_draft(context)["committee_review_focus"]
            # Approval notes are a reviewer/admin input field, not model prose.
            draft["approval_notes"] = _template_draft(context)["approval_notes"]
            llm["used"] = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("Governance LLM draft failed; using template fallback: %s", exc)
            llm["error"] = "LLM draft failed; template fallback used."

    return normalize_governance_package({
        "context": context,
        "sections": draft,
        "llm": llm,
        "disclaimer": (
            "Generated governance documentation is a review aid for financial-services governance. "
            "It does not establish legal, regulatory, model-risk, or compliance approval."
        ),
    })


def _esc(value: Any) -> str:
    return html.escape(str(value if value is not None else "Not specified"))


def _html_value(value: Any) -> str:
    if value in (None, ""):
        return "<ul><li>Not specified</li></ul>"
    if isinstance(value, dict):
        rows = []
        for key, item in value.items():
            if isinstance(item, list):
                rendered = "<ul>" + "".join(f"<li>{_esc(entry)}</li>" for entry in item) + "</ul>"
            else:
                rendered = _esc(item)
            rows.append(f"<dt>{_esc(key)}</dt><dd>{rendered}</dd>")
        return "<dl>" + "".join(rows) + "</dl>"
    if isinstance(value, list):
        return "<ul>" + "".join(f"<li>{_esc(item)}</li>" for item in value) + "</ul>"
    return "<ul>" + f"<li>{_esc(value)}</li>" + "</ul>"


def _section(title: str, body: Any) -> str:
    return f"<section><h2>{_esc(title)}</h2>{_html_value(body)}</section>"


def render_governance_html(package: dict) -> str:
    package = normalize_governance_package(package)
    context = package["context"]
    sections = package["sections"]
    employee = context["employee"]
    refs = "\n".join(
        f'<li><a href="{_esc(ref["url"])}">{_esc(ref["name"])}</a><span>{_esc(ref["summary"])}</span></li>'
        for ref in context["policy_references"]
    )

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
    section, .panel {{ break-inside: avoid; }}
    a {{ color: #05687f; }}
    li {{ margin: 6px 0; }}
    li span {{ color: #536471; display: block; font-size: 12px; }}
    dl {{ display: grid; grid-template-columns: 180px 1fr; gap: 8px 16px; }}
    dt {{ font-weight: 700; }}
    dd {{ margin: 0; }}
  </style>
</head>
<body>
  <h1>Financial Services AI Governance Package</h1>
  <p class="meta">Generated {_esc(context["generated_at"])} for {_esc(employee["name"])} · {_esc(employee["position"])}</p>
  <p class="notice">{_esc(package["disclaimer"])}</p>
  <div class="panel">
    <h2>Reference Governance Policies</h2>
    <ul>{refs}</ul>
  </div>
  {body}
</body>
</html>"""
