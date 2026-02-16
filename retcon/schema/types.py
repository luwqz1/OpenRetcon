from __future__ import annotations

from retcon.schema.nodes import Node


class TypeRef(Node, kw_only=True):
    """Base class for all type references.

    ``nullable`` indicates that the value may also be ``None`` / ``null``.
    """

    nullable: bool = False


class StringType(TypeRef, kw_only=True):
    """A string value, optionally qualified by *format* (e.g. ``date-time``, ``uuid``)."""

    format: str | None = None


class IntegerType(TypeRef, kw_only=True):
    """An integer value, optionally qualified by *format* (e.g. ``int32``, ``int64``)."""

    format: str | None = None


class NumberType(TypeRef, kw_only=True):
    """A floating-point number, optionally qualified by *format* (e.g. ``float``, ``double``)."""

    format: str | None = None


class BooleanType(TypeRef, kw_only=True):
    """A boolean value."""


class ArrayType(TypeRef, kw_only=True):
    """An ordered list of items sharing the same *item_type*."""

    item_type: TypeRef


class MapType(TypeRef, kw_only=True):
    """A string-keyed mapping where every value has *value_type*."""

    value_type: TypeRef


class UnionType(TypeRef, kw_only=True):
    """A discriminated or undiscriminated union of several type *variants*."""

    variants: list[TypeRef]


class ModelRef(TypeRef, kw_only=True):
    """A reference to a :class:`~retcon.schema.objects.Model` by *name*."""

    name: str


class EnumRef(TypeRef, kw_only=True):
    """A reference to a :class:`~retcon.schema.enums.Enum` by *name*."""

    name: str


class AnyType(TypeRef, kw_only=True):
    """An unconstrained value (``typing.Any``)."""


__all__ = (
    "TypeRef",
    "StringType",
    "IntegerType",
    "NumberType",
    "BooleanType",
    "ArrayType",
    "MapType",
    "UnionType",
    "ModelRef",
    "EnumRef",
    "AnyType",
)
