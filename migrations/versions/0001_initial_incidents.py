"""initial incidents and remediation audits

Revision ID: 0001
Revises:
Create Date: 2026-10-16

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "incidents",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("affected_component", sa.String(length=256), nullable=False),
        sa.Column("symptoms", sa.JSON(), nullable=False),
        sa.Column("severity", sa.String(length=32), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("candidate_causes", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.String(length=32), nullable=False),
        sa.Column("uncertainty_notes", sa.Text(), nullable=False),
        sa.Column("recommended_checks", sa.JSON(), nullable=False),
        sa.Column("proposed_remediation", sa.JSON(), nullable=False),
        sa.Column("verification_criteria", sa.JSON(), nullable=False),
        sa.Column("lifecycle_status", sa.String(length=64), nullable=False),
        sa.Column("analysis_outcome", sa.String(length=64), nullable=False),
        sa.Column("matched_rules", sa.JSON(), nullable=False),
        sa.Column("classification", sa.String(length=64), nullable=False),
        sa.Column("ai_summary", sa.JSON(), nullable=True),
    )
    op.create_table(
        "remediation_audits",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("incident_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_action", sa.String(length=128), nullable=False),
        sa.Column("result", sa.String(length=64), nullable=False),
        sa.Column("dry_run", sa.Boolean(), nullable=False),
        sa.Column("verification_status", sa.String(length=64), nullable=False),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"]),
    )
    op.create_index("ix_remediation_audits_incident_id", "remediation_audits", ["incident_id"])


def downgrade() -> None:
    op.drop_index("ix_remediation_audits_incident_id", table_name="remediation_audits")
    op.drop_table("remediation_audits")
    op.drop_table("incidents")
