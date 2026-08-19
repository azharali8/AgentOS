"""Phase 7 Adaptive Intelligence Extensions

Revision ID: d1e2f3a4b5c6
Revises: a7b8c9d0e1f2
Create Date: 2026-08-17 06:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "a7b8c9d0e1f2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "routing_decisions",
        sa.Column("decision_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("task_category", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("estimated_cost", sa.Float(), nullable=False),
        sa.Column("estimated_latency_ms", sa.Float(), nullable=False),
        sa.Column("routing_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.task_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("decision_id"),
    )
    op.create_index("ix_routing_decisions_task_id", "routing_decisions", ["task_id"], unique=False)
    op.create_index("ix_routing_decisions_created_at", "routing_decisions", ["created_at"], unique=False)

    op.create_table(
        "execution_evaluations",
        sa.Column("evaluation_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=False),
        sa.Column("efficiency_score", sa.Float(), nullable=False),
        sa.Column("safety_score", sa.Float(), nullable=False),
        sa.Column("coordination_score", sa.Float(), nullable=False),
        sa.Column("recommendations", sa.JSON(), nullable=True),
        sa.Column("evaluation_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.task_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("evaluation_id"),
    )
    op.create_index("ix_execution_evaluations_task_id", "execution_evaluations", ["task_id"], unique=False)
    op.create_index("ix_execution_evaluations_created_at", "execution_evaluations", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_execution_evaluations_created_at", table_name="execution_evaluations")
    op.drop_index("ix_execution_evaluations_task_id", table_name="execution_evaluations")
    op.drop_table("execution_evaluations")
    op.drop_index("ix_routing_decisions_created_at", table_name="routing_decisions")
    op.drop_index("ix_routing_decisions_task_id", table_name="routing_decisions")
    op.drop_table("routing_decisions")
