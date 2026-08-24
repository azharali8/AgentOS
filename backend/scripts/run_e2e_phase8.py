"""
Phase 8 End-to-End Demonstrations
"""

import sys
import os

from backend.app.agents.supervisor import SupervisorAgent
from backend.app.models.multi_agent import SubTask, AgentType

def run_e2e():
    supervisor = SupervisorAgent()

    print("Running E2E #1: Data Engineering...")
    st_data = SubTask(task_id="e2e1", subtask_id="s1", description="Profile and clean user_data.csv", assigned_agent=AgentType.DATA_ENGINEER)
    res_data = supervisor.execute_subtask(st_data)
    print(f"E2E #1 Result: {res_data.status} | {res_data.summary}")
    assert res_data.status == "completed"

    print("Running E2E #2: Debugging...")
    st_debug = SubTask(task_id="e2e2", subtask_id="s1", description="Diagnose test_auth.py failure", assigned_agent=AgentType.DEBUGGER)
    res_debug = supervisor.execute_subtask(st_debug)
    print(f"E2E #2 Result: {res_debug.status} | {res_debug.summary}")
    assert res_debug.status == "completed"

    print("Running E2E #3: DevOps...")
    st_devops = SubTask(task_id="e2e3", subtask_id="s1", description="Generate Dockerfile for app", assigned_agent=AgentType.DEVOPS)
    res_devops = supervisor.execute_subtask(st_devops)
    print(f"E2E #3 Result: {res_devops.status} | {res_devops.summary}")
    assert res_devops.status == "completed"

    print("Running E2E #4: Cybersecurity...")
    st_cyber = SubTask(task_id="e2e4", subtask_id="s1", description="Perform deep security audit", assigned_agent=AgentType.CYBERSECURITY)
    res_cyber = supervisor.execute_subtask(st_cyber)
    print(f"E2E #4 Result: {res_cyber.status} | {res_cyber.summary}")
    assert res_cyber.status == "completed"

    print("Running E2E #5: Multi-Agent Collaboration...")
    # Multi-agent mock execution through supervisor plan
    subtasks = supervisor.plan_and_decompose("Analyze security, clean data, and test the resulting application", task_id="e2e5")
    assert len(subtasks) > 0
    print(f"E2E #5 Result: Planned {len(subtasks)} tasks successfully.")

    print("ALL E2E DEMONSTRATIONS SUCCESSFUL")

if __name__ == "__main__":
    run_e2e()
