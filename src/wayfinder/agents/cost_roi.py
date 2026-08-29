"""Cost & ROI agent: sizes the migration effort and sketches a 3-year TCO
narrative. Effort sizing is driven by discovery + risk output so the
estimate reflects actual assessed complexity rather than a flat guess.
"""

from __future__ import annotations

from ..llm import Narrator
from ..models import (
    CostRoiFinding,
    CostTier,
    DiscoveryFinding,
    RiskComplianceFinding,
    SystemProfile,
)


def _size_effort(discovery: DiscoveryFinding, risk: RiskComplianceFinding) -> tuple[CostTier, int]:
    complexity_points = (
        len(discovery.complexity_signals) * 2
        + len(discovery.dependency_risks)
        + sum(3 for r in risk.risks if r.severity.value == "critical")
        + sum(1 for r in risk.risks if r.severity.value == "high")
    )
    if complexity_points <= 2:
        return CostTier.S, 2
    if complexity_points <= 5:
        return CostTier.M, 4
    if complexity_points <= 9:
        return CostTier.L, 9
    return CostTier.XL, 14


def run(
    profile: SystemProfile,
    discovery: DiscoveryFinding,
    risk: RiskComplianceFinding,
    narrator: Narrator,
) -> CostRoiFinding:
    tier, months = _size_effort(discovery, risk)

    # Efficiency gain is a function of how legacy the starting point is --
    # bigger gap to cloud-native, bigger headroom for improvement.
    efficiency_gain = max(15, min(45, 100 - discovery.readiness_score))

    tco_note = (
        f"Year 1 carries dual-running cost (legacy + target); years 2-3 should show net savings "
        f"once legacy licensing and on-prem capacity are decommissioned."
    )

    brief = "\n".join(
        [
            f"- effort sizing: {tier.value} (~{months} months)",
            f"- projected efficiency gain post-migration: {efficiency_gain}%",
            f"- {tco_note}",
        ]
    )
    summary = narrator.narrate(role="cost & ROI advisor", brief=brief)

    return CostRoiFinding(
        cost_tier=tier,
        estimated_duration_months=months,
        three_year_tco_note=tco_note,
        projected_efficiency_gain_pct=efficiency_gain,
        summary=summary,
    )
