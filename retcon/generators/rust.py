import typing

from retcon.generators.abc import ABCGenerator
from retcon.schema.enums import Enum as SchemaEnum
from retcon.schema.graph import APISchema
from retcon.schema.objects import Field, Model
from retcon.schema.paths import Operation, Response
from retcon.schema.types import (
    AnyType,
    ArrayType,
    BooleanType,
    Constraints,
    EnumRef,
    IntegerType,
    MapType,
    ModelRef,
    NumberType,
    StringType,
    TypeRef,
    UnionType,
)


class RustGenerator(ABCGenerator):
    ...


__all__ = ("RustGenerator",)
