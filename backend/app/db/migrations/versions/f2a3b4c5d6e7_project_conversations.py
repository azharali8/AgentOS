"""Add durable project/conversation membership without rewriting legacy tasks."""
from alembic import op
import sqlalchemy as sa

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("projects",
        sa.Column("project_id", sa.String(36), primary_key=True),
        sa.Column("owner_id", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("workspace_path", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("owner_id", "workspace_path", name="uq_project_owner_workspace"))
    op.create_index("ix_projects_owner_id", "projects", ["owner_id"])
    op.create_table("conversations",
        sa.Column("conversation_id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("projects.project_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_conversations_project_id", "conversations", ["project_id"])
    op.create_table("conversation_tasks",
        sa.Column("task_id", sa.String(36), sa.ForeignKey("tasks.task_id", ondelete="CASCADE"), primary_key=True),
        sa.Column("conversation_id", sa.String(36), sa.ForeignKey("conversations.conversation_id", ondelete="RESTRICT"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_conversation_tasks_conversation_id", "conversation_tasks", ["conversation_id"])


def downgrade():
    op.drop_table("conversation_tasks")
    op.drop_table("conversations")
    op.drop_table("projects")
