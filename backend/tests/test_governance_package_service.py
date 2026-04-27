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


def test_build_governance_context_includes_financial_policy_references():
    context = svc.build_governance_context(_employee(), _metrics())

    names = [ref["name"] for ref in context["policy_references"]]
    assert any("SR 11-7" in name for name in names)
    assert any("OCC Bulletin 2011-12" in name for name in names)
    assert any("NIST AI Risk Management Framework" in name for name in names)
    assert context["risk"]["tier"] == "High"


def test_generate_governance_package_uses_template_without_api_key(monkeypatch):
    monkeypatch.setattr(svc.config, "API_KEY", None, raising=False)

    package = asyncio.run(svc.generate_governance_package(_employee(), _metrics()))

    assert package["llm"]["used"] is False
    assert package["sections"]["risk_summary"]
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
    assert "https://www.federalreserve.gov/bankinforeg/srletters/sr1107.htm" in html
    assert "https://www.occ.gov/news-issuances/bulletins/2011/bulletin-2011-12a.pdf" in html
