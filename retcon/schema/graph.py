from __future__ import annotations

import typing

import msgspec

from retcon.schema.enums import Enum
from retcon.schema.nodes import Node
from retcon.schema.objects import Model
from retcon.schema.paths import Endpoint, NamedResponse
from retcon.schema.security import SecurityScheme
from retcon.schema.webhook import Webhook


class APISchema(Node, kw_only=True):
    """Version-independent intermediate representation of an API.

    Contains flat registries for
    :class:`Model`, :class:`Enum`, :class:`Endpoint`, and :class:`Webhook`
    nodes.  Cross-references between nodes use
    :class:`~retcon.schema.types.ModelRef` /
    :class:`~retcon.schema.types.EnumRef` by name.
    """

    title: str
    version: str
    description: str | None = None
    servers: list[str] = msgspec.field(default_factory=list)
    models: list[Model] = msgspec.field(default_factory=list)
    enums: list[Enum] = msgspec.field(default_factory=list)
    endpoints: list[Endpoint] = msgspec.field(default_factory=list)
    webhooks: list[Webhook] = msgspec.field(default_factory=list)
    named_responses: list[NamedResponse] = msgspec.field(default_factory=list)
    security_schemes: list[SecurityScheme] = msgspec.field(default_factory=list)
    custom_nodes: list[Node] = msgspec.field(default_factory=list)

    def add_node(self, node: Node) -> None:
        """Add *node* to the appropriate schema registry."""
        if isinstance(node, Model):
            self.models.append(node)
            return
        if isinstance(node, Enum):
            self.enums.append(node)
            return
        if isinstance(node, Endpoint):
            self.endpoints.append(node)
            return
        if isinstance(node, Webhook):
            self.webhooks.append(node)
            return
        if isinstance(node, NamedResponse):
            self.named_responses.append(node)
            return
        self.custom_nodes.append(node)

    def add_nodes(self, nodes: typing.Iterable[Node]) -> None:
        """Add multiple nodes preserving input order."""
        for node in nodes:
            self.add_node(node)


__all__ = ("APISchema",)
