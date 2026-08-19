from backend.app.llm.base import BaseLLMProvider
from typing import List, Dict

class OpenAICompatibleProvider(BaseLLMProvider):
    def generate(self, prompt: str, **kwargs) -> str:
        return "OpenAI Provider Stub - Generate"
        
    def generate_chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        return "OpenAI Provider Stub - Chat"
