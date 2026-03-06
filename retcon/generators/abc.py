from __future__ import annotations

from abc import ABC, abstractmethod

from retcon.schema.enums import Enum
from retcon.schema.graph import APISchema
from retcon.schema.nodes import Node
from retcon.schema.objects import Model
from retcon.schema.paths import Operation
from retcon.schema.types import TypeRef


class ABCGenerator(ABC):
    @abstractmethod
    def generate(self, schema: APISchema) -> dict[str, str]:
        """Generate all files for *schema*.

        Implementations may also use ``schema.custom_nodes`` for user-defined
        nodes added during the pipeline.

        Returns a mapping ``{filename: content}``.
        """

    @abstractmethod
    def generate_model(self, model: Model) -> str:
        """Emit code for a single data *model*."""

    @abstractmethod
    def generate_enum(self, enum: Enum) -> str:
        """Emit code for a single *enum* type."""

    @abstractmethod
    def generate_operation(self, operation: Operation) -> str:
        """Emit code for a single API *operation*."""

    @abstractmethod
    def type_to_string(self, type_ref: TypeRef) -> str:
        """Convert :class:`TypeRef` to a type string in the target language."""

    def generate_custom_node(self, node: Node) -> str | None:
        """Optional hook for language-specific custom node generation."""
        return None


__all__ = ("ABCGenerator",)
