"""Risk & compliance agent: cross-references the profile's stated regulatory
regime against a small knowledge base of concerns, plus scale/SLA-driven
operational risks. This is the agent most directly responsible for keeping
the system credible in a regulated industry -- every risk carries an id so
it can be tracked to closure outside the tool.
"""

from __future__ import annotations

from ..llm import Narrator
from ..models import RiskComplianceFinding, RiskFinding, RiskSeverity, SystemProfile

REGULATION_KNOWLEDGE_BASE: dict[str, list[tuple[str, RiskSeverity, str]]] = {
    "gdpr": [
        (
            "personal data must not leave its declared residency boundary during migration",
            RiskSeverity.HIGH,
            "pin all data-plane resources to in-region cloud accounts; use region-locked replication only",
        )
    ],
    "pci dss": [
        (
            "cardholder data environment scope must be re-certified after any infrastructure change",
            RiskSeverity.CRITICAL,
            "engage the QSA before cutover; segment the CDE in the target architecture from day one",
        )
    ],
    "mifid ii": [
        (
            "trade reporting timeliness (T+1) must be preserved through the migration cutover window",
            RiskSeverity.HIGH,
            "run the legacy and target systems in parallel through at least one full reporting cycle",
        )
    ],
    "sox": [
        (
            "change-management audit trail must remain unbroken across the migration",
            RiskSeverity.MEDIUM,
            "mirror existing approval workflows in the new CI/CD pipeline before decommissioning the old one",
        )
    ],
}


def _regulatory_risks(profile: SystemProfile) -> list[RiskFinding]:
    findings: list[RiskFinding] = []
    counter = 1
    for reg in profile.constraints.regulatory:
        for description, severity, mitigation in REGULATION_KNOWLEDGE_BASE.get(reg.lower(), []):
            findings.append(
                RiskFinding(
                    id=f"REG-{counter:02d}",
                    description=f"[{reg}] {description}",
                    severity=severity,
                    mitigation=mitigation,
                )
            )
            counter += 1
    return findings


def _operational_risks(profile: SystemProfile) -> list[RiskFinding]:
    findings: list[RiskFinding] = []
    counter = 1
    if profile.constraints.uptime_sla and "99.9" in profile.constraints.uptime_sla.replace("%", ""):
        findings.append(
            RiskFinding(
                id=f"OPS-{counter:02d}",
                description=f"stated SLA ({profile.constraints.uptime_sla}) leaves very little error budget during cutover",
                severity=RiskSeverity.MEDIUM,
                mitigation="use a blue/green cutover with instant rollback rather than a big-bang switch",
            )
        )
        counter += 1
    if not profile.constraints.regulatory:
        findings.append(
            RiskFinding(
                id=f"OPS-{counter:02d}",
                description="no regulatory regime was declared for this system -- compliance exposure is unscoped",
                severity=RiskSeverity.MEDIUM,
                mitigation="confirm applicable regulation with Legal/Compliance before finalizing the target architecture",
            )
        )
    return findings


def run(profile: SystemProfile, narrator: Narrator) -> RiskComplianceFinding:
    risks = _regulatory_risks(profile) + _operational_risks(profile)
    brief = "\n".join(f"- [{r.severity.value.upper()}] {r.description}" for r in risks) or "- no material risks identified"
    summary = narrator.narrate(role="risk & compliance advisor", brief=brief)
    return RiskComplianceFinding(risks=risks, summary=summary)
