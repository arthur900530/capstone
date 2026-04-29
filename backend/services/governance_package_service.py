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
    "document_control_governance",
    "purpose_scope_intended_use",
    "model_data_overview",
    "risk_assessment_controls",
    "evaluation_outputs",
    "performance_testing_validation",
    "deployment_monitoring_lifecycle",
)

NARRATIVE_SECTION_KEYS = tuple(key for key in SECTION_KEYS if key != "evaluation_outputs")

GOVERNANCE_PROMPT = (
    "You draft financial-services AI governance documentation. Use the supplied "
    "JSON facts plus reasonable business inferences from the employee name, role, "
    "description, system prompt, selected skills/plugins, and recent user task "
    "prompts. Prefer inferred, clearly scoped governance content over writing "
    "'Not specified' when the intended use is reasonably apparent, such as KYC, "
    "customer due diligence, credit risk, reporting, research, or financial "
    "analysis. Prefix inferred items with 'Inferred from role/task context:' when "
    "the value is not explicitly stated. Do not invent measured evaluation "
    "results, compliance, validation, approval, exact owner names, exact data "
    "sources, or performance claims. Do not state that the system complies with "
    "SR 11-7, OCC "
    "2011-12, or NIST AI RMF; say the document is assembled for committee "
    "review against those reference frameworks. Do not assign a model-risk "
    "tier or make an approval recommendation. Write detailed, audit-ready "
    "bullet points. Return strict JSON where every key maps to an array of "
    "bullet strings for these narrative sections only: "
    + ", ".join(NARRATIVE_SECTION_KEYS)
    + ". Required section coverage: document_control_governance must cover model "
    "name/ID, owners, and intended audience; purpose_scope_intended_use must "
    "cover business objective, in-scope use, out-of-scope use, assumptions, "
    "limitations, and dependencies; model_data_overview must cover the "
    "agent architecture/workflow, model design/technique, training and inference "
    "data sources, lineage, quality checks, and third-party components; "
    "risk_assessment_controls must cover key risks, failure modes, human "
    "oversight, controls, guardrails, escalation, fallback, and policy alignment; "
    "performance_testing_validation must cover accuracy, acceptance criteria, "
    "testing approach, benchmarks, robustness, stability, hallucination, fairness, "
    "and misuse considerations; deployment_monitoring_lifecycle must cover "
    "implementation environment, access/logging, ongoing monitoring, drift "
    "detection, retraining or update strategy, and incident response."
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


def _compact_text(value: Any, limit: int = 4000) -> str:
    text = str(value or "").strip()
    return text[:limit]


def _role_context(employee: dict, evaluation: dict | None = None) -> dict:
    evaluation = evaluation or {}
    text_parts = [
        employee.get("name"),
        employee.get("position"),
        employee.get("description"),
        employee.get("system_prompt"),
        *[task.get("prompt") for task in evaluation.get("recent_tasks", [])[:5]],
    ]
    evidence = " ".join(str(part or "") for part in text_parts).lower()
    is_kyc = any(term in evidence for term in ("kyc", "know your customer", "customer due diligence", "cdd", "edd"))
    is_credit = any(term in evidence for term in ("credit", "borrower", "loan", "exposure"))
    is_reporting = any(term in evidence for term in ("report", "summar", "analysis", "analy"))

    if is_kyc:
        domain = "KYC / customer due diligence"
        objective = (
            "Inferred from role/task context: prepare KYC or customer-due-diligence "
            "reports that summarize a target company or counterparty, including "
            "identity, business profile, risk indicators, public-source findings, "
            "and items requiring human compliance review."
        )
        audience = (
            "Inferred from role/task context: KYC analysts, AML/compliance reviewers, "
            "client-onboarding teams, financial-crime risk managers, model-risk reviewers, "
            "and business stakeholders who review due-diligence outputs."
        )
        owner = (
            "Inferred from role/task context: business ownership should sit with the "
            "KYC/client-onboarding or financial-crime compliance function, with technical "
            "ownership by the digital-employee platform team and governance ownership by "
            "model-risk/AI-governance reviewers."
        )
        in_scope = (
            "Inferred from role/task context: draft KYC reports, summarize public or "
            "approved internal information about companies/counterparties, identify "
            "risk themes and missing information, and support analyst review."
        )
        out_scope = (
            "Inferred from role/task context: final onboarding approval, sanctions/AML "
            "clearance, regulatory filing, adverse-action decisions, or use of unapproved "
            "customer confidential data without separate authorization."
        )
    elif is_credit:
        domain = "credit risk analysis"
        objective = (
            "Inferred from role/task context: support credit-risk analysis and reporting "
            "by summarizing borrower or issuer information, exposure considerations, "
            "financial indicators, and risk themes for analyst review."
        )
        audience = (
            "Inferred from role/task context: credit analysts, portfolio managers, risk "
            "reviewers, governance reviewers, and business stakeholders."
        )
        owner = (
            "Inferred from role/task context: business ownership should sit with the "
            "credit-risk or portfolio-risk function, with technical ownership by the "
            "digital-employee platform team and governance ownership by model-risk reviewers."
        )
        in_scope = "Inferred from role/task context: draft credit-risk summaries, research support, and analyst-facing report generation."
        out_scope = "Inferred from role/task context: final credit approval, limit setting, regulatory attestation, or customer-impacting decisions without human approval."
    elif is_reporting:
        domain = "business analysis and report generation"
        objective = (
            "Inferred from role/task context: generate structured business reports and "
            "analysis from provided prompts, approved data, and available tool outputs."
        )
        audience = (
            "Inferred from role/task context: business users, analysts, reviewers, "
            "technology owners, and AI-governance stakeholders."
        )
        owner = (
            "Inferred from role/task context: business ownership should sit with the "
            "requesting business function, with technical ownership by the digital-employee "
            "platform team and governance ownership by AI/model-risk reviewers."
        )
        in_scope = "Inferred from role/task context: draft reports, summarize information, analyze provided data, and prepare decision-support materials."
        out_scope = "Inferred from role/task context: final business decisions, regulated attestations, or production actions without human review."
    else:
        domain = "general digital-employee assistance"
        objective = (
            "Inferred from role/task context: support professional business tasks using "
            "the configured system prompt, model, skills, plugins, and approved inputs."
        )
        audience = (
            "Inferred from role/task context: business users, analysts, operational "
            "reviewers, technology owners, and AI-governance stakeholders."
        )
        owner = (
            "Inferred from role/task context: business ownership should sit with the "
            "requesting function, with technical ownership by the digital-employee platform "
            "team and governance ownership by AI/model-risk reviewers."
        )
        in_scope = "Inferred from role/task context: draft professional outputs, perform analysis, summarize information, and assist with workflow execution."
        out_scope = "Inferred from role/task context: final approvals, regulated decisions, legal/compliance opinions, or production changes without human review."

    return {
        "domain": domain,
        "business_objective": objective,
        "intended_audience": audience,
        "owners": owner,
        "in_scope_use": in_scope,
        "out_of_scope_use": out_scope,
    }


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


def _mean_numeric(values: list[Any]) -> float | None:
    numeric = []
    for value in values:
        try:
            numeric.append(float(value))
        except (TypeError, ValueError):
            continue
    if not numeric:
        return None
    return sum(numeric) / len(numeric)


def _evaluation_lab_rollup(evaluation_runs: list[dict]) -> dict:
    task_rates = []
    step_rates = []
    hallucination_rates = []
    latency_avgs = []
    for run in evaluation_runs:
        task_rates.append((run.get("task_success") or {}).get("rate"))
        step_rates.append((run.get("step_success") or {}).get("rate"))
        hallucination_rates.append((run.get("hallucination") or {}).get("rate"))
        latency_avgs.append((run.get("latency") or {}).get("avg_ms"))
    return {
        "runs": len(evaluation_runs),
        "avg_task_success_rate": _mean_numeric(task_rates),
        "avg_step_success_rate": _mean_numeric(step_rates),
        "avg_hallucination_rate": _mean_numeric(hallucination_rates),
        "avg_latency_ms": _mean_numeric(latency_avgs),
    }


def build_governance_context(
    employee: dict,
    metrics: dict,
    evaluation_runs: list[dict] | None = None,
) -> dict:
    aggregate = metrics.get("aggregate") or {}
    recent = metrics.get("recent") or []
    evaluation_runs = evaluation_runs or []
    evaluation_lab_rollup = _evaluation_lab_rollup(evaluation_runs)
    recent_tasks = _recent_task_summaries(recent)
    raw_system_prompt = employee.get("task") or ""
    stored_model = employee.get("model") or "Not specified"
    runtime_model = getattr(config, "AGENT_MODEL", None) or stored_model
    employee_context = {
        "id": employee.get("id"),
        "name": employee.get("name") or "Not specified",
        "position": employee.get("position") or "Not specified",
        "description": employee.get("description") or "Not specified",
        "system_prompt_present": bool(raw_system_prompt.strip()),
        "system_prompt": _compact_text(raw_system_prompt),
        "model": runtime_model,
        "stored_model": stored_model,
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
    }
    inferred_use_context = _role_context(employee_context, {"recent_tasks": recent_tasks})
    return {
        "document_type": "Financial Services AI Governance Package",
        "generated_at": _now_iso(),
        "employee": employee_context,
        "inferred_use_context": inferred_use_context,
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
            "avg_reflections": aggregate.get("avg_reflections", 0.0),
            "avg_latency_ms": aggregate.get("avg_latency_ms", 0),
            "p50_latency_ms": aggregate.get("p50_latency_ms", 0),
            "p95_latency_ms": aggregate.get("p95_latency_ms", 0),
            "reflexion_rate": aggregate.get("reflexion_rate", 0.0),
            "output_stability_rate": round(
                (float(aggregate.get("avg_task_score") or 0.0)
                 * (1.0 - float(aggregate.get("reflexion_rate") or 0.0))),
                4,
            ),
            "hallucination_rate": evaluation_lab_rollup["avg_hallucination_rate"],
            "tool_mix": aggregate.get("tool_mix") or [],
            "recent_task_count": len(recent),
            "recent_tasks": recent_tasks,
            "evaluation_lab_runs": evaluation_runs,
            "evaluation_lab_summary": _evaluation_lab_summary(evaluation_runs),
            "evaluation_lab_rollup": evaluation_lab_rollup,
        },
        "risk_classifications": _risk_classifications(employee, metrics, evaluation_runs),
        "policy_references": POLICY_REFERENCES,
    }


def _template_draft(context: dict) -> dict:
    employee = context["employee"]
    evaluation = context["evaluation"]
    risk_classifications = context["risk_classifications"]
    inferred = context.get("inferred_use_context") or _role_context(employee, evaluation)
    return {
        "document_control_governance": [
            f"Model/agent name: {employee['name']}.",
            f"Model/agent ID: {employee.get('id') or 'Not specified'}.",
            f"Runtime model: {employee['model']}.",
            *(
                [f"Stored employee model selection: {employee.get('stored_model')} (runtime is governed by backend AGENT_MODEL)."]
                if employee.get("stored_model") and employee.get("stored_model") != employee.get("model")
                else []
            ),
            f"Owners: {inferred['owners']}",
            f"Intended audience: {inferred['intended_audience']}",
            f"Generated at: {context.get('generated_at') or 'Not specified'}.",
            "Document status: generated review aid; it is not an approval decision or independent validation report.",
        ],
        "purpose_scope_intended_use": [
            f"Business objective: {inferred['business_objective']}",
            f"In-scope usage: {inferred['in_scope_use']}",
            f"Out-of-scope usage: {inferred['out_of_scope_use']}",
            "Assumptions: users provide accurate task context, the employee uses only approved data/tooling, reviewers confirm data permissions, and downstream users verify material outputs before relying on them.",
            f"Limitations: generated from available application evidence; system prompt present is {employee['system_prompt_present']}; underlying model training data, exact production owner names, and final approval authority must be confirmed by reviewers.",
            f"Dependencies: configured model {employee['model']}, plugins {', '.join(employee.get('plugins') or []) or 'none configured'}, skills {', '.join(employee.get('skills') or []) or 'none configured'}, project files {len(employee['project_files'])}.",
        ],
        "model_data_overview": [
            f"Agent architecture/workflow: a user submits a {inferred['domain']} task to the digital employee; the configured system prompt, model, plugins, skills, and project files form the runtime context; the agent may call tools; outputs and trajectory events are captured for report-card metrics and governance review.",
            f"Model design/technique: LLM-backed agent configured with model {employee['model']}; Reflexion self-correction is {'enabled' if employee.get('use_reflexion') else 'disabled'}; max trials is {employee.get('max_trials') or 'Not specified'}; confidence threshold is {employee.get('confidence_threshold') or 'Not specified'}.",
            "Training data sources: underlying foundation-model training data is not exposed in application evidence; reviewers should treat provider training data, fine-tuning status, and model-card details as externally governed dependencies.",
            f"Inference data sources: user prompts and recent requested tasks, including {', '.join(task['prompt'] for task in evaluation.get('recent_tasks', [])[:3]) or 'no recent prompt captured'}, employee system prompt, selected skills/plugins, attached project files, generated test cases, task trajectories, and any tool outputs available during a task.",
            f"Project-file lineage: {len(employee['project_files'])} attached file(s): "
            + ("; ".join(f"{file['name']} ({file['mime']}, {file['size']} bytes)" for file in employee["project_files"]) or "none configured."),
            "Quality checks: report-card task scoring, trajectory annotations, user ratings, latency metrics, Evaluation Lab benchmark runs, hallucination checks, and governance refresh review.",
            f"Third-party components: model provider implied by configured model '{employee['model']}'; plugins {', '.join(employee.get('plugins') or []) or 'none configured'}; skills {', '.join(employee.get('skills') or []) or 'none configured'}.",
        ],
        "risk_assessment_controls": [
            *[
                f"{item['category']}: {item['classification']}. Evidence: {' '.join(item['evidence'])}"
                for item in risk_classifications
            ],
            "Key failure modes: inaccurate or incomplete reasoning, hallucinated facts, stale data, unauthorized data exposure, incorrect tool use, excessive latency, unstable outputs across retries, and over-reliance by downstream users.",
            "Human oversight: reviewers should verify material outputs, confirm data-source approval, challenge high-impact conclusions, and document any approval notes separately from the LLM-generated package.",
            "Controls and guardrails: role-scoped prompt, configured skills/plugins, project-file inventory, task logging, report-card metrics, Evaluation Lab metrics, approval-note capture, and refreshable governance package generation.",
            "Escalation and fallback: route exceptions, low scores, hallucination findings, tool failures, or policy-sensitive use cases to the designated owner; fall back to manual review or disable the employee pending remediation.",
            "Regulatory/policy alignment: assembled for review against SR 11-7, OCC 2011-12, and NIST AI RMF reference expectations without asserting compliance.",
        ],
        "performance_testing_validation": [
            "Accuracy and acceptance criteria should be based on report-card task score, top-level task achievement, step/leaf success, user rating, latency, hallucination rate, and documented reviewer acceptance thresholds.",
            f"Observed report-card source: {evaluation['source']}; tasks observed: {evaluation['tasks']}; annotated tasks: {evaluation['annotated_tasks']}; unannotated tasks: {evaluation['unannotated_tasks']}.",
            f"Observed task score: {_pct(evaluation['avg_task_score'])}; leaf-step success: {_pct(evaluation['avg_leaf_rate'])}; average user rating: {evaluation['avg_user_rating'] or 'Not specified'} across {evaluation['rated_tasks']} rated task(s).",
            f"Robustness/stability: output stability proxy is {_pct(evaluation.get('output_stability_rate'))}, derived from task score adjusted by retry/reflexion rate; reflexion rate is {_pct(evaluation.get('reflexion_rate'))}; average trials is {evaluation.get('avg_trials')}.",
            f"Hallucination: Evaluation Lab average hallucination rate is {_pct(evaluation.get('hallucination_rate'))}; detailed benchmark runs: {' '.join(evaluation.get('evaluation_lab_summary') or [])}.",
            "Fairness and misuse: not independently validated in the available evidence; reviewers should define protected-class, customer-harm, access-control, prompt-injection, and misuse tests before production use.",
        ],
        "deployment_monitoring_lifecycle": [
            "Implementation environment: application-hosted digital employee using configured model, prompt, plugins, skills, project files, tool execution, task-run storage, and governance package cache.",
            "Access/logging: task runs, tool counts, trajectories, ratings, project-file metadata, Evaluation Lab outputs, and governance approval notes are available as monitoring evidence when recorded by the application.",
            "Ongoing monitoring: track task score, leaf-step success, top-level achievement, user ratings, latency, tool mix, reflexion/retry rate, hallucination rate, output stability proxy, and material configuration changes.",
            "Drift detection: compare current report-card metrics and Evaluation Lab benchmark results against prior refreshes; investigate score degradation, latency changes, tool-mix shifts, rising hallucination rate, or reduced output stability.",
            "Retraining/update strategy: Not specified for the underlying model; prompt, skill, plugin, file, model, or threshold changes should trigger documented retesting and governance refresh.",
            "Incident response: suspend or restrict use, preserve logs, notify owners, perform root-cause analysis, update controls, rerun validation, and document remediation before reinstatement.",
        ],
    }


def evaluation_summary_items(context: dict) -> dict:
    evaluation = context.get("evaluation") or {}
    lab = evaluation.get("evaluation_lab_rollup") or {}
    return {
        "columns": ["Report card metric", "Value"],
        "rows": [
            ["Metric source", evaluation.get("source") or "Not specified"],
            ["Tasks observed", evaluation.get("tasks", 0)],
            ["Average task score", _pct(evaluation.get("avg_task_score"))],
            ["Average leaf-step success", _pct(evaluation.get("avg_leaf_rate"))],
            ["Average user rating", evaluation.get("avg_user_rating") or "Not specified"],
            ["Rated tasks", evaluation.get("rated_tasks", 0)],
            ["Annotated tasks", evaluation.get("annotated_tasks", 0)],
            ["Unannotated tasks", evaluation.get("unannotated_tasks", 0)],
            ["Average tool calls", evaluation.get("avg_tool_calls", 0.0)],
            ["Average trials", evaluation.get("avg_trials", 0.0)],
            ["Average reflections", evaluation.get("avg_reflections", 0.0)],
            ["Reflexion / retry rate", _pct(evaluation.get("reflexion_rate"))],
            ["Average latency", f"{evaluation.get('avg_latency_ms', 0)} ms"],
            ["P50 latency", f"{evaluation.get('p50_latency_ms', 0)} ms"],
            ["P95 latency", f"{evaluation.get('p95_latency_ms', 0)} ms"],
            ["Tool mix", "; ".join(f"{tool}: {count}" for tool, count in (evaluation.get("tool_mix") or [])) or "No tools recorded"],
            ["Recent task count", evaluation.get("recent_task_count", 0)],
            ["Evaluation Lab runs", lab.get("runs", 0)],
            ["Evaluation Lab task success", _pct(lab.get("avg_task_success_rate"))],
            ["Evaluation Lab step success", _pct(lab.get("avg_step_success_rate"))],
            ["Hallucination rate", _pct(evaluation.get("hallucination_rate"))],
            ["Output stability proxy", _pct(evaluation.get("output_stability_rate"))],
        ],
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


def _merge_inferred_bullets(generated: list[str], fallback: list[str]) -> list[str]:
    usable = [
        item for item in generated
        if item and "not specified" not in item.lower()
    ]
    if len(usable) >= max(3, len(generated) // 2):
        return generated
    merged = usable[:]
    seen = {item.lower() for item in merged}
    for item in fallback:
        key = item.lower()
        if key not in seen:
            merged.append(item)
            seen.add(key)
    return merged or fallback or ["Not specified"]


def normalize_governance_package(package: dict) -> dict:
    """Normalize older cached packages to the current UI-friendly shape."""
    context = package.get("context") or {}
    sections = package.setdefault("sections", {})
    if isinstance(sections.get("evaluation_summary"), str):
        sections["evaluation_summary"] = evaluation_summary_items(context)
    for old_key in (
        "system_overview",
        "intended_use",
        "system_metadata",
        "agent_activity",
        "risk_classifications",
        "data_inputs",
        "committee_review_focus",
        "monitoring_plan",
        "limitations",
    ):
        sections.pop(old_key, None)
    sections.pop("risk_summary", None)
    sections.pop("controls_summary", None)
    sections.pop("evaluation_summary", None)
    defaults = _template_draft(context) if context.get("employee") and context.get("evaluation") else {}
    for key in NARRATIVE_SECTION_KEYS:
        sections[key] = _bullets_from_section(
            sections.get(key),
            defaults.get(key, ["Not specified"]),
        )
        if defaults.get(key):
            sections[key] = _merge_inferred_bullets(sections[key], defaults[key])
    sections["evaluation_outputs"] = evaluation_summary_items(context)
    sections["approval_notes"] = _bullets_from_section(
        sections.get("approval_notes"),
        ["Not specified. Governance approval should be recorded by an authorized reviewer."],
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
                max_tokens=3200,
                response_format={"type": "json_object"},
            )
            content = (resp.choices[0].message.content or "").strip()
            parsed = json.loads(content)
            draft = {
                key: _bullets_from_section(parsed.get(key), draft[key])
                for key in NARRATIVE_SECTION_KEYS
            }
            draft["evaluation_outputs"] = evaluation_summary_items(context)
            # Approval notes are a reviewer/admin input field, not model prose.
            draft["approval_notes"] = [
                "Not specified. Governance approval should be recorded by an authorized reviewer."
            ]
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
        if isinstance(value.get("rows"), list):
            columns = value.get("columns") or ["Metric", "Value"]
            head = "".join(f"<th>{_esc(column)}</th>" for column in columns)
            rows = []
            for row in value.get("rows") or []:
                cells = row if isinstance(row, list) else [row]
                rows.append(
                    "<tr>"
                    + "".join(f"<td>{_esc(cell)}</td>" for cell in cells)
                    + "</tr>"
                )
            return f"<table><thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table>"
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
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border: 1px solid #d8dee4; padding: 8px; text-align: left; vertical-align: top; }}
    th {{ background: #f6f8fa; font-weight: 700; }}
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
