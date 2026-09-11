import httpx
import pytest
from backend.app.llm.ollama import OllamaProvider


def test_structured_generation_is_requested_from_ollama(monkeypatch):
    seen = {}
    def post(url, **kwargs):
        seen.update(kwargs)
        return httpx.Response(200, request=httpx.Request("POST", url), json={"response": '{"files": []}'})
    monkeypatch.setattr(httpx, "post", post)
    assert OllamaProvider().generate("Return JSON", format="json") == '{"files": []}'
    assert seen["json"]["format"] == "json"
    assert seen["json"]["options"]["temperature"] == 0
    assert seen["timeout"] > 5


def test_model_network_failure_is_an_error_not_generated_content(monkeypatch):
    def post(*args, **kwargs):
        raise httpx.ConnectError("offline")
    monkeypatch.setattr(httpx, "post", post)
    with pytest.raises(RuntimeError, match="configured Ollama"):
        OllamaProvider().generate("Implement a task")
