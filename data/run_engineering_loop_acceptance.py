"""Real local-model acceptance harness; approval remains an explicit external step."""
import json, os, sys, time
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root))
run=root/"tmp"/os.environ.get("AGENTOS_ACCEPTANCE_RUN", "engineering-loop-acceptance")
run.mkdir(parents=True,exist_ok=True)
project=run/"project"
project.mkdir(exist_ok=True)
# Seed only the starting application. Never alter model-generated files.
if not (project/"main.py").exists():
    (project/"main.py").write_text("from fastapi import FastAPI\napp = FastAPI()\n")
os.environ.update(DATABASE_URL="sqlite:///"+(run/"acceptance.db").as_posix(),WORKSPACE_ROOT=str(project),LLM_PROVIDER="ollama",OLLAMA_MODEL="llama3.2:latest")
from backend.app.db.database import init_db
from backend.app.services.multi_agent_service import MultiAgentService
from backend.app.services.task_service import TaskService
from backend.app.security.approval import ApprovalManager
from backend.app.models.approval import ApprovalStatus
from backend.app.services.event_service import EventService
init_db()
# Trace real provider calls without modifying their output or bypassing validation.
from backend.app.llm.ollama import OllamaProvider
_original_generate = OllamaProvider.generate
def traced_generate(self, prompt, **kwargs):
    stamp = str(time.time_ns())
    started = time.monotonic()
    try:
        response = _original_generate(self, prompt, **kwargs)
        (run / ("model-" + stamp + ".json")).write_text(json.dumps({"model": self.model, "prompt": prompt, "response": response, "seconds": time.monotonic()-started}, indent=2), encoding="utf-8")
        return response
    except Exception as exc:
        (run / ("model-" + stamp + ".json")).write_text(json.dumps({"model": self.model, "error": str(exc), "seconds": time.monotonic()-started}, indent=2), encoding="utf-8")
        raise
OllamaProvider.generate = traced_generate
commands=["Create a simple API endpoint in main.py and add a test for it.","Run the tests, find the bugs, and explain why they are failing.","Fix the issues."]
for index, command in enumerate(commands,1):
    if str(index) not in os.environ.get("AGENTOS_ACCEPTANCE_PHASES", "1,2,3").split(","):
        continue
    if (run/f"result-{index}.json").exists():
        continue
    if index >= 2:
        from backend.app.config.settings import settings
        diagnosis_project=run/"diagnostic-project"
        if not diagnosis_project.exists():
            import shutil
            original=Path("C:/Users/evo/AppData/Local/Temp/AgentOS-engineering-stream-20260921")
            (diagnosis_project/"tests").mkdir(parents=True)
            shutil.copy2(original/"main.py",diagnosis_project/"main.py")
            shutil.copy2(original/"tests/test_main.py",diagnosis_project/"tests/test_main.py")
        settings.WORKSPACE_ROOT=str(diagnosis_project)
    print("START",index,command,flush=True)
    checkpoint=run/f"task-{index}.txt"
    existing=TaskService.get_task(checkpoint.read_text().strip()) if checkpoint.exists() else None
    task=existing or MultiAgentService.start_task(command,sync=True)
    checkpoint.write_text(task.task_id)
    while task.status.value=="WAITING_APPROVAL":
        state=MultiAgentService.get_state(task.task_id)
        pending=state.get("pending_coding_id")
        proposal=state["subtask_results"][pending]["evidence"]["patch"]
        approval=task.approval_id
        (run/"pending.json").write_text(json.dumps({"task_id":task.task_id,"approval_id":approval,"patch":proposal},indent=2))
        print("APPROVAL",index,approval,flush=True)
        gate=run/(approval+".approved")
        while not gate.exists(): time.sleep(1)
        ApprovalManager.resolve_approval(approval,ApprovalStatus.APPROVED,"Reviewed isolated acceptance patch",resolved_by="dev-default")
        MultiAgentService.resume_approval(task.task_id,True)
        task=TaskService.get_task(task.task_id)
    state=MultiAgentService.get_state(task.task_id)
    (run/f"result-{index}.json").write_text(json.dumps({"task":task.model_dump(mode="json"),"state":state,"events":EventService.get_task_events(task.task_id)},default=str,indent=2))
    print("RESULT",index,task.task_id,task.status.value,flush=True)
