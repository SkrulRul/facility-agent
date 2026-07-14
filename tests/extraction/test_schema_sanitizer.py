from __future__ import annotations

import json

from app.extraction_targets.term_sheet import TermSheetExtract
from app.services.extraction_service import (
    _UNSUPPORTED_SCHEMA_KEYWORDS,  # pyright: ignore[reportPrivateUsage]
    JSONSchemaValue,
    _schema_for,  # pyright: ignore[reportPrivateUsage]
)


def _walk(node: JSONSchemaValue) -> list[JSONSchemaValue]:
    """Flatten every dict/list node in a JSON-schema-shaped structure."""
    nodes: list[JSONSchemaValue] = [node]
    if isinstance(node, dict):
        for value in node.values():
            nodes.extend(_walk(value))
    elif isinstance(node, list):
        for item in node:
            nodes.extend(_walk(item))
    return nodes


def test_sanitized_schema_has_no_unsupported_keywords() -> None:
    schema = _schema_for(TermSheetExtract)

    serialized = json.dumps(schema)
    for keyword in _UNSUPPORTED_SCHEMA_KEYWORDS:
        assert f'"{keyword}"' not in serialized, f"unsupported keyword {keyword} leaked into schema"


def test_sanitized_schema_sets_additional_properties_false_on_every_object() -> None:
    schema = _schema_for(TermSheetExtract)

    for node in _walk(schema):
        if isinstance(node, dict) and node.get("type") == "object":
            assert node.get("additionalProperties") is False


def test_sanitized_schema_preserves_enum_and_format() -> None:
    schema = _schema_for(TermSheetExtract)

    serialized = json.dumps(schema)
    assert '"format"' in serialized  # date field retains format: date
    assert '"enum"' in serialized or '"const"' in serialized  # Literal fields
