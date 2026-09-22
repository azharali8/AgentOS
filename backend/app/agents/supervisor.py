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
        self.debugger_agent = DebuggerAgent(llm_provider=self.llm, strict=True)
        self.documentation_agent = DocumentationAgent(llm_provider=self.llm)
        self.security_agent = SecurityAgent(llm_provider=self.llm)
        self.reviewer_agent = ReviewerAgent(self.llm, strict=True)
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
        # A model plan cannot omit executable verification of a coding task.
        coding_ids = [s.subtask_id for s in subtasks if s.assigned_agent == AgentType.CODING]
        if coding_ids:
            tests = [s for s in subtasks if s.assigned_agent == AgentType.TESTING]
            reviews = [s for s in subtasks if s.assigned_agent == AgentType.REVIEWER]
            used = {s.subtask_id for s in subtasks}
            def unique_id(prefix):
                while prefix in used:
                    prefix += "-next"
                used.add(prefix)
                return prefix
            if not tests:
                tests = [SubTask(task_id=task_id, subtask_id=unique_id("verify-tests"),
                                 description="Run the full test suite after applying the proposed implementation",
                                 assigned_agent=AgentType.TESTING, dependencies=coding_ids)]
                subtasks.extend(tests)
                for review in reviews:
                    review.dependencies = list(dict.fromkeys(review.dependencies + [s.subtask_id for s in tests]))
            if not reviews:
                reviews = [SubTask(task_id=task_id, subtask_id=unique_id("verify-review"),
                                   description="Review the implementation and actual test evidence against the original request",
                                   assigned_agent=AgentType.REVIEWER, dependencies=[s.subtask_id for s in tests])]
                subtasks.extend(reviews)
            # Validate order rather than creating cycles by rewriting model dependencies.
            by_id = {s.subtask_id: s for s in subtasks}
            def ancestors(s, seen=None):
                seen = set() if seen is None else seen
                for dep in s.dependencies:
                    if dep not in by_id:
                        raise ValueError(f"Unknown planned dependency: {dep}")
                    if dep not in seen:
                        seen.add(dep)
                        ancestors(by_id[dep], seen)
                return seen
            if not any(set(coding_ids).issubset(ancestors(s)) for s in tests):
                raise ValueError("Engineering plan must run tests after all coding changes")
            if not any({s.subtask_id for s in tests}.issubset(ancestors(r)) for r in reviews):
                raise ValueError("Engineering plan must review actual test results")
            from backend.app.config.settings import settings
            if len(subtasks) > settings.MAX_SUBTASKS:
                raise ValueError("Verified engineering plan exceeds subtask limit")

        # Enhance subtasks with resolved target files if not explicitly present
        if rel_files:
            for st in subtasks:
                if not st.target_files and st.assigned_agent in (AgentType.RESEARCH, AgentType.CODING):
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
            EventService.record_event(subtask.task_id, "SUBTASK_STARTED", payload={
                "subtask_id": subtask.subtask_id, "agent": agent_type.value,
                "description": subtask.description, "delegated_by": "Supervisor",
            })
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
                # Diagnose the observed run, not a fresh run which may differ.
                sources = [v for v in subtask.input_data.values() if isinstance(v, dict) and v.get("agent_type") == AgentType.TESTING.value]
                sources += subtask.input_data.get("failure_history", [])
                source = sources[-1] if sources else None
                if source:
                    from backend.app.services.engineering_intent import valid_test_result
                    if not valid_test_result(source):
                        raise RuntimeError("WORKFLOW_ERROR: no valid test execution to diagnose")
                    data_dict = source["evidence"]["test_results"]
                    test_res = {"success": True, "data": data_dict}
                else:
                    test_res = self.debugger_agent.run_tests()
                    data_dict = test_res.get("data") if isinstance(test_res, dict) else None
                passed = data_dict.get("passed", False) if isinstance(data_dict, dict) else False

                
                from backend.app.agents.failure_analyzer import FailureAnalyzerAgent
                from backend.app.models.coding import InvestigationResult
                from backend.app.llm.evidence import failure_excerpt
                data = data_dict or {}
                failures = FailureAnalyzerAgent(llm_provider=self.llm).analyze(data.get("stdout", ""), data.get("stderr", ""))
                from backend.app.services.test_service import TestService
                structured_report = TestService.parse_test_report(data)
                def workspace_sources(paths):
                    from backend.app.services.workspace_service import WorkspaceService
                    valid = []
                    for candidate in paths:
                        try:
                            path = WorkspaceService.validate_path(candidate)
                            if path.is_file():
                                valid.append(path.relative_to(WorkspaceService.get_workspace_root()).as_posix())
                        except ValueError:
                            # Tracebacks contain library frames. Preserve them as
                            # evidence, never promote them to mutation targets.
                            continue
                    return list(dict.fromkeys(valid))
                issue_files = [i["test_file"] for i in structured_report.get("issues", []) if i.get("test_file")]
                if issue_files:
                    subtask.target_files = workspace_sources(subtask.target_files + issue_files)
                if subtask.input_data.get("changed_files"):
                    subtask.target_files = list(dict.fromkeys(subtask.target_files + subtask.input_data["changed_files"]))
                investigation = InvestigationResult(
                    affected_files=subtask.target_files or [],
                    evidence=f"Exit code: {data.get('exit_code')}; counts: {data.get('counts')}\n"
                             + failure_excerpt(data.get("stdout", "")) + "\n"
                             + str(data.get("stderr", ""))[:800]
                             + "\nSource context: " + str(self.research_agent.execute(subtask).evidence)[:10000],
                )
                actual = self.debugger_agent.diagnose(failures, investigation)
                captured_output = str(data.get("stdout", "")) + "\n" + str(data.get("stderr", ""))
                observed_symptoms = list(dict.fromkeys(
                    i.get("message", "").strip() for i in structured_report.get("issues", [])
                    if i.get("message", "").strip() and i["message"].strip() in captured_output
                ))
                diagnosis = DiagnosisReport(
                    symptoms=observed_symptoms or [f"Test process exited with code {data.get('exit_code')}"],
                    suspected_files=workspace_sources(actual.affected_files + (subtask.target_files or [])),
                    root_cause=actual.root_cause + "\n" + actual.explanation,
                    suggested_fix=actual.recommended_fix,
                    confidence_score=actual.confidence,
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
                    status=AgentStatus.COMPLETED if test_res.get("success") else AgentStatus.FAILED,
                    summary=f"Debugger completed root cause diagnosis (root_cause='{diagnosis.root_cause}').",
                    evidence={"test_res": test_res, "structured_report": structured_report, "diagnosis": diagnosis.model_dump()},
                )
            elif agent_type == AgentType.REVIEWER:
                review_sources = SubTask(task_id=subtask.task_id, subtask_id=subtask.subtask_id,
                                         description=subtask.description, assigned_agent=AgentType.RESEARCH,
                                         target_files=subtask.input_data.get("changed_files", []))
                review_data = {**subtask.input_data, "source_evidence": self.research_agent.execute(review_sources).evidence}
                from backend.app.config.settings import settings
                source_chars = 0
                for path, source in review_data["source_evidence"].items():
                    content = "\n".join(self.coding_agent.reader.read(path, start_line=1, end_line=settings.MAX_LINES_PER_READ).lines)
                    source_chars += len(content)
                    if source_chars > 24000:
                        raise ValueError("Review source budget exceeded; split the coding task")
                    source["content"] = content
                step = PlanStep(step_id=subtask.subtask_id, tool_name="review", operation="eval", description=subtask.description + " Original request: " + str(subtask.input_data.get("user_instruction", "")))
                obs = Observation(
                    step_id=subtask.subtask_id,
                    tool_name="review",
                    operation="eval",
                    success=all(r.get("status") != AgentStatus.FAILED.value for r in subtask.input_data.values() if isinstance(r, dict)),
                    data=review_data,
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
                    status=AgentStatus.COMPLETED if verdict == "SUCCESS" else AgentStatus.FAILED,
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
                error=(str(exc) if "_ERROR" in str(exc) else ("TARGET_VALIDATION_ERROR: " if "target" in str(exc).lower() or "workspace" in str(exc).lower() or "sensitive" in str(exc).lower() or "traversal" in str(exc).lower() else "WORKFLOW_ERROR: ") + str(exc)),
                evidence={"error_type": "MODEL_OUTPUT_ERROR" if "MODEL_OUTPUT_ERROR" in str(exc) else "TARGET_VALIDATION_ERROR" if "target" in str(exc).lower() or "workspace" in str(exc).lower() or "sensitive" in str(exc).lower() or "traversal" in str(exc).lower() else "WORKFLOW_ERROR"},
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
        for result in aggregated.get("evidence", {}).values():
            evidence = result.get("evidence", {})
            if result.get("agent") == AgentType.TESTING.value:
                summary_text += "\n" + result.get("summary", "")
            if evidence.get("diagnosis"):
                diagnosis = evidence["diagnosis"]
                summary_text += "\n" + diagnosis.get("root_cause", "") + "\nSuggested fix: " + diagnosis.get("suggested_fix", "")
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
