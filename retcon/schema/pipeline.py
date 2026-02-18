from __future__ import annotations

import dataclasses
import typing

from retcon.openapi.parser import OpenAPIDocument, OpenAPIObject, OpenAPIParseError, decode_openapi_document
from retcon.schema.converter import from_openapi
from retcon.schema.errors import ConversionError
from retcon.schema.graph import APISchema
from retcon.schema.nodes import Node
from retcon.schema.visitor import NodeVisitor

type CustomNodeFactory = typing.Callable[[APISchema], Node | typing.Iterable[Node] | None]


def build_schema_pipeline(
    document: OpenAPIDocument,
    *,
    custom_nodes: typing.Iterable[Node] = (),
    custom_node_factories: typing.Iterable[CustomNodeFactory] = (),
    visitor: NodeVisitor | None = None,
) -> tuple[OpenAPIObject, APISchema]:
    """Run `OpenAPI` parsing, conversion and schema enrichment pipeline."""
    try:
        openapi = decode_openapi_document(document)
    except OpenAPIParseError as exc:
        raise ConversionError(str(exc)) from exc
    schema = from_openapi(openapi)
    apply_custom_nodes(schema, nodes=custom_nodes, factories=custom_node_factories)

    if visitor is not None:
        visitor.visit(schema)

    return (openapi, schema)


def run_generation_pipeline(
    document: OpenAPIDocument,
    generator: GeneratorProtocol,
    *,
    custom_nodes: typing.Iterable[Node] = (),
    custom_node_factories: typing.Iterable[CustomNodeFactory] = (),
    visitor: NodeVisitor | None = None,
) -> GenerationResult:
    """Run full generation pipeline from `OpenAPI` document to generated files."""
    openapi, schema = build_schema_pipeline(
        document,
        custom_nodes=custom_nodes,
        custom_node_factories=custom_node_factories,
        visitor=visitor,
    )
    files = generator.generate(schema)
    return GenerationResult(openapi=openapi, schema=schema, files=files)


def apply_custom_nodes(
    schema: APISchema,
    *,
    nodes: typing.Iterable[Node] = (),
    factories: typing.Iterable[CustomNodeFactory] = (),
) -> APISchema:
    """Attach custom nodes to schema, including nodes created `on-the-fly`."""
    for node in nodes:
        schema.add_node(node)

    for factory in factories:
        produced = factory(schema)
        if produced is None:
            continue

        if isinstance(produced, Node):
            schema.add_node(produced)
            continue

        for node in produced:
            schema.add_node(node)

    return schema


class GeneratorProtocol(typing.Protocol):
    def generate(self, schema: APISchema) -> dict[str, str]:
        ...


@dataclasses.dataclass(slots=True)
class GenerationResult:
    openapi: OpenAPIObject
    schema: APISchema
    files: dict[str, str]


__all__ = (
    "CustomNodeFactory",
    "GeneratorProtocol",
    "GenerationResult",
    "apply_custom_nodes",
    "build_schema_pipeline",
    "run_generation_pipeline",
)
