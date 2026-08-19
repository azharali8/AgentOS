import os
from pathlib import Path
from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parents[3]

class Settings(BaseSettings):
    APP_ENV: str = "development"
    LLM_PROVIDER: str = "ollama"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3"
    WORKSPACE_ROOT: str = str(PROJECT_ROOT / "workspace")
    REQUIRE_APPROVAL_FOR_DANGEROUS_ACTIONS: bool = True
    MAX_RETRIES: int = 3
    TERMINAL_TIMEOUT: int = 30
    MAX_OUTPUT_SIZE: int = 1024 * 1024  # 1 MB

    # Phase 2 Database & Limits
    DATABASE_URL: str = "sqlite:///./data/agentos.db"
    MAX_TASK_DURATION: int = 3600  # Default 1 hour

    # Phase 1 agent execution limits — controlled by server config, never by LLM
    MAX_PLAN_STEPS: int = 20
    MAX_REPLANS: int = 3
    MAX_RETRIES_PER_STEP: int = 3
    MAX_TOOL_CALLS: int = 30

    # Phase 3 repository intelligence & code tool limits
    MAX_REPOSITORY_FILES: int = 1000
    MAX_FILE_SIZE: int = 1024 * 1024          # 1 MB per file
    MAX_TOTAL_SCAN_SIZE: int = 50 * 1024 * 1024  # 50 MB cumulative scan
    MAX_SEARCH_RESULTS: int = 100
    MAX_SEARCH_FILE_SIZE: int = 512 * 1024   # 512 KB per searched file
    MAX_LINES_PER_READ: int = 200

    # Phase 3 patch limits
    MAX_PATCH_FILES: int = 10
    MAX_PATCH_LINES: int = 500

    # Phase 3 test runner limits
    MAX_TEST_RUNTIME: int = 60               # seconds
    MAX_DEBUG_ATTEMPTS: int = 3

    # Phase 5 multi-agent collaboration limits
    MAX_SUBTASKS: int = 20
    MAX_AGENT_DEPTH: int = 5
    MAX_AGENT_HANDOFFS: int = 20
    MAX_AGENT_TOKENS: int = 100000
    MAX_AGENT_TOOL_CALLS: int = 50
    MAX_AGENT_RUNTIME: int = 300
    MAX_AGENT_RETRIES: int = 3
    MAX_AGENT_CONCURRENCY: int = 4
    MAX_MEMORY_ITEMS: int = 1000

    # Phase 8 continuous learning & long-term intelligence limits
    MAX_LEARNING_EXPERIENCES: int = 1000
    MAX_LEARNING_RETRIEVAL_TOP_K: int = 5
    MAX_LEARNING_RECOMMENDATIONS: int = 10
    LEARNING_RETENTION_DAYS: int = 90
    LEARNING_LOOP_LIMIT: int = 3

    # Phase 6 production platform & observability settings
    LOG_LEVEL: str = "INFO"
    RATE_LIMIT_REQUESTS: int = 100
    RATE_LIMIT_WINDOW: int = 60  # seconds
    ENABLE_METRICS: bool = True
    ENABLE_TRACING: bool = True
    ENABLE_AUDIT_LOGGING: bool = True
    GLOBAL_DAILY_TOKEN_LIMIT: int = 1000000
    TASK_TOKEN_LIMIT: int = 100000
    AGENT_TOKEN_LIMIT: int = 50000
    AUTH_ENABLED: bool = False  # Safe dev/test default; enabled in production
    API_KEY_SALT: str = "agentos-default-salt-change-in-prod"
    JWT_SECRET: str = "agentos-default-jwt-secret-change-in-prod"
    JWT_EXPIRATION: int = 3600  # seconds
    MAX_REQUEST_BODY_SIZE: int = 2 * 1024 * 1024  # 2 MB
    MAX_JSON_DEPTH: int = 10

    class Config:
        env_file = ".env"

settings = Settings()
