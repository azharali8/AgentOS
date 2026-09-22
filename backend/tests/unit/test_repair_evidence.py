import json
import pytest
from backend.app.llm.structured import GeneratedFiles, generate_structured, ModelOutputError
from backend.app.llm.proposal_validation import validate_python_proposal
from backend.app.llm.mock import MockLLMProvider
from backend.app.agents.debugger import DebuggerAgent
from backend.app.models.coding import InvestigationResult


ORIGINAL = "import pytest\nfrom main import app\n@pytest.fixture\ndef client():\n    return app.test_client()\ndef test_endpoint(client):\n    assert client.get('/').status_code == 200\n"


@pytest.mark.parametrize("content,reason", [
    ("def test_broken(:", "valid complete Python"),
    (ORIGINAL + "\n", "whitespace"),
    (ORIGINAL.replace("@pytest.fixture\n", ""), "fixture"),
    (ORIGINAL.replace("from main import app", "app = object()"), "workspace application"),
    (ORIGINAL.replace("assert client.get('/').status_code == 200", "assert True"), "assertions"),
])
def test_invalid_repairs_rejected_without_mutation(content, reason):
    proposal = GeneratedFiles(files=[{"path": "tests/test_main.py", "content": content}])
    with pytest.raises(ValueError, match=reason):
        validate_python_proposal(proposal, {"main.py": "app = None", "tests/test_main.py": ORIGINAL})


def test_fixture_setup_repair_preserves_coverage():
    content = ORIGINAL.replace("import pytest", "import pytest\nfrom fastapi.testclient import TestClient").replace("app.test_client()", "TestClient(app)")
    validate_python_proposal(GeneratedFiles(files=[{"path": "tests/test_main.py", "content": content}]),
                             {"main.py": "app = None", "tests/test_main.py": ORIGINAL})


def test_invalid_syntax_gets_bounded_model_feedback():
    calls = []
    class Model:
        def generate(self, prompt, **kwargs):
            calls.append(prompt)
            return json.dumps({"files": [{"path": "app.py", "content": "x = (" if len(calls) == 1 else "x = 1"}]})
    result = generate_structured(Model(), "Code", GeneratedFiles, validate=lambda p: validate_python_proposal(p, {}))
    assert result.files[0].content == "x = 1"
    assert len(calls) == 2 and "app.py:1" in calls[1]


def test_strict_diagnosis_publishes_observations_not_model_claims():
    model = MockLLMProvider(response_queue=[json.dumps({"root_cause": "API removed in version 99",
        "explanation": "Unsupported historical claim", "recommended_fix": "Use a supported client",
        "affected_files": ["../library.py"], "confidence": 1.0})])
    observed = "tests/test_main.py:5: AttributeError: missing test_client"
    result = DebuggerAgent(llm_provider=model, strict=True).diagnose([], InvestigationResult(
        affected_files=["tests/test_main.py"], evidence=observed))
    assert result.explanation == observed
    assert "version 99" not in result.root_cause + result.explanation
    assert result.recommended_fix.startswith("Unverified model repair proposal")
    assert result.affected_files == ["tests/test_main.py"]
    assert result.confidence == 0
