from backend.app.llm.base import BaseLLMProvider
from typing import List, Dict

class ColabProvider(BaseLLMProvider):
    def generate(self, prompt: str, **kwargs) -> str:
        return "Colab Provider Stub - Generate"
        
    def generate_chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        return "Colab Provider Stub - Chat"
