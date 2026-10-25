"""Typed request and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from self_healing_platform.lifecycle import LifecycleStatus

Severity = Literal["low", "medium", "high", "critical"]
Confidence = Literal["low", "medium", "high", "none"]
DemoMode = Literal["http_500", "http_503", "inject_latency"]
AnalysisOutcome = Literal[
    "classified",
    "insufficient_evidence",
    "conflicting_evidence",
]


class RootResponse(BaseModel):
    name: str
    version: str
    description: str


class LiveResponse(BaseModel):
    status: Literal["live"]


class ReadyResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    database: Literal["ok", "unavailable"]
    reason: str | None = None


class StatusResponse(BaseModel):
    service: str
    version: str
    environment: str
    uptime_seconds: float
    demo_failure_enabled: bool
    remediation_dry_run_only: bool
    ai_summaries_enabled: bool
    database_backend: str


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class DemoWorkResponse(BaseModel):
    iterations: int
    delay_ms: int
    elapsed_ms: float


class DemoFailureRequest(BaseModel):
    mode: DemoMode = "http_500"
    duration_seconds: int = Field(default=15, ge=1, le=300)
    max_requests: int = Field(default=25, ge=1, le=1000)


class DemoFailureResponse(BaseModel):
    enabled: bool
    mode: DemoMode | None = None
    remaining_seconds: float = 0
    remaining_requests: int = 0
    incident_id: str | None = None
    message: str


class KubernetesEvent(BaseModel):
    reason: str = Field(max_length=128)
    message: str = Field(default="", max_length=2048)
    count: int = Field(default=1, ge=1, le=10000)


class IncidentEvidence(BaseModel):
    http_5xx_count: int | None = Field(default=None, ge=0, le=10_000_000)
    http_request_count: int | None = Field(default=None, ge=0, le=10_000_000)
    latency_p99_seconds: float | None = Field(default=None, ge=0, le=600)
    readiness_consecutive_failures: int | None = Field(default=None, ge=0, le=1000)
    kubernetes_events: list[KubernetesEvent] = Field(default_factory=list, max_length=50)
    rollout_failed: bool | None = None
    image_pull_failed: bool | None = None
    cpu_utilization: float | None = Field(default=None, ge=0, le=1)
    memory_utilization: float | None = Field(default=None, ge=0, le=1)
    config_expected_hash: str | None = Field(default=None, max_length=128)
    config_observed_hash: str | None = Field(default=None, max_length=128)
    logs_excerpt: str | None = Field(default=None, max_length=4000)

    @field_validator("logs_excerpt")
    @classmethod
    def bound_logs(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value[:4000]


class AnalyzeIncidentRequest(BaseModel):
    source: str = Field(min_length=1, max_length=128)
    affected_component: str = Field(min_length=1, max_length=256)
    symptoms: list[str] = Field(default_factory=list, max_length=20)
    evidence: IncidentEvidence


class ProposedRemediation(BaseModel):
    action: str
    simulated: bool = True
    rationale: str
    allowlisted: bool


class IncidentResponse(BaseModel):
    id: str
    created_at: datetime
    updated_at: datetime
    source: str
    affected_component: str
    symptoms: list[str]
    severity: Severity
    explanation: str
    evidence: dict[str, Any]
    candidate_causes: list[str]
    confidence: Confidence
    uncertainty_notes: str
    recommended_checks: list[str]
    proposed_remediation: dict[str, Any]
    verification_criteria: list[str]
    lifecycle_status: LifecycleStatus
    analysis_outcome: AnalysisOutcome
    matched_rules: list[str]
    classification: str
    ai_summary: dict[str, Any] | None = None
    audits: list[RemediationAuditResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class IncidentListResponse(BaseModel):
    items: list[IncidentResponse]
    total: int
    limit: int
    offset: int


class RemediateRequest(BaseModel):
    action: str = Field(min_length=1, max_length=128)
    approved: bool = False
    dry_run: bool = True
    actor: str = Field(default="operator", max_length=128)


class RemediationAuditResponse(BaseModel):
    id: str
    incident_id: str
    created_at: datetime
    requested_action: str
    result: str
    dry_run: bool
    verification_status: str
    actor: str
    detail: dict[str, Any]

    model_config = {"from_attributes": True}


class AnalysisResult(BaseModel):
    classification: str
    severity: Severity
    explanation: str
    candidate_causes: list[str]
    confidence: Confidence
    uncertainty_notes: str
    recommended_checks: list[str]
    proposed_remediation: ProposedRemediation
    verification_criteria: list[str]
    analysis_outcome: AnalysisOutcome
    matched_rules: list[str]
    lifecycle_status: LifecycleStatus
    sanitized_evidence: dict[str, Any]
