import json
from types import SimpleNamespace
import pytest
from backend.app.config.settings import settings
from backend.app.llm.mock import MockLLMProvider
from backend.app.llm.structured import GeneratedFiles, generate_structured, ModelOutputError
from backend.app.agents.specialized import CodingAgent
from backend.app.models.multi_agent import SubTask, AgentType, AgentStatus, AgentResult
from backend.app.services.task_decomposer import TaskDecomposer
from backend.app.services.engineering_intent import engineering_intent, valid_test_result
from backend.app.workflows import multi_agent_nodes as nodes


def proposal(*paths, value=2):
    return json.dumps({"files":[{"path":p,"content":f"VALUE = {value}\n"} for p in paths]})


def test_sequential_applied_modifications_and_recovery_have_fresh_originals(tmp_path, monkeypatch):
    monkeypatch.setattr(settings,"WORKSPACE_ROOT",str(tmp_path))
    (tmp_path/"value.py").write_text("VALUE = 1\n")
    agent=CodingAgent(MockLLMProvider(response_queue=[proposal("value.py",value=n) for n in (2,3,4)]))
    hashes=[]
    for index in range(3):
        st=SubTask(task_id="sequential",subtask_id=f"recovery-{index}",description="Update",assigned_agent=AgentType.CODING,target_files=["value.py"])
        patch=agent.formulate_patch(st)
        hashes.append(patch.files[0].original_hash)
        assert agent.apply_patch(patch)["applied"]
        assert (tmp_path/"value.py").read_text()==f"VALUE = {index+2}\n"
    assert len(set(hashes))==3


@pytest.mark.parametrize("paths",[("value.py","value.py"),("value.py","./value.py"),("tests/x.py","tests\\x.py")])
def test_duplicate_proposal_rejected_and_bounded(paths):
    model=MockLLMProvider(response_queue=[proposal(*paths),proposal(*paths)])
    with pytest.raises(ModelOutputError): generate_structured(model,"Generate",GeneratedFiles)


def test_duplicate_repair_keeps_only_valid_complete_proposal():
    model=MockLLMProvider(response_queue=[proposal("value.py","value.py"),proposal("value.py")])
    assert len(generate_structured(model,"Generate",GeneratedFiles).files)==1


@pytest.mark.parametrize("path",[".env","../escape.py","C:/escape.py"])
def test_unsafe_targets_remain_rejected(tmp_path,monkeypatch,path):
    monkeypatch.setattr(settings,"WORKSPACE_ROOT",str(tmp_path))
    agent=CodingAgent(MockLLMProvider(response_queue=[proposal(path),proposal(path)]))
    with pytest.raises(ValueError): agent.formulate_patch(SubTask(task_id="unsafe",subtask_id="code",description="Write",assigned_agent=AgentType.CODING))


@pytest.mark.parametrize("instruction,agents",[
    ("Run tests",["testing"]),
    ("Run the tests, find the bugs, and explain why they are failing.",["testing","debugger"]),
    ("Find bugs",["testing","debugger"]),
    ("Explain failing tests",["testing","debugger"]),
    ("Fix the issues.",["testing","debugger","coding","testing","reviewer"]),
])
def test_intent_aware_plan(instruction,agents):
    assert [s.assigned_agent.value for s in TaskDecomposer(MockLLMProvider()).decompose(instruction)]==agents


def result(infra=False):
    return AgentResult(subtask_id="run-tests",agent_type=AgentType.TESTING,status=AgentStatus.FAILED,summary="1 failed",evidence={"passed":False,"execution_failed":infra,"test_results":{"exit_code":1,"stdout":"actual traceback","counts":{"failed":1}}})


@pytest.mark.parametrize("instruction",["Run tests","Find bugs","Explain failing tests","Fix bugs"])
def test_failure_evidence_reaches_next_operation(monkeypatch,instruction):
    plan=TaskDecomposer(MockLLMProvider()).decompose(instruction,task_id="intent")
    r=result()
    supervisor=SimpleNamespace(executor=SimpleNamespace(execute_batch=lambda **kw:{r.subtask_id:r}),execute_subtask=None)
    monkeypatch.setattr(nodes,"_supervisor",lambda state:supervisor)
    state={"task_id":"intent","user_instruction":instruction,"subtasks":[s.model_dump() for s in plan]}
    out=nodes.parallel_execution_node(state)
    assert out["status"]=="EXECUTING"
    assert out["subtask_results"][r.subtask_id]["evidence"]["test_results"]["stdout"]=="actual traceback"


def test_runner_infrastructure_failure_is_fatal(monkeypatch):
    r=result(True)
    assert not valid_test_result(r)
    monkeypatch.setattr(nodes,"_supervisor",lambda state:SimpleNamespace(executor=SimpleNamespace(execute_batch=lambda **kw:{r.subtask_id:r}),execute_subtask=None))
    state={"task_id":"infra","user_instruction":"Find bugs","subtasks":[s.model_dump() for s in TaskDecomposer().decompose("Find bugs","infra")]}
    assert nodes.parallel_execution_node(state)["status"]=="FAILED"


def test_unrecovered_fix_cannot_complete(monkeypatch):
    from backend.app.services.result_aggregator import ResultAggregator
    monkeypatch.setattr(nodes,"_supervisor",lambda state:SimpleNamespace(aggregator=ResultAggregator(),synthesize_response=lambda *a,**k:"summary"))
    r=result()
    state={"task_id":"verdict","user_instruction":"Make all tests pass","subtask_results":{"run-tests":r.model_dump()},"subtasks":[{}],"completed_subtask_ids":["run-tests"]}
    assert nodes.merge_results_node(state)["status"]=="FAILED"
    state["user_instruction"]="Run tests"
    assert nodes.merge_results_node(state)["status"]=="COMPLETED"


def test_debugger_uses_original_evidence_without_rerunning(tmp_path,monkeypatch):
    from backend.app.agents.supervisor import SupervisorAgent
    from backend.app.models.coding import DebugDiagnosis
    monkeypatch.setattr(settings,"WORKSPACE_ROOT",str(tmp_path))
    (tmp_path/"test_value.py").write_text("def test_value():\n    assert 1 == 2\n")
    supervisor=SupervisorAgent(MockLLMProvider())
    monkeypatch.setattr(supervisor.debugger_agent,"run_tests",lambda:pytest.fail("must reuse captured run"))
    captured=[]
    def diagnose(failures,investigation):
        captured.append(investigation.evidence)
        return DebugDiagnosis(root_cause="Mismatched values",explanation="Evidence shows 1 != 2",recommended_fix="Correct the value",affected_files=["test_value.py","../../library.py"],confidence=0.9)
    monkeypatch.setattr(supervisor.debugger_agent,"diagnose",diagnose)
    r=result()
    r.evidence["test_results"]["stdout"]="___ test_value ___\nE   assert 1 == 2\ntest_value.py:2: AssertionError\n=== 1 failed ==="
    st=SubTask(task_id="diagnosis",subtask_id="diagnose",assigned_agent=AgentType.DEBUGGER,description="Explain failure",input_data={"run-tests":r.model_dump()})
    out=supervisor.execute_subtask(st)
    assert out.status==AgentStatus.COMPLETED
    assert "assert 1 == 2" in captured[0]
    assert out.evidence["test_res"]["data"]==r.evidence["test_results"]
    assert out.evidence["structured_report"]["issues"][0]["line"]==2
    assert "Evidence shows" in out.evidence["diagnosis"]["root_cause"]
    assert out.evidence["diagnosis"]["suspected_files"]==["test_value.py"]


def test_existing_target_identity_uses_filesystem_normalization(tmp_path,monkeypatch):
    import os
    monkeypatch.setattr(settings,"WORKSPACE_ROOT",str(tmp_path))
    (tmp_path/"value.py").write_text("VALUE = 1\n")
    alias="VALUE.py" if os.name=="nt" else "./value.py"
    calls=[]
    class Model(MockLLMProvider):
        def generate(self,prompt,**kwargs):
            calls.append(prompt)
            return proposal(alias)
    agent=CodingAgent(Model())
    patch=agent.formulate_patch(SubTask(task_id="normalized",subtask_id="code",description="Update",assigned_agent=AgentType.CODING,target_files=["value.py"]))
    assert len(calls)==1
    assert agent.apply_patch(patch)["applied"]
    assert (tmp_path/"value.py").read_text()=="VALUE = 2\n"
