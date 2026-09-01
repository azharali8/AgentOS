from __future__ import annotations
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'd1e2f3a4b5c6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table(
        'workers',
        sa.Column('worker_id', sa.String(length=64), nullable=False),
        sa.Column('hostname', sa.String(length=255), nullable=False),
        sa.Column('process_id', sa.Integer(), nullable=False),
        sa.Column('capabilities', sa.JSON(), nullable=False),
        sa.Column('active_tasks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('max_tasks', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='STARTING'),
        sa.Column('last_heartbeat', sa.DateTime(), nullable=False),
        sa.Column('started_at', sa.DateTime(), nullable=False),
        sa.Column('worker_metadata', sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint('worker_id'),
    )
    op.create_index('ix_workers_status', 'workers', ['status'], unique=False)
    op.create_index('ix_workers_last_heartbeat', 'workers', ['last_heartbeat'], unique=False)

    op.create_table(
        'task_leases',
        sa.Column('lease_id', sa.String(length=64), nullable=False),
        sa.Column('task_id', sa.String(length=36), nullable=False),
        sa.Column('worker_id', sa.String(length=64), nullable=False),
        sa.Column('fencing_token', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('lease_started_at', sa.DateTime(), nullable=False),
        sa.Column('lease_expires_at', sa.DateTime(), nullable=False),
        sa.Column('last_renewed_at', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='ACTIVE'),
        sa.Column('renew_count', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.task_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['worker_id'], ['workers.worker_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('lease_id'),
    )
    op.create_index('ix_task_leases_task_id', 'task_leases', ['task_id'], unique=False)
    op.create_index('ix_task_leases_worker_id', 'task_leases', ['worker_id'], unique=False)
    op.create_index('ix_task_leases_status', 'task_leases', ['status'], unique=False)
    op.create_index('ix_task_leases_expires', 'task_leases', ['lease_expires_at'], unique=False)

    op.create_table(
        'task_queue',
        sa.Column('queue_id', sa.String(length=64), nullable=False),
        sa.Column('task_id', sa.String(length=36), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='2'),
        sa.Column('status', sa.String(length=50), nullable=False, server_default='QUEUED'),
        sa.Column('required_capabilities', sa.JSON(), nullable=False),
        sa.Column('assigned_worker_id', sa.String(length=64), nullable=True),
        sa.Column('current_fencing_token', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('enqueued_at', sa.DateTime(), nullable=False),
        sa.Column('dispatched_at', sa.DateTime(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('retry_limit', sa.Integer(), nullable=False, server_default='3'),
        sa.Column('idempotency_key', sa.String(length=64), nullable=True),
        sa.Column('queue_metadata', sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.task_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assigned_worker_id'], ['workers.worker_id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('queue_id'),
        sa.UniqueConstraint('task_id'),
    )
    op.create_index('ix_task_queue_status', 'task_queue', ['status'], unique=False)
    op.create_index('ix_task_queue_priority', 'task_queue', ['priority'], unique=False)
    op.create_index('ix_task_queue_enqueued_at', 'task_queue', ['enqueued_at'], unique=False)
    op.create_index('ix_task_queue_idempotency', 'task_queue', ['idempotency_key'], unique=False)

def downgrade() -> None:
    op.drop_table('task_queue')
    op.drop_table('task_leases')
    op.drop_table('workers')
