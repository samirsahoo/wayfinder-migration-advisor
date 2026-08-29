"""Typed data model for Wayfinder.

Everything that flows through the agent graph is a plain, validated Pydantic
model. Agents read a `SystemProfile` plus the findings produced by earlier
agents, and append their own typed finding to `AdvisoryState.findings` -- the
graph never passes free-text blobs between nodes.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class MigrationPattern(str, Enum):
    """The classic "6 R's" of cloud migration, used as a controlled vocabulary
    so agent output is comparable across runs instead of free-text guesses."""

    REHOST = "rehost"
    REPLATFORM = "replatform"
    REFACTOR = "refactor"
    REPURCHASE = "repurchase"
    RETAIN = "retain"
    RETIRE = "retire"


class RiskSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CostTier(str, Enum):
    S = "S"  # weeks, single team
    M = "M"  # one quarter, single team
    L = "L"  # two-three quarters, multiple teams
    XL = "XL"  # 12+ months, programme-level


class CurrentStack(BaseModel):
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    database: str = "unknown"
    deployment: str = "unknown"
    integration: list[str] = Field(default_factory=list)


class Scale(BaseModel):
    daily_transactions: Optional[int] = None
    peak_tps: Optional[int] = None
    users: Optional[int] = None


class Constraints(BaseModel):
    data_residency: Optional[str] = None
    regulatory: list[str] = Field(default_factory=list)
    uptime_sla: Optional[str] = None
    change_window: Optional[str] = None


class SystemProfile(BaseModel):
    """The input to a Wayfinder run: a description of one legacy system,
    written by a human (an architect, typically) as YAML."""

    name: str
    description: str = ""
    industry: str = "general"
    current_stack: CurrentStack = Field(default_factory=CurrentStack)
    scale: Scale = Field(default_factory=Scale)
    constraints: Constraints = Field(default_factory=Constraints)
    business_drivers: list[str] = Field(default_factory=list)


class DiscoveryFinding(BaseModel):
    readiness_score: int = Field(ge=0, le=100)
    complexity_signals: list[str]
    dependency_risks: list[str]
    summary: str


class ArchitectureRecommendation(BaseModel):
    target_cloud: str
    migration_pattern: MigrationPattern
    candidate_services: list[str]
    well_architected_notes: dict[str, str]
    summary: str


class RiskFinding(BaseModel):
    id: str
    description: str
    severity: RiskSeverity
    mitigation: str


class RiskComplianceFinding(BaseModel):
    risks: list[RiskFinding]
    summary: str

    @property
    def has_critical(self) -> bool:
        return any(r.severity == RiskSeverity.CRITICAL for r in self.risks)


class CostRoiFinding(BaseModel):
    cost_tier: CostTier
    estimated_duration_months: int
    three_year_tco_note: str
    projected_efficiency_gain_pct: int
    summary: str


class GovernanceDecision(BaseModel):
    status: str  # "approved" | "changes_requested" | "pending"
    reviewer_note: str = ""


class MigrationPhase(BaseModel):
    name: str
    duration_weeks: int
    goal: str
    exit_criteria: list[str]


class AdvisoryReport(BaseModel):
    """The final synthesized artifact -- what a human actually reads."""

    system_name: str
    executive_summary: str
    phases: list[MigrationPhase]
    top_risks: list[RiskFinding]
    governance: GovernanceDecision
