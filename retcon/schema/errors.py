from __future__ import annotations


class SchemaError(Exception):
    """Base exception for all schema-related errors."""


class ConversionError(SchemaError):
    """Raised when an OpenAPI document cannot be converted to the IR.

    Attributes:
        path: JSON-pointer-like path to the problematic element.
        detail: Human-readable explanation.
    """

    def __init__(self, detail: str, *, path: str | None = None) -> None:
        self.detail = detail
        self.path = path
        msg = f"{path}: {detail}" if path else detail
        super().__init__(msg)


class ValidationError(SchemaError):
    """Raised when an IR graph fails a consistency check.

    For example, a :class:`~retcon.schema.types.ModelRef` that points to a
    model name not present in :attr:`~retcon.schema.graph.APISchema.models`.
    """

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


__all__ = (
    "SchemaError",
    "ConversionError",
    "ValidationError",
)
