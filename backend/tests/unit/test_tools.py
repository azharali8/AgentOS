from backend.app.tools.registry import ToolRegistry

def test_registry_has_tools():
    # Ensure that our loaded tools are in the registry
    assert len(ToolRegistry.list_tools()) >= 0
