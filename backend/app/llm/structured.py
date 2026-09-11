"""Validated structured generation shared by providers; retries never invent results."""
import json
import logging
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from backend.app.config.settings import settings
from backend.app.llm.base import BaseLLMProvider

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)


def generate_structured(provider: BaseLLMProvider, prompt: str, schema: type[T]) -> T:
    schema_json = schema.model_json_schema()
    request = prompt + "\nRESPONSE_SCHEMA:\n" + json.dumps(schema_json)
    for attempt in range(max(1, min(settings.LLM_STRUCTURED_ATTEMPTS, 3))):
        # Transport/model errors are not malformed-output retries.
        raw = provider.generate(request, format=schema_json).strip()
        if raw.startswith("```") and raw.endswith("```"):
            raw = "\n".join(raw.splitlines()[1:-1]).strip()
        try:
            return schema.model_validate_json(raw)
        except ValidationError as exc:
            logger.warning("Invalid %s output, attempt %s: %s", schema.__name__, attempt + 1,
                           [e["type"] for e in exc.errors()])
            # Regenerate against the original request; never execute/repair partial code.
            request = prompt + "\nThe previous response was invalid. Return a complete JSON object matching RESPONSE_SCHEMA.\nRESPONSE_SCHEMA:\n" + json.dumps(schema_json)
    raise ValueError(f"Model returned invalid {schema.__name__} after bounded retries")


class GeneratedFile(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    path: str = Field(min_length=1)
    content: str = Field(min_length=1)


class GeneratedFiles(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    files: list[GeneratedFile] = Field(min_length=1, max_length=10)
