import msgspec


class Node(msgspec.Struct, kw_only=True):
    pass


__all__ = ("Node",)
