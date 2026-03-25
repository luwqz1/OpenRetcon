# pyright: reportUnnecessaryIsInstance=false, reportUnreachable=false

from __future__ import annotations

import re
import typing

import msgspec

from retcon.openapi.v3 import oas300, oas310, oas320

type OAS3 = type[oas300.OpenAPI] | type[oas310.OpenAPI] | type[oas320.OpenAPI]
type OpenAPIDocument = OpenAPI3Object | str | bytes | bytearray | dict[str, typing.Any]

OpenAPI3Object = oas300.OpenAPI | oas310.OpenAPI | oas320.OpenAPI

_OPENAPI_VERSION_RE: typing.Final = re.compile(r"^\s*(\d+)\.(\d+)\.(\d+)(?:[-+][0-9A-Za-z.-]+)?\s*$")


class OpenAPIParseError(ValueError):
    """Raised when a raw OpenAPI document cannot be parsed."""


def parse_openapi_version(version: str) -> tuple[int, int, int]:
    matched = _OPENAPI_VERSION_RE.match(version)

    if not matched:
        raise OpenAPIParseError("/openapi: Invalid OpenAPI version format")

    major = int(matched.group(1))
    minor = int(matched.group(2))
    patch = int(matched.group(3))
    return (major, minor, patch)


def resolve_openapi_model(version: str) -> OAS3:
    major, minor, _ = parse_openapi_version(version)

    if major != 3:
        raise OpenAPIParseError(f"/openapi: Unsupported OpenAPI major version: {major}")

    if minor == 0:
        return oas300.OpenAPI

    if minor == 1:
        return oas310.OpenAPI

    return oas320.OpenAPI


def decode_openapi_document(
    document: OpenAPIDocument,
    document_type: typing.Literal["json", "yaml"],
) -> OpenAPI3Object:
    if isinstance(document, OpenAPI3Object):
        return document

    source: dict[str, typing.Any]

    if isinstance(document, dict):
        source = document
    elif isinstance(document, str | bytes | bytearray):
        source = _decode_raw_mapping(
            document if not isinstance(document, str) else document.encode("utf-8"),
            document_type,
        )
    else:
        raise OpenAPIParseError(f"Unsupported OpenAPI document type: {type(document).__name__}")

    version = source.get("openapi")

    if not isinstance(version, str):
        raise OpenAPIParseError("/openapi: Missing or invalid OpenAPI version string")

    model = resolve_openapi_model(version)

    try:
        return msgspec.convert(source, type=model)
    except msgspec.ValidationError as exc:
        raise OpenAPIParseError(str(exc)) from exc


def _decode_raw_mapping(
    payload: bytes | bytearray,
    document_type: typing.Literal["json", "yaml"],
    /,
) -> dict[str, typing.Any]:
    try:
        parsed = msgspec.json.decode(payload) if document_type == "json" else msgspec.yaml.decode(payload)
    except msgspec.DecodeError as exc:
        raise OpenAPIParseError(f"Failed to decode OpenAPI {document_type.upper()}: {exc}") from exc

    if not isinstance(parsed, dict):
        raise OpenAPIParseError("OpenAPI document root must be an object")

    return typing.cast("dict[str, typing.Any]", parsed)


__all__ = (
    "OpenAPIDocument",
    "OpenAPIParseError",
    "decode_openapi_document",
    "parse_openapi_version",
    "resolve_openapi_model",
)
