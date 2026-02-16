from __future__ import annotations

from retcon.openapi.v3 import oas300, oas310, oas320
from retcon.schema.graph import APISchema


def from_openapi_300(spec: oas300.OpenAPI) -> APISchema:
    raise NotImplementedError


def from_openapi_310(spec: oas310.OpenAPI) -> APISchema:
    raise NotImplementedError


def from_openapi_320(spec: oas320.OpenAPI) -> APISchema:
    raise NotImplementedError


__all__ = (
    "from_openapi_300",
    "from_openapi_310",
    "from_openapi_320",
)
