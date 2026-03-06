from __future__ import annotations

import msgspec

from retcon.schema.nodes import Node


class Constraints(Node, kw_only=True):
    """Validation constraints that map to ``msgspec.Meta`` arguments.

    Numeric bounds follow ``msgspec.Meta`` semantics:
    ``gt``/``ge`` for exclusive/inclusive lower bounds,
    ``lt``/``le`` for exclusive/inclusive upper bounds.
    """

    gt: float | None = None
    ge: float | None = None
    lt: float | None = None
    le: float | None = None
    multiple_of: float | None = None
    pattern: str | None = None
    min_length: int | None = None
    max_length: int | None = None

    def is_empty(self) -> bool:
        return all(
            getattr(self, f.name) is None
            for f in msgspec.structs.fields(self)
        )


class TypeRef(Node, kw_only=True):
    """Base class for all type references.

    ``nullable`` indicates that the value may also be ``None`` / ``null``.
    ``constraints`` carries optional validation constraints; when present the
    generator wraps the type in ``Annotated[T, msgspec.Meta(...)]``.
    """

    nullable: bool = False
    constraints: Constraints | None = None


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
    "Constraints",
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
