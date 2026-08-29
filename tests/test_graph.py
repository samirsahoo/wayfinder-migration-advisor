"""End-to-end tests for the Wayfinder graph, run entirely offline (MockNarrator,
no network, no API key). These are the tests a stranger cloning the repo can
run immediately with no setup beyond `pip install -e .`.
"""

from __future__ import annotations

import uuid

import pytest

from wayfinder.graph import Command, build_graph
from wayfinder.llm import MockNarrator
from wayfinder.models import Constraints, CurrentStack, Scale, SystemProfile


def make_profile(**overrides) -> SystemProfile:
    base = dict(
        name="Test System",
        description="A test system",
        industry="banking_financial_services",
        current_stack=CurrentStack(
            languages=["Java"],
            frameworks=["EJB 2.1"],
            database="Oracle 11g",
            deployment="on_prem_datacenter",
            integration=["MQ Series", "SOAP", "FTP", "CORBA"],
        ),
        scale=Scale(daily_transactions=1_000_000, peak_tps=800, users=200),
        constraints=Constraints(
            data_residency="EU",
            regulatory=["PCI DSS", "GDPR"],
            uptime_sla="99.95%",
            change_window="monthly",
        ),
        business_drivers=["cut cost", "go faster"],
    )
    base.update(overrides)
    return SystemProfile(**base)


def run_to_completion(profile: SystemProfile, decision: dict):
    app = build_graph(narrator=MockNarrator())
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    state = app.invoke({"profile": profile, "escalated": False}, config=config)
    assert "__interrupt__" in state, "graph should pause at the governance gate"
    final_state = app.invoke(Command(resume=decision), config=config)
    return final_state


def test_graph_runs_end_to_end_and_produces_a_report():
    profile = make_profile()
    final_state = run_to_completion(profile, {"status": "approved", "note": ""})

    assert final_state["report"].system_name == "Test System"
    assert final_state["report"].governance.status == "approved"
    assert 0 <= final_state["discovery"].readiness_score <= 100
    assert final_state["architecture"].migration_pattern is not None
    assert len(final_state["report"].phases) == 4


def test_pci_dss_profile_surfaces_a_critical_risk_and_escalates():
    profile = make_profile()  # includes PCI DSS
    final_state = run_to_completion(profile, {"status": "approved", "note": ""})

    assert final_state["risk"].has_critical
    assert final_state["escalated"] is True
    assert any(r.severity.value == "critical" for r in final_state["report"].top_risks)


def test_low_risk_profile_does_not_escalate():
    profile = make_profile(
        current_stack=CurrentStack(
            languages=["C#"],
            frameworks=["ASP.NET"],
            database="PostgreSQL",
            deployment="cloud_kubernetes",
            integration=["REST"],
        ),
        constraints=Constraints(regulatory=[]),
        scale=Scale(daily_transactions=1000, peak_tps=20, users=10),
    )
    final_state = run_to_completion(profile, {"status": "approved", "note": ""})

    assert final_state["escalated"] is False
    assert not final_state["risk"].has_critical


def test_governance_gate_records_a_rejection_with_reviewer_note():
    profile = make_profile()
    final_state = run_to_completion(
        profile, {"status": "changes_requested", "note": "Need a DR plan before sign-off."}
    )

    assert final_state["report"].governance.status == "changes_requested"
    assert "DR plan" in final_state["report"].governance.reviewer_note


def test_readiness_score_penalizes_legacy_stack_more_than_modern_stack():
    legacy = make_profile()
    modern = make_profile(
        current_stack=CurrentStack(
            languages=["Java"],
            frameworks=["Spring Boot"],
            database="PostgreSQL",
            deployment="cloud_kubernetes",
            integration=["REST"],
        ),
    )

    legacy_state = run_to_completion(legacy, {"status": "approved", "note": ""})
    modern_state = run_to_completion(modern, {"status": "approved", "note": ""})

    assert legacy_state["discovery"].readiness_score < modern_state["discovery"].readiness_score


def test_cli_yaml_examples_are_valid_profiles():
    import yaml
    from pathlib import Path

    examples_dir = Path(__file__).parent.parent / "examples"
    profiles = list(examples_dir.glob("*.yaml"))
    assert len(profiles) >= 2, "expected at least two example profiles in examples/"

    for path in profiles:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        profile = SystemProfile.model_validate(data)
        assert profile.name
