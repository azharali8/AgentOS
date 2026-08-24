"""
AgentOS SDK Example: Create and inspect a task.
"""

from agentos import AgentOS

def main():
    client = AgentOS(base_url="http://localhost:8000")
    
    # 1. Create a task
    task = client.tasks.create(
        task="Investigate repository test coverage and report gaps",
        priority=2,
    )
    print(f"Created task: {task.task_id} (Status: {task.status})")

    # 2. Check task status
    status = client.tasks.status(task.task_id)
    print(f"Task status details: {status}")

    # 3. Retrieve task events
    events = client.tasks.events(task.task_id)
    print(f"Recorded events: {len(events)}")

if __name__ == "__main__":
    main()
