"""The Wayfinder agent graph.

Five agents, wired as a LangGraph ``StateGraph``:

::

    START -> discovery -> architecture -> risk --+--> cost -> governance -> END
                                                   |
                                (critical risk) -> escalation -> cost

``governance`` calls ``interrupt()`` and halts the graph until a human
supplies an approve/request-changes decision -- this is the actual
"agentic AI with a human in the loop" mechanic, not a diagram of one. A
``MemorySaver`` checkpointer keeps the paused run's state so the CLI (or any
other caller) can resume it after the human responds, potentially in a
completely separate process invocation.
"""

from __future__ import annotations

from typing import Optional, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from .agents import cloud_architecture, cost_roi, discovery as discovery_agent, governance, risk_compliance
from .llm import Narrator, get_narrator
from .models import (
    AdvisoryReport,
    ArchitectureRecommendation,
    Constraints,
    CostRoiFinding,
    CostTier,
    CurrentStack,
    DiscoveryFinding,
    GovernanceDecision,
    MigrationPattern,
    MigrationPhase,
    RiskComplianceFinding,
    RiskFinding,
    RiskSeverity,
    Scale,
    SystemProfile,
)

# The checkpointer serializes graph state (including our Pydantic models) to
# resume a run after the governance interrupt. langgraph's default msgpack
# codec refuses to (de)serialize app-defined types unless they're explicitly
# allow-listed -- this is exactly that allow-list, kept next to the models
# it covers so a new model added to models.py and forgotten here fails loudly
# in tests rather than silently warning at runtime.
_CHECKPOINT_SERDE = JsonPlusSerializer(
    allowed_msgpack_modules=[
        SystemProfile,
        CurrentStack,
        Scale,
        Constraints,
        DiscoveryFinding,
        ArchitectureRecommendation,
        MigrationPattern,
        RiskFinding,
        RiskSeverity,
        RiskComplianceFinding,
        CostRoiFinding,
        CostTier,
        GovernanceDecision,
        MigrationPhase,
        AdvisoryReport,
    ]
)


class GraphState(TypedDict, total=False):
    profile: SystemProfile
    discovery: DiscoveryFinding
    architecture: ArchitectureRecommendation
    risk: RiskComplianceFinding
    cost: CostRoiFinding
    escalated: bool
    report: AdvisoryReport


def _make_nodes(narrator: Narrator):
    def discovery_node(state: GraphState) -> dict:
        finding = discovery_agent.run(state["profile"], narrator)
        return {"discovery": finding}

    def architecture_node(state: GraphState) -> dict:
        rec = cloud_architecture.run(state["profile"], state["discovery"], narrator)
        return {"architecture": rec}

    def risk_node(state: GraphState) -> dict:
        finding = risk_compliance.run(state["profile"], narrator)
        return {"risk": finding}

    def escalation_node(state: GraphState) -> dict:
        # A real deployment would page a human reviewer or open a ticket here.
        # The graph records that escalation happened so it shows up in the
        # final report and in the governance interrupt payload.
        return {"escalated": True}

    def cost_node(state: GraphState) -> dict:
        finding = cost_roi.run(state["profile"], state["discovery"], state["risk"], narrator)
        return {"cost": finding}

    def governance_node(state: GraphState) -> dict:
        payload = {
            "system_name": state["profile"].name,
            "readiness_score": state["discovery"].readiness_score,
            "migration_pattern": state["architecture"].migration_pattern.value,
            "critical_risks": [r.description for r in state["risk"].risks if r.severity.value == "critical"],
            "escalated": state.get("escalated", False),
            "cost_tier": state["cost"].cost_tier.value,
            "prompt": "Approve this migration roadmap for release? Respond 'approved' or 'changes_requested'.",
        }
        decision = interrupt(payload)

        if isinstance(decision, dict):
            status = decision.get("status", "approved")
            note = decision.get("note", "")
        else:
            status = str(decision)
            note = ""

        human_decision = GovernanceDecision(status=status, reviewer_note=note)
        report = governance.run(
            profile=state["profile"],
            discovery=state["discovery"],
            architecture=state["architecture"],
            risk=state["risk"],
            cost=state["cost"],
            human_decision=human_decision,
        )
        return {"report": report}

    return discovery_node, architecture_node, risk_node, escalation_node, cost_node, governance_node


def _route_after_risk(state: GraphState) -> str:
    return "escalation" if state["risk"].has_critical else "cost"


def build_graph(narrator: Optional[Narrator] = None):
    narrator = narrator or get_narrator()
    discovery_node, architecture_node, risk_node, escalation_node, cost_node, governance_node = _make_nodes(narrator)

    graph = StateGraph(GraphState)
    graph.add_node("discovery", discovery_node)
    graph.add_node("architecture", architecture_node)
    graph.add_node("risk", risk_node)
    graph.add_node("escalation", escalation_node)
    graph.add_node("cost", cost_node)
    graph.add_node("governance", governance_node)

    graph.add_edge(START, "discovery")
    graph.add_edge("discovery", "architecture")
    graph.add_edge("architecture", "risk")
    graph.add_conditional_edges("risk", _route_after_risk, {"escalation": "escalation", "cost": "cost"})
    graph.add_edge("escalation", "cost")
    graph.add_edge("cost", "governance")
    graph.add_edge("governance", END)

    return graph.compile(checkpointer=MemorySaver(serde=_CHECKPOINT_SERDE))


__all__ = ["build_graph", "GraphState", "Command"]
