from backend.app.config.settings import settings
from backend.app.llm.base import BaseLLMProvider

def get_llm_provider() -> BaseLLMProvider:
    provider_name = settings.LLM_PROVIDER.lower()
    if provider_name == "ollama":
        from backend.app.llm.ollama import OllamaProvider
        return OllamaProvider()
    elif provider_name == "openai":
        from backend.app.llm.openai_compatible import OpenAICompatibleProvider
        return OpenAICompatibleProvider()
    elif provider_name == "colab":
        from backend.app.llm.colab import ColabProvider
        return ColabProvider()
    elif provider_name == "mock":
        from backend.app.llm.mock import MockLLMProvider
        return MockLLMProvider()
    else:
        raise ValueError(f"Unknown LLM provider: {provider_name}")

