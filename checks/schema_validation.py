"""Deterministic two-phase validation for the JSON Schema subset SpecRail uses."""

from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import unquote


ANNOTATION_KEYS = {"$id", "$schema", "description", "title"}
SUPPORTED_KEYS = ANNOTATION_KEYS | {
    "additionalProperties",
    "allOf",
    "anyOf",
    "const",
    "else",
    "enum",
    "exclusiveMaximum",
    "exclusiveMinimum",
    "if",
    "items",
    "minItems",
    "minLength",
    "minProperties",
    "minimum",
    "pattern",
    "properties",
    "required",
    "then",
    "type",
}
JSON_TYPES = {"array", "boolean", "integer", "null", "number", "object", "string"}


class SpecRailError(ValueError):
    """Base error for malformed SpecRail configuration or evidence."""


class SchemaDefinitionError(SpecRailError):
    """Raised when a schema definition is invalid or unsupported."""


class InstanceMismatch(SpecRailError):
    """Raised when a valid schema does not match an instance."""


def _resolve_pointer(document: Any, fragment: str, label: str) -> Any:
    if not fragment:
        return document
    decoded = unquote(fragment)
    if not decoded.startswith("/"):
        raise SchemaDefinitionError(
            f"{label}: local $ref fragment must be a JSON Pointer"
        )
    current = document
    for raw_token in decoded[1:].split("/"):
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and token in current:
            current = current[token]
            continue
        if isinstance(current, list) and token.isdigit():
            index = int(token)
            if index < len(current):
                current = current[index]
                continue
        raise SchemaDefinitionError(f"{label}: unresolved JSON Pointer token {token!r}")
    return current


def load_json_schema(path: Path) -> dict[str, Any]:
    """Load a schema and expand same-directory JSON references fail-closed."""

    entry = path.resolve()
    schema_root = entry.parent
    documents: dict[Path, dict[str, Any]] = {}

    def load_document(document_path: Path) -> dict[str, Any]:
        if document_path in documents:
            return documents[document_path]
        try:
            loaded = json.loads(document_path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise SchemaDefinitionError(
                f"{document_path}: cannot read referenced schema: {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise SchemaDefinitionError(
                f"{document_path}: referenced schema is invalid JSON: {exc.msg}"
            ) from exc
        if not isinstance(loaded, dict):
            raise SchemaDefinitionError(
                f"{document_path}: referenced schema must be an object"
            )
        documents[document_path] = loaded
        return loaded

    def expand(
        value: Any,
        document_path: Path,
        active: frozenset[tuple[Path, str]],
    ) -> Any:
        if isinstance(value, list):
            return [expand(item, document_path, active) for item in value]
        if not isinstance(value, dict):
            return value
        if "$ref" not in value:
            return {
                key: expand(child, document_path, active)
                for key, child in value.items()
            }
        if set(value) != {"$ref"} or not isinstance(value["$ref"], str):
            raise SchemaDefinitionError(
                f"{document_path}: $ref must be the only key and a string"
            )
        reference = value["$ref"]
        file_part, _, fragment = reference.partition("#")
        if (
            "://" in file_part
            or file_part.startswith(("/", "\\"))
            or "\\" in file_part
        ):
            raise SchemaDefinitionError(
                f"{document_path}: only repo-local relative $ref values are supported"
            )
        target_path = (
            document_path if not file_part else (document_path.parent / file_part).resolve()
        )
        try:
            target_path.relative_to(schema_root)
        except ValueError as exc:
            raise SchemaDefinitionError(
                f"{document_path}: $ref escapes the schema directory"
            ) from exc
        reference_key = (target_path, fragment)
        if reference_key in active:
            raise SchemaDefinitionError(
                f"{document_path}: circular $ref {reference!r}"
            )
        target = _resolve_pointer(
            load_document(target_path),
            fragment,
            f"{document_path} $ref {reference!r}",
        )
        return expand(target, target_path, active | {reference_key})

    expanded = expand(load_document(entry), entry, frozenset({(entry, "")}))
    if not isinstance(expanded, dict):
        raise SchemaDefinitionError(f"{entry}: expanded schema must be an object")
    return copy.deepcopy(expanded)


def _schema_path(path: str, key: str) -> str:
    return f"{path}.{key}"


def _definition_error(path: str, message: str) -> None:
    raise SchemaDefinitionError(f"{path}: {message}")


def _validate_schema_definition(schema: Any, path: str) -> None:
    if not isinstance(schema, dict):
        _definition_error(path, "schema must be an object")
    unsupported = sorted(set(schema) - SUPPORTED_KEYS)
    if unsupported:
        _definition_error(
            path, f"unsupported JSON Schema keyword {unsupported[0]!r}"
        )

    for key in ANNOTATION_KEYS:
        if key in schema and not isinstance(schema[key], str):
            _definition_error(_schema_path(path, key), "annotation must be a string")

    if "type" in schema:
        raw_types = schema["type"]
        types = raw_types if isinstance(raw_types, list) else [raw_types]
        if not types or not all(isinstance(item, str) for item in types):
            _definition_error(
                _schema_path(path, "type"),
                "must be a string or list of strings",
            )
        unknown_types = sorted(set(types) - JSON_TYPES)
        if unknown_types:
            _definition_error(
                _schema_path(path, "type"), f"unsupported type {unknown_types[0]!r}"
            )

    if "enum" in schema and (
        not isinstance(schema["enum"], list) or not schema["enum"]
    ):
        _definition_error(_schema_path(path, "enum"), "must be a non-empty list")

    for key in ["minItems", "minLength", "minProperties"]:
        value = schema.get(key)
        if key in schema and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0
        ):
            _definition_error(path, f"{key} must be a non-negative integer")

    for key in ["minimum", "exclusiveMinimum", "exclusiveMaximum"]:
        value = schema.get(key)
        if key in schema and (
            isinstance(value, bool) or not isinstance(value, (int, float))
        ):
            _definition_error(_schema_path(path, key), "must be a number")

    if "pattern" in schema:
        pattern = schema["pattern"]
        if not isinstance(pattern, str):
            _definition_error(_schema_path(path, "pattern"), "must be a string")
        try:
            re.compile(pattern)
        except re.error as exc:
            _definition_error(_schema_path(path, "pattern"), f"invalid pattern: {exc}")

    if "required" in schema:
        required = schema["required"]
        if not isinstance(required, list) or not all(
            isinstance(item, str) for item in required
        ):
            _definition_error(
                _schema_path(path, "required"), "must be a list of strings"
            )
        if len(set(required)) != len(required):
            _definition_error(
                _schema_path(path, "required"), "must not contain duplicates"
            )

    if "properties" in schema:
        properties = schema["properties"]
        if not isinstance(properties, dict):
            _definition_error(_schema_path(path, "properties"), "must be an object")
        for key, child in properties.items():
            if not isinstance(key, str):
                _definition_error(
                    _schema_path(path, "properties"), "keys must be strings"
                )
            _validate_schema_definition(
                child, _schema_path(_schema_path(path, "properties"), key)
            )

    if "additionalProperties" in schema:
        additional = schema["additionalProperties"]
        if not isinstance(additional, (bool, dict)):
            _definition_error(
                _schema_path(path, "additionalProperties"),
                "must be boolean or an object",
            )
        if isinstance(additional, dict):
            _validate_schema_definition(
                additional, _schema_path(path, "additionalProperties")
            )

    if "items" in schema:
        _validate_schema_definition(schema["items"], _schema_path(path, "items"))

    for key in ["allOf", "anyOf"]:
        if key not in schema:
            continue
        children = schema[key]
        if not isinstance(children, list) or not children:
            _definition_error(_schema_path(path, key), "must be a non-empty list")
        for index, child in enumerate(children):
            _validate_schema_definition(
                child, f"{_schema_path(path, key)}[{index}]"
            )

    for key in ["if", "then", "else"]:
        if key in schema:
            _validate_schema_definition(schema[key], _schema_path(path, key))


def _json_type_matches(data: Any, expected_type: str) -> bool:
    if expected_type == "object":
        return isinstance(data, dict)
    if expected_type == "array":
        return isinstance(data, list)
    if expected_type == "string":
        return isinstance(data, str)
    if expected_type == "integer":
        return isinstance(data, int) and not isinstance(data, bool)
    if expected_type == "number":
        return isinstance(data, (int, float)) and not isinstance(data, bool)
    if expected_type == "boolean":
        return isinstance(data, bool)
    return data is None


def _instance_path(path: str, key: str) -> str:
    return f"{path}.{key}" if path else key


def _mismatch(path: str, message: str) -> None:
    raise InstanceMismatch(f"{path}: {message}")


def _evaluate(schema: dict[str, Any], data: Any, path: str) -> None:
    if "type" in schema:
        raw_types = schema["type"]
        types = raw_types if isinstance(raw_types, list) else [raw_types]
        if not any(_json_type_matches(data, item) for item in types):
            _mismatch(path, f"expected type {', '.join(types)}")
    if "const" in schema and data != schema["const"]:
        _mismatch(path, f"expected const {schema['const']!r}")
    if "enum" in schema and data not in schema["enum"]:
        _mismatch(path, f"value {data!r} is not in enum")

    for key, expected_type, type_message, threshold_message in [
        (
            "minLength",
            str,
            "minLength requires a string instance",
            "string is shorter than minLength",
        ),
        (
            "minItems",
            list,
            "minItems requires an array instance",
            "array is shorter than minItems",
        ),
        (
            "minProperties",
            dict,
            "minProperties requires an object instance",
            "object has fewer properties than minProperties",
        ),
    ]:
        if key not in schema:
            continue
        if not isinstance(data, expected_type):
            _mismatch(path, type_message)
        if len(data) < schema[key]:
            _mismatch(path, threshold_message)

    if "pattern" in schema:
        if not isinstance(data, str):
            _mismatch(path, "pattern requires a string instance")
        if re.search(schema["pattern"], data) is None:
            _mismatch(path, "string does not match pattern")

    for key, operator, message in [
        ("minimum", lambda value, limit: value < limit, "value is below minimum"),
        (
            "exclusiveMinimum",
            lambda value, limit: value <= limit,
            "value is not above exclusiveMinimum",
        ),
        (
            "exclusiveMaximum",
            lambda value, limit: value >= limit,
            "value is not below exclusiveMaximum",
        ),
    ]:
        if key not in schema:
            continue
        if not _json_type_matches(data, "number"):
            _mismatch(path, f"{key} requires a number instance")
        if operator(data, schema[key]):
            _mismatch(path, message)

    if "required" in schema:
        if not isinstance(data, dict):
            _mismatch(path, "required fields need an object instance")
        for key in schema["required"]:
            if key not in data:
                _mismatch(_instance_path(path, key), "missing required field")

    properties = schema.get("properties", {})
    if isinstance(data, dict):
        for key, child in properties.items():
            if key in data:
                _evaluate(child, data[key], _instance_path(path, key))
        additional = schema.get("additionalProperties", True)
        extra_keys = sorted(set(data) - set(properties))
        if additional is False and extra_keys:
            _mismatch(
                _instance_path(path, extra_keys[0]),
                "additional property is not allowed",
            )
        if isinstance(additional, dict):
            for key in extra_keys:
                _evaluate(additional, data[key], _instance_path(path, key))

    if "items" in schema:
        if not isinstance(data, list):
            _mismatch(path, "items requires an array instance")
        for index, item in enumerate(data):
            _evaluate(schema["items"], item, f"{path}[{index}]")

    for child in schema.get("allOf", []):
        _evaluate(child, data, path)
    if "anyOf" in schema:
        for child in schema["anyOf"]:
            try:
                _evaluate(child, data, path)
            except InstanceMismatch:
                continue
            break
        else:
            _mismatch(path, "instance does not match anyOf")
    if "if" in schema:
        try:
            _evaluate(schema["if"], data, path)
        except InstanceMismatch:
            branch = schema.get("else")
        else:
            branch = schema.get("then")
        if branch is not None:
            _evaluate(branch, data, path)


def validate_instance(schema: dict[str, Any], data: Any, path: str = "$") -> None:
    """Validate a schema definition completely, then evaluate one instance."""

    _validate_schema_definition(schema, "$schema")
    _evaluate(schema, data, path)
