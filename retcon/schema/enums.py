from __future__ import annotations

from retcon.schema.nodes import Node


class EnumValue(Node, kw_only=True):
    """A single member of an :class:`Enum`."""

    name: str
    value: str | int | float


class Enum(Node, kw_only=True):
    """A named enumeration of allowed values.

    Corresponds to a Schema with the ``enum`` keyword in OpenAPI.
    """

    name: str
    values: list[EnumValue]
    description: str | None = None


__all__ = ("Enum", "EnumValue")
