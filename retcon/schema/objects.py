from __future__ import annotations

import typing

import msgspec

from retcon.schema.nodes import Node
from retcon.schema.types import TypeRef


class Field(Node, kw_only=True):
    """A single field within a :class:`Model`."""

    name: str
    type: TypeRef
    required: bool = True
    description: str | None = None
    default: typing.Any = msgspec.UNSET


class Model(Node, kw_only=True):
    """A named data model composed of :class:`Field` instances.

    Corresponds to an ``object``-typed Schema in OpenAPI.
    """

    name: str
    fields: list[Field] = []
    description: str | None = None


__all__ = ("Field", "Model")
