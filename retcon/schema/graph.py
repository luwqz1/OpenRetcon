from __future__ import annotations

from retcon.schema.enums import Enum
from retcon.schema.nodes import Node
from retcon.schema.objects import Model
from retcon.schema.paths import Endpoint
from retcon.schema.webhook import Webhook


class APISchema(Node, kw_only=True):
    """Version-independent intermediate representation of an API.

    Acts as the root of the IR tree.  Contains flat registries for
    :class:`Model`, :class:`Enum`, :class:`Endpoint`, and :class:`Webhook`
    nodes.  Cross-references between nodes use
    :class:`~retcon.schema.types.ModelRef` /
    :class:`~retcon.schema.types.EnumRef` by name.
    """

    title: str
    version: str
    description: str | None = None
    models: list[Model] = []
    enums: list[Enum] = []
    endpoints: list[Endpoint] = []
    webhooks: list[Webhook] = []


__all__ = ("APISchema",)
