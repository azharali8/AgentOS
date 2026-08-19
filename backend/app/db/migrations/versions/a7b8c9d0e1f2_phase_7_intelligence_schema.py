"""Phase 7 Intelligence Schema

Revision ID: a7b8c9d0e1f2
Revises: 5633cd945800
Create Date: 2026-08-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, Sequence[str], None] = '5633cd945800'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('agent_performance',
        sa.Column('record_id', sa.String(length=36), nullable=False),
        sa.Column('agent_type', sa.String(length=50), nullable=False),
        sa.Column('metrics', sa.JSON(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('record_id')
    )
    op.create_index('ix_agent_performance_agent_type', 'agent_performance', ['agent_type'], unique=False)
    op.create_index('ix_agent_performance_updated_at', 'agent_performance', ['updated_at'], unique=False)

    op.create_table('task_history',
        sa.Column('history_id', sa.String(length=36), nullable=False),
        sa.Column('task_id', sa.String(length=36), nullable=False),
        sa.Column('task_category', sa.String(length=100), nullable=False),
        sa.Column('strategy_used', sa.String(length=100), nullable=False),
        sa.Column('agents_involved', sa.JSON(), nullable=True),
        sa.Column('success', sa.Integer(), nullable=False),
        sa.Column('duration_seconds', sa.Integer(), nullable=False),
        sa.Column('history_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.task_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('history_id')
    )
    op.create_index('ix_task_history_task_id', 'task_history', ['task_id'], unique=False)
    op.create_index('ix_task_history_category', 'task_history', ['task_category'], unique=False)

    op.create_table('task_strategies',
        sa.Column('strategy_id', sa.String(length=36), nullable=False),
        sa.Column('task_id', sa.String(length=36), nullable=False),
        sa.Column('strategy', sa.String(length=100), nullable=False),
        sa.Column('strategy_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.task_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('strategy_id')
    )
    op.create_index('ix_task_strategies_task_id', 'task_strategies', ['task_id'], unique=False)

    op.create_table('failure_patterns',
        sa.Column('pattern_id', sa.String(length=36), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('occurrence_count', sa.Integer(), nullable=False),
        sa.Column('resolution', sa.Text(), nullable=True),
        sa.Column('pattern_metadata', sa.JSON(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('pattern_id')
    )
    op.create_index('ix_failure_patterns_category', 'failure_patterns', ['category'], unique=False)

    op.create_table('strategy_evaluations',
        sa.Column('eval_id', sa.String(length=36), nullable=False),
        sa.Column('task_id', sa.String(length=36), nullable=False),
        sa.Column('strategy', sa.String(length=100), nullable=False),
        sa.Column('score', sa.Integer(), nullable=False),
        sa.Column('eval_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.task_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('eval_id')
    )
    op.create_index('ix_strategy_evaluations_task_id', 'strategy_evaluations', ['task_id'], unique=False)

    op.create_table('plan_evaluations',
        sa.Column('eval_id', sa.String(length=36), nullable=False),
        sa.Column('task_id', sa.String(length=36), nullable=False),
        sa.Column('score', sa.Integer(), nullable=False),
        sa.Column('plan_metadata', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.task_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('eval_id')
    )
    op.create_index('ix_plan_evaluations_task_id', 'plan_evaluations', ['task_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_plan_evaluations_task_id', table_name='plan_evaluations')
    op.drop_table('plan_evaluations')
    op.drop_index('ix_strategy_evaluations_task_id', table_name='strategy_evaluations')
    op.drop_table('strategy_evaluations')
    op.drop_index('ix_failure_patterns_category', table_name='failure_patterns')
    op.drop_table('failure_patterns')
    op.drop_index('ix_task_strategies_task_id', table_name='task_strategies')
    op.drop_table('task_strategies')
    op.drop_index('ix_task_history_category', table_name='task_history')
    op.drop_index('ix_task_history_task_id', table_name='task_history')
    op.drop_table('task_history')
    op.drop_index('ix_agent_performance_updated_at', table_name='agent_performance')
    op.drop_index('ix_agent_performance_agent_type', table_name='agent_performance')
    op.drop_table('agent_performance')
