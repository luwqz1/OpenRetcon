from __future__ import annotations

import msgspec

from retcon.schema.nodes import Node
from retcon.schema.types import TypeRef


class Parameter(Node, kw_only=True):
    """A single operation parameter (query, path, header, or cookie)."""

    name: str
    location: str
    type: TypeRef
    required: bool = False
    description: str | None = None


class RequestBody(Node, kw_only=True):
    """Describes the body of an HTTP request."""

    content_type: str
    type: TypeRef
    required: bool = False
    description: str | None = None


class Response(Node, kw_only=True):
    """Describes a single HTTP response."""

    status_code: str
    description: str | None = None
    content: dict[str, TypeRef] = msgspec.field(default_factory=dict)


class Operation(Node, kw_only=True):
    """A single HTTP operation (method + path combination)."""

    method: str
    path: str
    operation_id: str | None = None
    summary: str | None = None
    description: str | None = None
    tags: list[str] = msgspec.field(default_factory=list)
    parameters: list[Parameter] = msgspec.field(default_factory=list)
    request_body: RequestBody | None = None
    responses: list[Response] = msgspec.field(default_factory=list)
    deprecated: bool = False


class Endpoint(Node, kw_only=True):
    """A URL path that groups one or more :class:`Operation` instances."""

    path: str
    operations: list[Operation] = msgspec.field(default_factory=list)
    description: str | None = None


__all__ = ("Endpoint", "Operation", "Parameter", "RequestBody", "Response")
