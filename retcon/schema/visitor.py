from __future__ import annotations

import typing

import msgspec

from retcon.schema.nodes import Node

if typing.TYPE_CHECKING:
    from retcon.schema.graph import APISchema


class NodeVisitor:
    """Walk tree of nodes and optionally mutate nodes in-place.

    For every node encountered the visitor calls ``visit_<ClassName>(node)``.
    If no specific handler exists, :meth:`generic_visit` is used which
    recurses into all child nodes discovered via ``msgspec`` field
    introspection.

    Subclasses override ``visit_*`` methods to implement custom logic.
    Call :meth:`generic_visit` inside a handler to continue the traversal
    into the node's children.  Placing the call at the beginning or end
    of the handler gives pre-order or post-order traversal respectively.

    Because the visitor is *mutable*, handlers may freely reassign fields
    on the node they receive::

        class PrefixModels(NodeVisitor):
            def visit_Model(self, node):
                node.name = f"Api{node.name}"
                self.generic_visit(node)

    To inject new nodes into the schema during visitation, call
    :meth:`emit` from any handler.  The node is added to the schema
    registry and then visited immediately::

        class AddStatusEnum(NodeVisitor):
            def visit_APISchema(self, schema):
                from retcon.schema.enums import Enum, EnumValue
                extra = Enum(name="Status", values=[
                    EnumValue(name="ACTIVE", value="active"),
                    EnumValue(name="INACTIVE", value="inactive"),
                ])
                self.emit(schema, extra)   # registers + visits the new node
                self.generic_visit(schema)
    """

    def visit(self, node: Node) -> None:
        """Dispatch *node* to the appropriate ``visit_*`` handler."""
        method_name = f"visit_{type(node).__name__}"
        handler = getattr(self, method_name, self.generic_visit)
        handler(node)

    def emit(self, schema: APISchema, node: Node) -> None:
        """Add *node* to the appropriate *schema* registry and visit it.

        Use this inside ``visit_*`` handlers to inject nodes that are not
        derived from the original OpenAPI document.  The node is registered
        via :meth:`~retcon.schema.graph.APISchema.add_node` and then
        dispatched through :meth:`visit` so that any visitor hooks apply.
        """
        schema.add_node(node)
        self.visit(node)

    def generic_visit(self, node: Node) -> None:
        """Recurse into every child :class:`Node` reachable from *node*."""
        for field_info in msgspec.structs.fields(node):
            value = getattr(node, field_info.name)

            if isinstance(value, Node):
                self.visit(value)

            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, Node):
                        self.visit(item)

            elif isinstance(value, dict):
                for item in value.values():
                    if isinstance(item, Node):
                        self.visit(item)


__all__ = ("NodeVisitor",)
