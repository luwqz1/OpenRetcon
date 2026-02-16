from __future__ import annotations

from retcon.schema.nodes import Node
from retcon.schema.paths import Operation


class Webhook(Node, kw_only=True):
    """A named webhook that groups one or more :class:`Operation` instances.

    Webhooks represent requests initiated by the API provider (as opposed
    to the consumer) and are available starting from OpenAPI 3.1.0.
    """

    name: str
    operations: list[Operation] = []
    description: str | None = None


__all__ = ("Webhook",)
