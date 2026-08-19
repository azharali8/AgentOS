import datetime
from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text
from sqlalchemy.orm import relationship
from backend.app.db.database import Base

class TaskModel(Base):
    __tablename__ = "tasks"

    task_id = Column(String(36), primary_key=True)
    user_request = Column(Text, nullable=False)
    status = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    current_step = Column(Integer, default=0, nullable=False)
    total_steps = Column(Integer, default=0, nullable=False)
    retry_count = Column(Integer, default=0, nullable=False)
    replan_count = Column(Integer, default=0, nullable=False)
    final_response = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    thread_id = Column(String(36), nullable=True)
    task_metadata = Column(JSON, nullable=True)

    approvals = relationship("ApprovalModel", back_populates="task", cascade="all, delete-orphan")
    executions = relationship("ExecutionModel", back_populates="task", cascade="all, delete-orphan")
    events = relationship("EventModel", back_populates="task", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_tasks_status", "status"),
        Index("ix_tasks_created_at", "created_at"),
        Index("ix_tasks_thread_id", "thread_id"),
    )

class ApprovalModel(Base):
    __tablename__ = "approvals"

    approval_id = Column(String(36), primary_key=True)
    task_id = Column(String(36), ForeignKey("tasks.task_id", ondelete="CASCADE"), nullable=False)
    step_id = Column(String(100), nullable=False)
    tool_name = Column(String(100), nullable=False)
    operation = Column(String(100), nullable=False)
    arguments_hash = Column(String(64), nullable=False)
    arguments_summary = Column(JSON, nullable=False)
    risk_level = Column(String(50), nullable=False)
    status = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    resolved_by = Column(String(100), nullable=True)
    resolution_reason = Column(Text, nullable=True)

    task = relationship("TaskModel", back_populates="approvals")

    __table_args__ = (
        Index("ix_approvals_task_id", "task_id"),
        Index("ix_approvals_status", "status"),
    )

class ExecutionModel(Base):
    __tablename__ = "executions"

    execution_id = Column(String(36), primary_key=True)
    task_id = Column(String(36), ForeignKey("tasks.task_id", ondelete="CASCADE"), nullable=False)
    step_id = Column(String(100), nullable=False)
    tool_name = Column(String(100), nullable=False)
    operation = Column(String(100), nullable=False)
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)
    status = Column(String(50), nullable=False)
    risk_level = Column(String(50), nullable=True)
    output_summary = Column(Text, nullable=True)
    error = Column(Text, nullable=True)
    retry_number = Column(Integer, default=0, nullable=False)

    task = relationship("TaskModel", back_populates="executions")

    __table_args__ = (
        Index("ix_executions_task_id", "task_id"),
        Index("ix_executions_started_at", "started_at"),
    )

class EventModel(Base):
    __tablename__ = "events"

    event_id = Column(String(36), primary_key=True)
    task_id = Column(String(36), ForeignKey("tasks.task_id", ondelete="CASCADE"), nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False)
    event_type = Column(String(50), nullable=False)
    step_id = Column(String(100), nullable=True)
    payload = Column(JSON, nullable=True)

    task = relationship("TaskModel", back_populates="events")

    __table_args__ = (
        Index("ix_events_task_id", "task_id"),
        Index("ix_events_timestamp", "timestamp"),
        Index("ix_events_event_type", "event_type"),
    )


class AgentPerformanceModel(Base):
    __tablename__ = "agent_performance"

    record_id = Column(String(36), primary_key=True)
    agent_type = Column(String(50), nullable=False)
    metrics = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_agent_performance_agent_type", "agent_type"),
        Index("ix_agent_performance_updated_at", "updated_at"),
    )


class TaskHistoryModel(Base):
    __tablename__ = "task_history"

    history_id = Column(String(36), primary_key=True)
    task_id = Column(String(36), ForeignKey("tasks.task_id", ondelete="CASCADE"), nullable=False)
    task_category = Column(String(100), nullable=False)
    strategy_used = Column(String(100), nullable=False)
    agents_involved = Column(JSON, nullable=True)
    success = Column(Integer, default=0, nullable=False)
    duration_seconds = Column(Integer, default=0, nullable=False)
    history_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_task_history_task_id", "task_id"),
        Index("ix_task_history_category", "task_category"),
    )


class TaskStrategyModel(Base):
    __tablename__ = "task_strategies"

    strategy_id = Column(String(36), primary_key=True)
    task_id = Column(String(36), ForeignKey("tasks.task_id", ondelete="CASCADE"), nullable=False)
    strategy = Column(String(100), nullable=False)
    strategy_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_task_strategies_task_id", "task_id"),
    )


class FailurePatternModel(Base):
    __tablename__ = "failure_patterns"

    pattern_id = Column(String(36), primary_key=True)
    category = Column(String(100), nullable=False)
    occurrence_count = Column(Integer, default=1, nullable=False)
    resolution = Column(Text, nullable=True)
    pattern_metadata = Column(JSON, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_failure_patterns_category", "category"),
    )


class StrategyEvaluationModel(Base):
    __tablename__ = "strategy_evaluations"

    eval_id = Column(String(36), primary_key=True)
    task_id = Column(String(36), ForeignKey("tasks.task_id", ondelete="CASCADE"), nullable=False)
    strategy = Column(String(100), nullable=False)
    score = Column(Integer, default=0, nullable=False)
    eval_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_strategy_evaluations_task_id", "task_id"),
    )


class PlanEvaluationModel(Base):
    __tablename__ = "plan_evaluations"

    eval_id = Column(String(36), primary_key=True)
    task_id = Column(String(36), ForeignKey("tasks.task_id", ondelete="CASCADE"), nullable=False)
    score = Column(Integer, default=0, nullable=False)
    plan_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_plan_evaluations_task_id", "task_id"),
    )


class RoutingDecisionModel(Base):
    __tablename__ = "routing_decisions"

    decision_id = Column(String(36), primary_key=True)
    task_id = Column(String(36), ForeignKey("tasks.task_id", ondelete="CASCADE"), nullable=False)
    task_category = Column(String(100), nullable=False)
    provider = Column(String(50), nullable=False)
    model = Column(String(100), nullable=False)
    reason = Column(Text, nullable=False)
    confidence = Column(Float, default=0.0, nullable=False)
    estimated_cost = Column(Float, default=0.0, nullable=False)
    estimated_latency_ms = Column(Float, default=0.0, nullable=False)
    routing_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_routing_decisions_task_id", "task_id"),
        Index("ix_routing_decisions_created_at", "created_at"),
    )


class ExecutionEvaluationModel(Base):
    __tablename__ = "execution_evaluations"

    evaluation_id = Column(String(36), primary_key=True)
    task_id = Column(String(36), ForeignKey("tasks.task_id", ondelete="CASCADE"), nullable=False)
    success = Column(Boolean, default=False, nullable=False)
    quality_score = Column(Float, default=0.0, nullable=False)
    efficiency_score = Column(Float, default=0.0, nullable=False)
    safety_score = Column(Float, default=0.0, nullable=False)
    coordination_score = Column(Float, default=0.0, nullable=False)
    recommendations = Column(JSON, nullable=True)
    evaluation_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_execution_evaluations_task_id", "task_id"),
        Index("ix_execution_evaluations_created_at", "created_at"),
    )


class LearningExperienceModel(Base):
    __tablename__ = "learning_experiences"

    experience_id = Column(String(36), primary_key=True)
    task_id = Column(String(36), nullable=False)
    parent_task_id = Column(String(36), nullable=True)
    task_type = Column(String(100), nullable=False)
    task_description_hash = Column(String(64), nullable=False)
    task_complexity = Column(String(50), nullable=False)
    project_type = Column(String(100), nullable=False)
    framework = Column(String(100), nullable=True)
    selected_strategy = Column(String(100), nullable=False)
    selected_model = Column(String(100), nullable=True)
    selected_agents = Column(JSON, nullable=False)
    decomposition_summary = Column(JSON, nullable=False)
    plan_score = Column(Float, default=0.0, nullable=False)
    resource_budget = Column(JSON, nullable=False)
    execution_duration = Column(Float, default=0.0, nullable=False)
    tool_call_count = Column(Integer, default=0, nullable=False)
    token_usage = Column(Integer, default=0, nullable=False)
    success = Column(Boolean, default=False, nullable=False)
    failure_type = Column(String(100), nullable=True)
    failure_pattern = Column(String(100), nullable=True)
    regression_detected = Column(Boolean, default=False, nullable=False)
    approval_required = Column(Boolean, default=False, nullable=False)
    approval_outcome = Column(String(50), nullable=True)
    security_events = Column(JSON, nullable=False)
    evaluation_score = Column(Float, default=0.0, nullable=False)
    final_outcome = Column(Text, nullable=False)
    task_summary = Column(Text, nullable=True)
    evidence_ids = Column(JSON, nullable=False)
    learning_metadata = Column(JSON, nullable=False)
    timestamp = Column(DateTime, default=lambda: datetime.datetime.now(datetime.timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_learning_experiences_task_id", "task_id"),
        Index("ix_learning_experiences_parent_task_id", "parent_task_id"),
        Index("ix_learning_experiences_task_type", "task_type"),
        Index("ix_learning_experiences_task_complexity", "task_complexity"),
        Index("ix_learning_experiences_selected_strategy", "selected_strategy"),
        Index("ix_learning_experiences_success", "success"),
        Index("ix_learning_experiences_failure_pattern", "failure_pattern"),
        Index("ix_learning_experiences_timestamp", "timestamp"),
        Index("ix_learning_experiences_task_description_hash", "task_description_hash"),
    )


from backend.app.db.database import engine  # noqa: E402

Base.metadata.create_all(bind=engine)
