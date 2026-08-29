"""Discovery agent: turns a raw SystemProfile into a readiness assessment.

The scoring heuristic is intentionally legible (no black box): every
deduction is a named signal, so a human reviewer can see exactly why a
system scored the way it did. That auditability is the point -- it's the
same property a real migration-governance board would demand before trusting
an automated recommendation.
"""

from __future__ import annotations

from ..llm import Narrator
from ..models import CurrentStack, DiscoveryFinding, SystemProfile

LEGACY_LANGUAGES = {"cobol", "vb", "vb6", "powerbuilder", "pl/sql"}
LEGACY_FRAMEWORKS = {"ejb 2.1", "ejb", "struts", "wicket", "jsf 1.x"}
TIGHTLY_COUPLED_INTEGRATIONS = {"mq series", "soap", "corba", "ftp"}


def _signals_from_stack(stack: CurrentStack) -> list[str]:
    signals: list[str] = []
    for lang in stack.languages:
        if lang.lower() in LEGACY_LANGUAGES:
            signals.append(f"legacy language in use: {lang}")
    for fw in stack.frameworks:
        if fw.lower() in LEGACY_FRAMEWORKS:
            signals.append(f"end-of-life framework: {fw}")
    if "on_prem" in stack.deployment.lower() or "on-prem" in stack.deployment.lower():
        signals.append("currently deployed on-premises")
    for integration in stack.integration:
        if integration.lower() in TIGHTLY_COUPLED_INTEGRATIONS:
            signals.append(f"tightly-coupled integration channel: {integration}")
    return signals


def _dependency_risks(profile: SystemProfile) -> list[str]:
    risks: list[str] = []
    if len(profile.current_stack.integration) >= 4:
        risks.append(
            f"high integration fan-out ({len(profile.current_stack.integration)} channels) "
            "increases regression risk during cutover"
        )
    if profile.scale.peak_tps and profile.scale.peak_tps > 500:
        risks.append(
            f"peak load of {profile.scale.peak_tps} TPS requires a load-tested target "
            "architecture before cutover, not after"
        )
    if profile.constraints.change_window:
        risks.append(
            f"narrow change window ({profile.constraints.change_window}) constrains "
            "how migration waves can be sequenced"
        )
    return risks


def run(profile: SystemProfile, narrator: Narrator) -> DiscoveryFinding:
    signals = _signals_from_stack(profile.current_stack)
    risks = _dependency_risks(profile)

    score = 100
    score -= 12 * len(signals)
    score -= 6 * len(risks)
    score -= 5 if not profile.constraints.regulatory else 0  # unscoped compliance = unknown risk
    score = max(5, min(100, score))

    brief = "\n".join(
        [f"- readiness score computed at {score}/100"]
        + [f"- signal: {s}" for s in signals]
        + [f"- dependency risk: {r}" for r in risks]
    )
    summary = narrator.narrate(role="discovery & readiness analyst", brief=brief)

    return DiscoveryFinding(
        readiness_score=score,
        complexity_signals=signals,
        dependency_risks=risks,
        summary=summary,
    )
