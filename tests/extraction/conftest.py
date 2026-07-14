from __future__ import annotations

import json
from typing import Any

from app.config import ExtractionSettings
from app.services.extraction_service import ExtractionService


class _StubTextBlock:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _StubNonTextBlock:
    def __init__(self) -> None:
        self.type = "image"


class _StubResponse:
    def __init__(self, content: list[Any]) -> None:
        self.content = content


class RaiseError:
    """Script entry: the next create() call raises this exception."""

    def __init__(self, exc: BaseException) -> None:
        self.exc = exc


class MalformedShape:
    """Script entry: the next create() call returns a malformed response.

    kind="empty" -> response.content == []
    kind="non_text" -> response.content[0].type != "text"
    """

    def __init__(self, kind: str) -> None:
        self.kind = kind


class ScriptedAnthropicClient:
    """A contract-enforcing fake for AnthropicClientLike.

    Asserts the real API request shape on every call (max_tokens, thinking,
    output_config, model, alternating message roles) so a request-shape
    regression fails the suite even on the happy path — not just a canned
    echo of scripted responses.
    """

    def __init__(self, *scripted: dict[str, Any] | RaiseError | MalformedShape) -> None:
        self._queue: list[dict[str, Any] | RaiseError | MalformedShape] = list(scripted)
        self.calls: list[dict[str, Any]] = []
        self.messages = self

    async def create(self, **kwargs: Any) -> Any:  # noqa: ANN401 — mirrors the real SDK's dynamic call
        self.calls.append(kwargs)
        self._assert_contract(kwargs)

        item = self._queue.pop(0)
        if isinstance(item, RaiseError):
            raise item.exc
        if isinstance(item, MalformedShape):
            if item.kind == "empty":
                return _StubResponse([])
            return _StubResponse([_StubNonTextBlock()])
        return _StubResponse([_StubTextBlock(json.dumps(item, default=str))])

    def _assert_contract(self, kwargs: dict[str, Any]) -> None:
        assert isinstance(kwargs.get("max_tokens"), int)
        assert kwargs["max_tokens"] > 0
        assert kwargs.get("thinking") == {"type": "disabled"}

        output_config = kwargs.get("output_config")
        assert output_config is not None
        fmt = output_config.get("format", {})
        assert fmt.get("type") == "json_schema"
        assert fmt.get("schema")

        assert isinstance(kwargs.get("model"), str)
        assert kwargs["model"]

        messages = kwargs.get("messages")
        assert messages, "messages must be non-empty"
        assert messages[0]["role"] == "user"
        for prev, curr in zip(messages, messages[1:], strict=False):
            assert prev["role"] != curr["role"], "roles must strictly alternate"


def make_service(
    *scripted: dict[str, Any] | RaiseError | MalformedShape,
) -> tuple[ExtractionService, ScriptedAnthropicClient]:
    fake = ScriptedAnthropicClient(*scripted)
    settings = ExtractionSettings(extraction_model="test-model")
    return ExtractionService(fake, settings), fake
