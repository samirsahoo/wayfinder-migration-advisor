"""Cloud architecture agent: recommends a target platform, a migration
pattern (one of the "6 R's"), and a first-cut service decomposition, then
self-checks the recommendation against the AWS Well-Architected pillars.
"""

from __future__ import annotations

from ..llm import Narrator
from ..models import ArchitectureRecommendation, DiscoveryFinding, MigrationPattern, SystemProfile

WELL_ARCHITECTED_PILLARS = [
    "Operational Excellence",
    "Security",
    "Reliability",
    "Performance Efficiency",
    "Cost Optimization",
]


def _choose_pattern(profile: SystemProfile, discovery: DiscoveryFinding) -> MigrationPattern:
    if discovery.readiness_score >= 75:
        return MigrationPattern.REPLATFORM
    if discovery.readiness_score >= 45:
        return MigrationPattern.REFACTOR
    if any("end-of-life" in s for s in discovery.complexity_signals):
        return MigrationPattern.REFACTOR
    return MigrationPattern.REHOST


def _slugify(name: str) -> str:
    return "-".join(name.lower().split()) or "system"


def _decompose_services(profile: SystemProfile) -> list[str]:
    """Heuristic bounded-context guesser: turns integration channels and the
    system description into plausible service candidates. This is a
    starting hypothesis for an architect to refine, not a final design --
    the report says so explicitly."""

    base = _slugify(profile.name)
    candidates = [f"{base}-api-gateway", f"{base}-domain-service"]
    for integration in profile.current_stack.integration:
        candidates.append(f"{base}-{integration.lower().replace(' ', '-')}-adapter")
    if profile.scale.peak_tps and profile.scale.peak_tps > 500:
        candidates.append(f"{base}-read-replica-service")
    return candidates


def _well_architected_notes(profile: SystemProfile, pattern: MigrationPattern) -> dict[str, str]:
    notes = {
        "Operational Excellence": "Introduce IaC (Terraform) and CI/CD from day one of the migration, not after.",
        "Security": "Encrypt at rest and in transit by default; map every regulatory constraint to a control before cutover.",
        "Reliability": f"Design to the stated SLA ({profile.constraints.uptime_sla or 'undefined -- confirm with the business'}) with multi-AZ deployment.",
        "Performance Efficiency": "Load-test the target architecture at 1.5x current peak TPS before go-live.",
        "Cost Optimization": "Right-size compute post-migration using 30 days of real usage data, not pre-migration estimates.",
    }
    if pattern == MigrationPattern.REHOST:
        notes["Cost Optimization"] += " Rehosting captures infra savings only; plan a follow-on refactor wave for real cost efficiency."
    return notes


def _choose_target_cloud(profile: SystemProfile) -> str:
    """Single-region workloads go to AWS. Multi-region data-residency
    constraints (the profile names more than one jurisdiction) are the one
    case where a second, regionally-strong provider genuinely earns its
    place in the recommendation -- not just because *some* residency value
    was declared, which nearly every real profile will have."""

    residency = (profile.constraints.data_residency or "").lower()
    multi_region = "+" in residency or " and " in residency
    if multi_region:
        return "AWS (primary) with IBM Cloud for the data-residency-constrained region(s)"
    return "AWS"


def run(profile: SystemProfile, discovery: DiscoveryFinding, narrator: Narrator) -> ArchitectureRecommendation:
    pattern = _choose_pattern(profile, discovery)
    services = _decompose_services(profile)
    notes = _well_architected_notes(profile, pattern)

    target_cloud = _choose_target_cloud(profile)

    brief = "\n".join(
        [
            f"- recommended pattern: {pattern.value}",
            f"- target platform: {target_cloud}",
            f"- candidate services: {', '.join(services)}",
        ]
    )
    summary = narrator.narrate(role="cloud architecture advisor", brief=brief)

    return ArchitectureRecommendation(
        target_cloud=target_cloud,
        migration_pattern=pattern,
        candidate_services=services,
        well_architected_notes=notes,
        summary=summary,
    )
