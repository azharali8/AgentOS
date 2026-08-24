"""
AgentOS Phase 9 — Python SDK Agents Client.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from agentos.models import AgentInvokeRequest, AgentInvokeResponse, AgentMetadata


class AgentsClient:
    """SDK client for interacting with AgentOS Specialized Agents."""

    def __init__(self, client: Any) -> None:
        self._client = client

    def list(self) -> List[AgentMetadata]:
        """List all registered specialized agents."""
        res = self._client._request("GET", "/api/v1/agents")
        return [
            AgentMetadata(
                agent_id=a.get("name", ""),
                name=a.get("name", ""),
                domain=a.get("agent_type", ""),
                description=a.get("description", ""),
                capabilities=[str(c) for c in a.get("capabilities", [])],
                allowed_tools=a.get("allowed_tools", []),
                risk_level=a.get("risk_level", "LOW"),
                max_concurrency=a.get("max_concurrency", 1),
                max_execution_time=a.get("max_execution_time", 300),
            )
            for a in res
        ]

    def get(self, agent_id: str) -> AgentMetadata:
        """Fetch metadata for a single specialized agent."""
        a = self._client._request("GET", f"/api/v1/agents/{agent_id}")
        return AgentMetadata(
            agent_id=a.get("name", ""),
            name=a.get("name", ""),
            domain=a.get("agent_type", ""),
            description=a.get("description", ""),
            capabilities=[str(c) for c in a.get("capabilities", [])],
            allowed_tools=a.get("allowed_tools", []),
            risk_level=a.get("risk_level", "LOW"),
            max_concurrency=a.get("max_concurrency", 1),
            max_execution_time=a.get("max_execution_time", 300),
        )

    def status(self, agent_id: str) -> Dict[str, Any]:
        """Check live availability and concurrency status of an agent."""
        return self._client._request("GET", f"/api/v1/agents/{agent_id}/status")

    def capabilities(self, agent_id: str) -> List[str]:
        """List explicit capabilities for an agent."""
        return self._client._request("GET", f"/api/v1/agents/{agent_id}/capabilities")

    def metrics(self, agent_id: str) -> Dict[str, Any]:
        """Fetch empirical performance metrics for an agent."""
        return self._client._request("GET", f"/api/v1/agents/{agent_id}/metrics")

    def invoke(
        self,
        agent_id: str,
        instruction: str,
        task_id: Optional[str] = None,
        target_files: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> AgentInvokeResponse:
        """
        Directly invoke a specialized agent under Supervisor boundaries.
        Cybersecurity agent requires ADMIN credentials.
        """
        payload = {
            "instruction": instruction,
            "task_id": task_id,
            "target_files": target_files or [],
            "context": context or {},
        }
        res = self._client._request("POST", f"/api/v1/agents/{agent_id}/invoke", json=payload)
        return AgentInvokeResponse(**res)
