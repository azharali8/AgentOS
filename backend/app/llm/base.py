from abc import ABC, abstractmethod
from typing import List, Dict, Any

class BaseLLMProvider(ABC):
    def check_available(self) -> None:
        """Optional provider preflight. Never substitutes generated output."""

    @abstractmethod
    def generate(self, prompt: str, **kwargs) -> str:
        pass
        
    @abstractmethod
    def generate_chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        pass
