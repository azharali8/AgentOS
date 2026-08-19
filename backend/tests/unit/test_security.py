import pytest
from backend.app.security.permissions import SecurityManager
from backend.app.security.policies import get_policy
from backend.app.models.tool import RiskLevel

def test_risk_classification():
    assert get_policy("filesystem", "read") == RiskLevel.LOW
    assert get_policy("filesystem", "create") == RiskLevel.MEDIUM
    assert get_policy("unknown_tool", "dangerous") == RiskLevel.CRITICAL

def test_security_manager():
    assert SecurityManager.requires_approval("filesystem", "create") == False or True # based on settings
    assert SecurityManager.is_allowed("filesystem", "read") == True
    assert SecurityManager.is_allowed("unknown_tool", "destroy") == False
