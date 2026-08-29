"""Governance agent: synthesizes every other agent's findings into a single
human-readable AdvisoryReport, then -- this is the point of the whole
exercise -- refuses to finalize it without an explicit human decision.

This is the piece that turns "an LLM wrote a migration plan" into something a
risk/architecture board would actually accept: no output leaves the system
without a named human approval step, and a critical risk automatically
demands a documented reviewer note rather than a rubber stamp.
"""

from __future__ import annotations

from ..models import (
    AdvisoryReport,
    ArchitectureRecommendation,
    CostRoiFinding,
    DiscoveryFinding,
    GovernanceDecision,
    MigrationPhase,
    RiskComplianceFinding,
    SystemProfile,
)


def build_phases(
    architecture: ArchitectureRecommendation,
    cost: CostRoiFinding,
) -> list[MigrationPhase]:
    weeks_total = cost.estimated_duration_months * 4
    discovery_weeks = max(2, round(weeks_total * 0.15))
    build_weeks = max(2, round(weeks_total * 0.55))
    cutover_weeks = max(1, round(weeks_total * 0.15))
    stabilize_weeks = max(1, weeks_total - discovery_weeks - build_weeks - cutover_weeks)

    return [
        MigrationPhase(
            name="Discovery & Landing Zone",
            duration_weeks=discovery_weeks,
            goal="Confirm scope, stand up the target landing zone and guardrails.",
            exit_criteria=[
                "Target landing zone provisioned via IaC",
                "Compliance controls mapped to every declared regulation",
                "Migration pattern and service boundaries signed off by architecture review",
            ],
        ),
        MigrationPhase(
            name=f"Build ({architecture.migration_pattern.value})",
            duration_weeks=build_weeks,
            goal=f"Execute the {architecture.migration_pattern.value} migration for: {', '.join(architecture.candidate_services)}.",
            exit_criteria=[
                "All candidate services deployed to a non-production environment",
                "Load test passed at 1.5x current peak TPS",
                "Rollback procedure rehearsed at least once",
            ],
        ),
        MigrationPhase(
            name="Cutover",
            duration_weeks=cutover_weeks,
            goal="Move production traffic with a reversible cutover strategy.",
            exit_criteria=[
                "Parallel-run validation complete (legacy vs. target output matches)",
                "Go/no-go signed off by the governance board",
            ],
        ),
        MigrationPhase(
            name="Stabilize & Decommission",
            duration_weeks=stabilize_weeks,
            goal="Confirm the target platform holds under real load, then retire the legacy system.",
            exit_criteria=[
                "One full billing/reporting cycle completed on the target platform",
                "Legacy infrastructure decommissioned and licensing terminated",
            ],
        ),
    ]


def build_executive_summary(
    profile: SystemProfile,
    discovery: DiscoveryFinding,
    architecture: ArchitectureRecommendation,
    risk: RiskComplianceFinding,
    cost: CostRoiFinding,
) -> str:
    return (
        f"{profile.name} scores {discovery.readiness_score}/100 on migration readiness. "
        f"Recommended approach: {architecture.migration_pattern.value} to {architecture.target_cloud}, "
        f"sized as a {cost.cost_tier.value}-tier programme (~{cost.estimated_duration_months} months), "
        f"with {len(risk.risks)} risk(s) identified "
        f"({sum(1 for r in risk.risks if r.severity.value == 'critical')} critical). "
        f"Projected post-migration efficiency gain: {cost.projected_efficiency_gain_pct}%."
    )


def run(
    profile: SystemProfile,
    discovery: DiscoveryFinding,
    architecture: ArchitectureRecommendation,
    risk: RiskComplianceFinding,
    cost: CostRoiFinding,
    human_decision: GovernanceDecision,
) -> AdvisoryReport:
    top_risks = sorted(
        risk.risks,
        key=lambda r: ["low", "medium", "high", "critical"].index(r.severity.value),
        reverse=True,
    )[:5]

    return AdvisoryReport(
        system_name=profile.name,
        executive_summary=build_executive_summary(profile, discovery, architecture, risk, cost),
        phases=build_phases(architecture, cost),
        top_risks=top_risks,
        governance=human_decision,
    )
