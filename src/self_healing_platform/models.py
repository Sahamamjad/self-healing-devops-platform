"""Persistent incident and audit models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from self_healing_platform.db import Base


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    source: Mapped[str] = mapped_column(String(128))
    affected_component: Mapped[str] = mapped_column(String(256))
    symptoms: Mapped[list[str]] = mapped_column(JSON, default=list)
    severity: Mapped[str] = mapped_column(String(32))
    explanation: Mapped[str] = mapped_column(Text)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    candidate_causes: Mapped[list[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[str] = mapped_column(String(32))
    uncertainty_notes: Mapped[str] = mapped_column(Text, default="")
    recommended_checks: Mapped[list[str]] = mapped_column(JSON, default=list)
    proposed_remediation: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    verification_criteria: Mapped[list[str]] = mapped_column(JSON, default=list)
    lifecycle_status: Mapped[str] = mapped_column(String(64), default="Detected")
    analysis_outcome: Mapped[str] = mapped_column(String(64))
    matched_rules: Mapped[list[str]] = mapped_column(JSON, default=list)
    classification: Mapped[str] = mapped_column(String(64))
    ai_summary: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True, default=None)

    audits: Mapped[list[RemediationAudit]] = relationship(
        back_populates="incident", cascade="all, delete-orphan"
    )


class RemediationAudit(Base):
    __tablename__ = "remediation_audits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    incident_id: Mapped[str] = mapped_column(ForeignKey("incidents.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    requested_action: Mapped[str] = mapped_column(String(128))
    result: Mapped[str] = mapped_column(String(64))
    dry_run: Mapped[bool] = mapped_column(default=True)
    verification_status: Mapped[str] = mapped_column(String(64))
    actor: Mapped[str] = mapped_column(String(128), default="operator")
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    incident: Mapped[Incident] = relationship(back_populates="audits")
