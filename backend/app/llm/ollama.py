"""Local Ollama adapter with explicit failures and bounded CPU inference."""
import threading
from typing import List, Dict

import httpx

from backend.app.config.settings import settings
from backend.app.llm.base import BaseLLMProvider

_inference_slot = threading.BoundedSemaphore(1)


class OllamaProvider(BaseLLMProvider):
    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL.rstrip("/")
        self.model = settings.OLLAMA_MODEL

    def generate(self, prompt: str, **kwargs) -> str:
        timeout = max(1, min(settings.LLM_TIMEOUT_SECONDS, 900))
        if not _inference_slot.acquire(timeout=timeout):
            raise RuntimeError("Configured Ollama inference queue timed out; another request is still running")
        try:
            payload = {"model": self.model, "prompt": prompt, "stream": False,
                       "keep_alive": "10m", "options": {
                           "temperature": 0, "num_ctx": settings.OLLAMA_NUM_CTX,
                           "num_predict": settings.OLLAMA_NUM_PREDICT}}
            if settings.OLLAMA_REASONING_EFFORT:
                payload["think"] = settings.OLLAMA_REASONING_EFFORT
            # Ollama Cloud currently rejects server-side structured output.
            # The shared helper still validates and retries against the schema.
            if "format" in kwargs and not self.model.endswith((":cloud", "-cloud")):
                payload["format"] = kwargs["format"]
            for attempt in range(2):
                try:
                    response = httpx.post(f"{self.base_url}/api/generate", json=payload, timeout=timeout)
                    response.raise_for_status()
                    data = response.json()
                    if data.get("done_reason") == "length":
                        raise RuntimeError("Configured Ollama output reached its token limit; narrow the coding task")
                    output = data.get("response")
                    if data.get("error") or data.get("done") is False or not isinstance(output, str) or not output.strip():
                        raise RuntimeError("Configured Ollama returned an empty or incomplete response")
                    return output
                except httpx.ConnectError as exc:
                    if attempt == 0:
                        continue
                    raise RuntimeError(f"Could not reach the configured Ollama service at {self.base_url}; start ollama serve") from exc
                except httpx.TimeoutException as exc:
                    raise RuntimeError(f"Configured Ollama model {self.model} timed out after {timeout}s") from exc
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code == 404:
                        raise RuntimeError(f"Configured Ollama model '{self.model}' is unavailable; use ollama list and set OLLAMA_MODEL to an installed model") from exc
                    raise RuntimeError(f"Configured Ollama request failed (HTTP {exc.response.status_code})") from exc
                except httpx.RequestError as exc:
                    raise RuntimeError("Could not reach the configured Ollama model") from exc
        finally:
            _inference_slot.release()

    def generate_chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        return self.generate("\n".join(f"{m['role']}: {m['content']}" for m in messages), **kwargs)
