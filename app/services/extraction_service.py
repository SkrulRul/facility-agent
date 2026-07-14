from __future__ import annotations

import json
from typing import Any, Protocol, TypeVar, cast

import anthropic
from anthropic import AsyncAnthropic
from pydantic import BaseModel, ValidationError

from app.config import ExtractionSettings

ModelT = TypeVar("ModelT", bound=BaseModel)

_MAX_TOKENS = 4096

_UNSUPPORTED_SCHEMA_KEYWORDS = (
    "pattern",
    "minLength",
    "maxLength",
    "minimum",
    "maximum",
    "multipleOf",
    "exclusiveMinimum",
    "exclusiveMaximum",
)


class ExtractionError(Exception):
    """Raised after max_attempts total create() calls fail validation.

    Carries the last ValidationError as __cause__.
    """


class ExtractionTransportError(Exception):
    """Raised when the Anthropic SDK's own transport retries are exhausted.

    Wraps anthropic.APIError and its subclasses. Never counted against
    max_attempts — this is a distinct failure category from validation
    retries, per the tech-lead review addendum.
    """


class ExtractionResponseShapeError(Exception):
    """Raised when a successful API response's content is empty or its

    first block is not a text block. Not a validation failure (nothing to
    validate yet) and not a transport failure (the SDK call succeeded) — a
    distinct response-contract anomaly. Not retried, not counted against
    max_attempts: there is no ValidationError to feed a correction prompt.
    """


class AnthropicMessagesLike(Protocol):
    async def create(self, **kwargs: Any) -> Any: ...  # noqa: ANN401 — mirrors the real SDK's dynamic call


class AnthropicClientLike(Protocol):
    @property
    def messages(self) -> AnthropicMessagesLike: ...


JSONSchemaValue = dict[str, Any] | list[Any] | str | int | float | bool | None


def _sanitize_schema(schema: dict[str, Any]) -> dict[str, Any]:
    """Recursively strip JSON Schema keywords unsupported by structured outputs

    and set additionalProperties: false on every object node.
    """
    sanitized: dict[str, Any] = {}
    for key, value in schema.items():
        if key in _UNSUPPORTED_SCHEMA_KEYWORDS:
            continue
        sanitized[key] = _sanitize_value(value)

    if sanitized.get("type") == "object":
        sanitized["additionalProperties"] = False

    return sanitized


def _sanitize_value(value: JSONSchemaValue) -> JSONSchemaValue:
    if isinstance(value, dict):
        return _sanitize_schema(value)
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return value


def _schema_for(target_model: type[BaseModel]) -> dict[str, Any]:
    return _sanitize_schema(target_model.model_json_schema())


def _filter_errors(exc: ValidationError) -> str:
    filtered = [
        {"loc": err["loc"], "msg": err["msg"], "input": err.get("input")}
        for err in exc.errors()
    ]
    return json.dumps(filtered, default=str)


class ExtractionService:
    def __init__(self, client: AnthropicClientLike, settings: ExtractionSettings) -> None:
        self._client = client
        self._settings = settings

    async def extract(
        self,
        text: str,
        target_model: type[ModelT],
        *,
        max_attempts: int = 3,
    ) -> ModelT:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")

        schema = _schema_for(target_model)
        messages: list[dict[str, Any]] = [
            {
                "role": "user",
                "content": (
                    "Extract structured data from the following document. "
                    f"Return JSON matching the schema.\n\n{text}"
                ),
            }
        ]

        last_error: ValidationError | None = None
        for _attempt in range(1, max_attempts + 1):
            try:
                response = await self._client.messages.create(
                    model=self._settings.extraction_model,
                    max_tokens=_MAX_TOKENS,
                    thinking={"type": "disabled"},
                    output_config={"format": {"type": "json_schema", "schema": schema}},
                    messages=messages,
                )
            except anthropic.APIError as exc:
                raise ExtractionTransportError(str(exc)) from exc

            content = getattr(response, "content", None)
            if not content or getattr(content[0], "type", None) != "text":
                raise ExtractionResponseShapeError(
                    "Anthropic response.content was empty or its first block "
                    "was not a text block"
                )
            raw_text = content[0].text

            try:
                return target_model.model_validate_json(raw_text)
            except ValidationError as exc:
                last_error = exc
                messages = [
                    *messages,
                    {"role": "assistant", "content": raw_text},
                    {
                        "role": "user",
                        "content": (
                            "That output failed validation:\n"
                            f"{_filter_errors(exc)}\n"
                            "Return corrected JSON matching the schema."
                        ),
                    },
                ]

        raise ExtractionError(
            f"Extraction failed validation after {max_attempts} attempts"
        ) from last_error


def build_extraction_service(settings: ExtractionSettings) -> ExtractionService:
    raw = AsyncAnthropic(
        api_key=settings.anthropic_api_key.get_secret_value(),
        max_retries=settings.transport_max_retries,
    )
    # AsyncAnthropic.messages.create's typed signature won't satisfy the
    # **kwargs Protocol under strict checkers, though it's structurally
    # compatible at runtime.
    client = cast(AnthropicClientLike, raw)
    return ExtractionService(client, settings)
