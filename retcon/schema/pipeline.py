from __future__ import annotations

import dataclasses
import typing

from retcon.openapi.parser import OpenAPI3Object, OpenAPIDocument, OpenAPIParseError, decode_openapi_document
from retcon.schema.converter import from_openapi
from retcon.schema.errors import ConversionError
from retcon.schema.graph import APISchema
from retcon.schema.nodes import Node
from retcon.schema.visitor import NodeVisitor

type CustomNodeFactory = typing.Callable[[APISchema], Node | typing.Iterable[Node] | None]


def build_schema_pipeline(
    document: OpenAPIDocument,
    document_type: typing.Literal["json", "yaml"] = "json",
    *,
    custom_nodes: typing.Iterable[Node] = (),
    custom_node_factories: typing.Iterable[CustomNodeFactory] = (),
    visitor: NodeVisitor | None = None,
) -> tuple[OpenAPI3Object, APISchema]:
    try:
        openapi = decode_openapi_document(document, document_type)
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
    document_type: typing.Literal["json", "yaml"] = "json",
    custom_nodes: typing.Iterable[Node] = (),
    custom_node_factories: typing.Iterable[CustomNodeFactory] = (),
    visitor: NodeVisitor | None = None,
) -> GenerationResult:
    openapi, schema = build_schema_pipeline(
        document,
        document_type,
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
    def generate(self, schema: APISchema) -> dict[str, str]: ...


@dataclasses.dataclass(slots=True)
class GenerationResult:
    openapi: OpenAPI3Object
    schema: APISchema
    files: dict[str, str]


__all__ = (
    "CustomNodeFactory",
    "GenerationResult",
    "GeneratorProtocol",
    "apply_custom_nodes",
    "build_schema_pipeline",
    "run_generation_pipeline",
)
