from backend.app.llm.base import BaseLLMProvider
from backend.app.config.settings import settings
from typing import List, Dict
import httpx

class OllamaProvider(BaseLLMProvider):
    def __init__(self):
        self.base_url = settings.OLLAMA_BASE_URL
        self.model = settings.OLLAMA_MODEL
        
    def generate(self, prompt: str, **kwargs) -> str:
        try:
            response = httpx.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False}
            )
            response.raise_for_status()
            return response.json().get("response", "")
        except httpx.RequestError as e:
            return f"Error connecting to Ollama: {str(e)}"
            
    def generate_chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        # Simplistic implementation for chat
        prompt = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
        return self.generate(prompt)
