import asyncio

from services import governance_package_service as svc


def _employee():
    return {
        "id": "emp-1",
        "name": "Credit Risk Analyst",
        "position": "Credit Risk",
        "description": "Reviews credit exposure and prepares risk summaries.",
        "task": "You are a credit risk analyst.",
        "model": "openai/gpt-4o-mini",
        "pluginIds": ["web-search"],
        "skillIds": ["edgar-search"],
        "useReflexion": True,
        "maxTrials": 3,
        "confidenceThreshold": 0.75,
        "files": [{"name": "portfolio.csv", "mime": "text/csv", "size": 1024}],
        "createdAt": "2026-01-01T00:00:00+00:00",
        "lastActiveAt": "2026-01-02T00:00:00+00:00",
    }


def _metrics():
    return {
        "source": "db",
        "aggregate": {
            "tasks": 4,
            "avg_task_score": 0.72,
            "avg_leaf_rate": 0.8,
            "avg_user_rating": 3.25,
            "rated_tasks": 2,
            "annotated_tasks": 3,
            "unannotated_tasks": 1,
            "avg_tool_calls": 2.5,
            "avg_trials": 1.5,
            "reflexion_rate": 0.25,
            "tool_mix": [["web_search", 3], ["file_editor", 1]],
        },
        "recent": [{"session_id": "s1"}],
    }


def _evaluation_runs():
    return [
        {
            "run_id": "bench-1",
            "agent_id": "agent-gpt4o-web",
            "task_success": {"passed": 14, "total": 20, "rate": 0.70},
            "step_success": {"passed": 128, "total": 172, "rate": 0.744},
            "latency": {"avg_ms": 4100},
            "hallucination": {"rate": 0.122},
        }
    ]


def test_build_governance_context_includes_financial_policy_references():
    context = svc.build_governance_context(_employee(), _metrics(), _evaluation_runs())

    names = [ref["name"] for ref in context["policy_references"]]
    assert any("SR 11-7" in name for name in names)
    assert any("OCC Bulletin 2011-12" in name for name in names)
    assert any("NIST AI Risk Management Framework" in name for name in names)
    assert "committee_review_focus" in context
    assert context["evaluation"]["evaluation_lab_runs"]
    assert context["risk_classifications"]
    assert "risk" not in context


def test_generate_governance_package_uses_template_without_api_key(monkeypatch):
    monkeypatch.setattr(svc.config, "API_KEY", None, raising=False)

    package = asyncio.run(svc.generate_governance_package(_employee(), _metrics(), _evaluation_runs()))

    assert package["llm"]["used"] is False
    assert package["sections"]["committee_review_focus"]
    assert package["sections"]["agent_activity"]
    assert package["sections"]["evaluation_outputs"]
    assert package["sections"]["risk_classifications"]
    assert all(isinstance(package["sections"][key], list) for key in svc.SECTION_KEYS)
    assert "risk_summary" not in package["sections"]
    assert "legal, regulatory" in package["disclaimer"]


def test_render_governance_html_links_policy_references():
    package = {
        "context": svc.build_governance_context(_employee(), _metrics()),
        "sections": {
            key: f"{key} body"
            for key in svc.SECTION_KEYS
        },
        "disclaimer": "Generated for review.",
    }

    html = svc.render_governance_html(package)

    assert "Financial Services AI Governance Package" in html
    assert "https://www.federalreserve.gov/boarddocs/srletters/2011/sr1107a1.pdf" in html
    assert "https://occ.gov/news-issuances/bulletins/2011/bulletin-2011-12a.pdf" in html
    assert "https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-ai-rmf-10" in html


def test_render_governance_html_formats_dict_sections():
    context = svc.build_governance_context(_employee(), _metrics())
    package = {
        "context": context,
        "sections": {
            key: f"{key} body"
            for key in svc.SECTION_KEYS
        },
        "disclaimer": "Generated for review.",
    }
    package["sections"]["evaluation_outputs"] = svc.evaluation_summary_items(context)

    html = svc.render_governance_html(package)

    assert "<ul>" in html
    assert "web_search: 3" in html
    assert "{&#x27;Source&#x27;" not in html


def test_llm_section_normalization_removes_raw_dict_repr():
    bullets = svc._text_from_llm_section(
        "{'tier': 'Medium', 'score': 2, 'reasons': ['Average score warrants monitoring.']}",
        ["fallback"],
    )
    text = " ".join(bullets)

    assert "Tier: Medium" in text
    assert "Average score warrants monitoring." in text
    assert "{'tier'" not in text


def test_normalize_governance_package_migrates_old_cached_shape():
    package = {
        "context": svc.build_governance_context(_employee(), _metrics()),
        "sections": {
            "evaluation_summary": "Source: db. Tasks: 4.",
            "risk_summary": "old risk",
            "controls_summary": "old controls",
        },
    }

    normalized = svc.normalize_governance_package(package)

    assert "evaluation_summary" not in normalized["sections"]
    assert isinstance(normalized["sections"]["evaluation_outputs"], list)
    assert "committee_review_focus" in normalized["sections"]
    assert "risk_summary" not in normalized["sections"]
    assert "controls_summary" not in normalized["sections"]
