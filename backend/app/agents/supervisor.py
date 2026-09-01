"""
AgentOS Phase 5, 12 & 13 — Supervisor Agent.

The central orchestration intelligence of the multi-agent runtime:
- Classifies incoming tasks with TaskClassifier
- Decomposes instructions via TaskDecomposer & RepoIntelligence
- Assembles bounded context through ContextEngine
- Stores immutable plan, diagnosis, test, and review artifacts via ArtifactService
- Uses AgentProtocol for typed, auditable messaging
- Manages failure recovery, replanning loops, and retry policies
- Never executes mutating tools directly
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.app.agents.debugger import DebuggerAgent
from backend.app.agents.domain_experts import CybersecurityAgent, DataEngineerAgent, DevOpsAgent, TestingAgent
from backend.app.agents.reviewer import ReviewerAgent
from backend.app.agents.specialized import CodingAgent, DocumentationAgent, ResearchAgent, SecurityAgent
from backend.app.llm.base import BaseLLMProvider
from backend.app.llm.factory import get_llm_provider
from backend.app.models.agent import Observation, PlanStep
from backend.app.models.engineering_workflow import (
    DiagnosisReport,
    EngineeringWorkflowSummary,
    ReplanningDecision,
    ReviewVerdictPayload,
)
from backend.app.models.multi_agent import (
    AgentMessage,
    AgentResult,
    AgentStatus,
    AgentType,
    SubTask,
)
from backend.app.services.agent_message_bus import AgentMessageBus
from backend.app.services.agent_protocol import AgentProtocol, MessageType
from backend.app.services.artifact_service import ArtifactService, ArtifactType
from backend.app.services.concurrency_manager import ConcurrencyManager
from backend.app.services.context_engine import ContextEngine
from backend.app.services.event_service import EventService
from backend.app.services.model_router import ModelRouter, ModelTaskType
from backend.app.services.parallel_executor import ParallelExecutor
from backend.app.services.repo_intelligence import RepoIntelligence
from backend.app.services.result_aggregator import ResultAggregator
from backend.app.services.task_classifier import TaskClassification, TaskClassifier
from backend.app.services.task_decomposer import TaskDecomposer

logger = logging.getLogger("agentos.supervisor")


class SupervisorAgent:
    """Oversees task decomposition, agent assignment, failure recovery, and execution coordination."""

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None) -> None:
        self.llm = llm_provider or ModelRouter.get_provider(ModelTaskType.REASONING)
        self.decomposer = TaskDecomposer(llm_provider=self.llm)
        self.executor = ParallelExecutor()
        self.aggregator = ResultAggregator()
        self.intelligence = RepoIntelligence()
        self.context_engine = ContextEngine()

        # Instantiate specialized agent handlers
        self.research_agent = ResearchAgent(llm_provider=self.llm)
        self.coding_agent = CodingAgent(llm_provider=self.llm)
        self.debugger_agent = DebuggerAgent(llm_provider=self.llm)
        self.documentation_agent = DocumentationAgent(llm_provider=self.llm)
        self.security_agent = SecurityAgent(llm_provider=self.llm)
        self.reviewer_agent = ReviewerAgent(self.llm)
        self.testing_agent = TestingAgent(llm_provider=self.llm)
        self.data_engineer_agent = DataEngineerAgent(llm_provider=self.llm)
        self.devops_agent = DevOpsAgent(llm_provider=self.llm)
        self.cybersecurity_agent = CybersecurityAgent(llm_provider=self.llm)

    def plan_and_decompose(self, instruction: str, task_id: str) -> List[SubTask]:
        """Classify request, build context, decompose subtasks, and persist plan artifact."""
        # 1. Task classification
        classification: TaskClassification = TaskClassifier.classify(instruction)
        EventService.record_event(
            task_id,
            "TASK_CLASSIFIED",
            payload=classification.model_dump(),
        )

        # 2. Bounded Context assembly
        context_bundle = self.context_engine.assemble_context(
            task_id=task_id,
            instruction=instruction,
            target_agent=AgentType.SUPERVISOR,
            token_budget=4000,
        )
        ArtifactService.save(
            task_id=task_id,
            agent_id="supervisor",
            artifact_type=ArtifactType.CONTEXT,
            content=context_bundle.model_dump(),
        )

        # 3. Decomposition
        rel_files = list(context_bundle.files.keys())
        subtasks = self.decomposer.decompose(instruction, task_id=task_id)

        # Enhance subtasks with resolved target files if not explicitly present
        if rel_files:
            for st in subtasks:
                if not st.target_files and st.assigned_agent in (AgentType.RESEARCH, AgentType.CODING, AgentType.TESTING):
                    st.target_files = rel_files

        # 4. Save immutable PLAN artifact
        ArtifactService.save(
            task_id=task_id,
            agent_id="supervisor",
            artifact_type=ArtifactType.PLAN,
            content={
                "classification": classification.model_dump(),
                "subtasks": [st.model_dump() for st in subtasks],
                "relevant_files": rel_files,
            },
        )

        # 5. Broadcast assignments via typed protocol and message bus
        for st in subtasks:
            AgentProtocol.send(
                task_id=task_id,
                sender=AgentType.SUPERVISOR,
                recipient=st.assigned_agent,
                message_type=MessageType.TASK_ASSIGNMENT,
                payload={"subtask_id": st.subtask_id, "description": st.description, "target_files": st.target_files},
                subtask_id=st.subtask_id,
            )
            AgentMessageBus.send(AgentMessage(
                message_id="",
                task_id=task_id,
                sender_agent=AgentType.SUPERVISOR,
                recipient_agent=st.assigned_agent,
                message_type="TASK_ASSIGNMENT",
                payload={"subtask_id": st.subtask_id, "description": st.description, "target_files": st.target_files},
            ))
        return subtasks

    def adaptive_decompose(
        self,
        instruction: str,
        task_id: str,
        strategy: str = "DIRECT",
        complexity: str = "medium",
    ) -> List[SubTask]:
        """Adaptive decomposition using strategy and complexity analysis."""
        subtasks = self.decomposer.adaptive_decompose(
            instruction, task_id=task_id, strategy=strategy, complexity=complexity,
        )
        for st in subtasks:
            AgentProtocol.send(
                task_id=task_id,
                sender=AgentType.SUPERVISOR,
                recipient=st.assigned_agent,
                message_type=MessageType.TASK_ASSIGNMENT,
                payload={"subtask_id": st.subtask_id, "description": st.description},
                subtask_id=st.subtask_id,
            )
        return subtasks

    def handle_subtask_failure(
        self,
        subtask: SubTask,
        failed_result: AgentResult,
        task_id: str,
    ) -> ReplanningDecision:
        """Evaluate failure and decide recovery strategy (RETRY, REROUTE, REPLAN, ABORT)."""
        EventService.record_event(
            task_id=task_id,
            event_type="REPLAN_TRIGGERED",
            payload={
                "subtask_id": subtask.subtask_id,
                "agent": subtask.assigned_agent.value,
                "error": failed_result.error or failed_result.summary,
            }
        )

        # Route based on failure characteristics
        if subtask.assigned_agent == AgentType.TESTING:
            decision = ReplanningDecision(
                trigger_event="TEST_FAILURE",
                failed_subtask_id=subtask.subtask_id,
                reason="Tests failed during execution; diagnosing defect.",
                strategy="REROUTE",
                assigned_agent=AgentType.DEBUGGER.value,
                recovery_instructions=f"Diagnose failure in {subtask.target_files}: {failed_result.summary}",
            )
        elif "permission" in (failed_result.error or "").lower() or "denied" in (failed_result.error or "").lower():
            decision = ReplanningDecision(
                trigger_event="SECURITY_VIOLATION",
                failed_subtask_id=subtask.subtask_id,
                reason="Permission denied under security policy; aborting execution.",
                strategy="ABORT",
                recovery_instructions="Halt execution due to authorization failure.",
            )
        elif subtask.assigned_agent == AgentType.RESEARCH:
            decision = ReplanningDecision(
                trigger_event="TOOL_ERROR",
                failed_subtask_id=subtask.subtask_id,
                reason="File read error during research; retrying with root context.",
                strategy="RETRY",
                assigned_agent=AgentType.RESEARCH.value,
                recovery_instructions="Re-read workspace overview and retry search.",
            )
        else:
            decision = ReplanningDecision(
                trigger_event="AGENT_FAILURE",
                failed_subtask_id=subtask.subtask_id,
                reason=f"Execution error in {subtask.assigned_agent.value}; retrying with fallback guidance.",
                strategy="RETRY",
                assigned_agent=subtask.assigned_agent.value,
                recovery_instructions=f"Retry {subtask.description} with updated parameters.",
            )

        AgentProtocol.send(
            task_id=task_id,
            sender=AgentType.SUPERVISOR,
            recipient=AgentType(decision.assigned_agent) if decision.assigned_agent in [a.value for a in AgentType] else AgentType.SUPERVISOR,
            message_type=MessageType.RECOVERY_REQUEST,
            payload=decision.model_dump(),
            subtask_id=subtask.subtask_id,
        )
        return decision

    def execute_subtask(self, subtask: SubTask) -> AgentResult:
        """Route a single subtask with concurrency management and artifact preservation."""
        agent_type = subtask.assigned_agent
        ConcurrencyManager.acquire_agent_slot(agent_type)
        try:
            if agent_type == AgentType.RESEARCH:
                res = self.research_agent.execute(subtask)
            elif agent_type == AgentType.CODING:
                res = self.coding_agent.execute(subtask)
                if res.evidence.get("patch"):
                    ArtifactService.save(
                        task_id=subtask.task_id,
                        agent_id="coding",
                        artifact_type=ArtifactType.PATCH,
                        content=res.evidence["patch"],
                    )
            elif agent_type == AgentType.DOCUMENTATION:
                res = self.documentation_agent.execute(subtask)
            elif agent_type == AgentType.SECURITY:
                res = self.security_agent.execute(subtask)
                ArtifactService.save(
                    task_id=subtask.task_id,
                    agent_id="security",
                    artifact_type=ArtifactType.SECURITY_FINDINGS,
                    content=res.evidence,
                )
            elif agent_type == AgentType.DEBUGGER:
                test_res = self.debugger_agent.run_tests()
                passed = test_res.get("data", {}).get("passed", False) if isinstance(test_res, dict) else False
                
                diagnosis = DiagnosisReport(
                    symptoms=["Test failure detected" if not passed else "Diagnostics probe run"],
                    suspected_files=subtask.target_files or [],
                    root_cause="Operator mismatch or syntax defect" if not passed else "No critical defects detected",
                    suggested_fix="Apply verified patch via CodingAgent",
                    confidence_score=0.95,
                )
                ArtifactService.save(
                    task_id=subtask.task_id,
                    agent_id="debugger",
                    artifact_type=ArtifactType.DIAGNOSIS,
                    content=diagnosis.model_dump(),
                )
                res = AgentResult(
                    subtask_id=subtask.subtask_id,
                    agent_type=AgentType.DEBUGGER,
                    status=AgentStatus.COMPLETED,
                    summary=f"Debugger completed root cause diagnosis (root_cause='{diagnosis.root_cause}').",
                    evidence={"test_res": test_res, "diagnosis": diagnosis.model_dump()},
                )
            elif agent_type == AgentType.REVIEWER:
                step = PlanStep(step_id=subtask.subtask_id, tool_name="review", operation="eval", description=subtask.description)
                obs = Observation(
                    step_id=subtask.subtask_id,
                    tool_name="review",
                    operation="eval",
                    success=True,
                    data=subtask.input_data,
                )
                verdict, reasoning = self.reviewer_agent.review(step, obs)
                review_payload = ReviewVerdictPayload(
                    approved=verdict == "SUCCESS",
                    verdict="APPROVE" if verdict == "SUCCESS" else "REVISE",
                    quality_score=0.95 if verdict == "SUCCESS" else 0.6,
                    recommendations=[reasoning],
                    summary=f"Review verdict: {verdict}. {reasoning}",
                )
                ArtifactService.save(
                    task_id=subtask.task_id,
                    agent_id="reviewer",
                    artifact_type=ArtifactType.REVIEW,
                    content=review_payload.model_dump(),
                )
                res = AgentResult(
                    subtask_id=subtask.subtask_id,
                    agent_type=AgentType.REVIEWER,
                    status=AgentStatus.COMPLETED,
                    summary=f"Review verdict: {verdict}. {reasoning}",
                    evidence={"verdict": verdict, "reasoning": reasoning, "structured_payload": review_payload.model_dump()},
                )
            elif agent_type == AgentType.TESTING:
                res = self.testing_agent.execute(subtask)
                if res.evidence.get("structured_report"):
                    ArtifactService.save(
                        task_id=subtask.task_id,
                        agent_id="testing",
                        artifact_type=ArtifactType.TEST_REPORT,
                        content=res.evidence["structured_report"],
                    )
            elif agent_type == AgentType.DATA_ENGINEER:
                res = self.data_engineer_agent.execute(subtask)
                if res.evidence.get("structured_report"):
                    ArtifactService.save(
                        task_id=subtask.task_id,
                        agent_id="data_engineer",
                        artifact_type=ArtifactType.DATA_PROFILE,
                        content=res.evidence["structured_report"],
                    )
            elif agent_type == AgentType.DEVOPS:
                res = self.devops_agent.execute(subtask)
                if res.evidence.get("structured_report"):
                    ArtifactService.save(
                        task_id=subtask.task_id,
                        agent_id="devops",
                        artifact_type=ArtifactType.DEVOPS_ANALYSIS,
                        content=res.evidence["structured_report"],
                    )
            elif agent_type == AgentType.CYBERSECURITY:
                res = self.cybersecurity_agent.execute(subtask)
            else:
                res = AgentResult(
                    subtask_id=subtask.subtask_id,
                    agent_type=agent_type,
                    status=AgentStatus.FAILED,
                    summary=f"Unknown agent type {agent_type.value}",
                    error=f"Unrecognized agent {agent_type.value}",
                )
        except Exception as exc:
            logger.error("Error executing subtask %s with agent %s: %s", subtask.subtask_id, agent_type, exc)
            res = AgentResult(
                subtask_id=subtask.subtask_id,
                agent_type=agent_type,
                status=AgentStatus.FAILED,
                summary=f"Execution exception: {exc}",
                error=str(exc),
            )
        finally:
            ConcurrencyManager.release_agent_slot(agent_type)

        return res

    def synthesize_response(self, instruction: str, aggregated: Dict[str, Any], task_id: str) -> str:
        """Generate final user-facing multi-agent summary report and save summary artifact."""
        status_str = "COMPLETED" if aggregated.get("all_succeeded") else "PARTIAL_OR_FAILED"
        summary_text = (
            f"AgentOS Multi-Agent Collaboration Report\n"
            f"=========================================\n"
            f"Task ID: {task_id}\n"
            f"Instruction: {instruction}\n"
            f"Status: {status_str}\n"
            f"Subtasks Completed: {aggregated.get('completed_count')}/{aggregated.get('total_subtasks')}\n"
            f"Files Modified: {aggregated.get('files_modified', [])}\n"
            f"Conflicts Detected: {len(aggregated.get('conflicts', []))}\n"
        )
        ArtifactService.save(
            task_id=task_id,
            agent_id="supervisor",
            artifact_type=ArtifactType.FINAL_SUMMARY,
            content={
                "status": status_str,
                "summary_text": summary_text,
                "completed_count": aggregated.get("completed_count"),
                "total_subtasks": aggregated.get("total_subtasks"),
                "files_modified": aggregated.get("files_modified", []),
            },
        )
        return summary_text
