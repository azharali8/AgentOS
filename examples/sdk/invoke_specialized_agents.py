"""
AgentOS SDK Example: Invoke Specialized Agents.
"""

from agentos import AgentOS

def main():
    client = AgentOS(base_url="http://localhost:8000")

    # 1. List registered agents
    agents = client.agents.list()
    print(f"Available agents ({len(agents)}):")
    for a in agents:
        print(f" - {a.name} ({a.domain}): {len(a.capabilities)} capabilities")

    # 2. Invoke Data Engineer Agent
    de_res = client.agents.invoke(
        agent_id="data_engineer",
        instruction="Profile sample dataset for anomalies and missing values",
    )
    print(f"\nData Engineer Result: {de_res.status} | {de_res.summary}")

    # 3. Invoke DevOps Agent
    devops_res = client.agents.invoke(
        agent_id="devops",
        instruction="Generate multi-stage Dockerfile for FastAPI runtime",
    )
    print(f"DevOps Result: {devops_res.status} | {devops_res.summary}")

if __name__ == "__main__":
    main()
