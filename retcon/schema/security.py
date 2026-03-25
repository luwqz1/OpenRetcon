from __future__ import annotations

import msgspec

from retcon.schema.nodes import Node


class SecurityScheme(Node, kw_only=True):
    """Base class for all security scheme IR nodes."""

    name: str
    description: str | None = None


class ApiKeyScheme(SecurityScheme, kw_only=True):
    """An API-key scheme transmitted via header, query, or cookie."""

    param_name: str
    location: str  # "header", "query", or "cookie"


class HttpScheme(SecurityScheme, kw_only=True):
    """An HTTP authentication scheme (e.g. bearer, basic)."""

    scheme: str  # "bearer", "basic", "digest", …
    bearer_format: str | None = None


class OAuth2Flow(Node, kw_only=True):
    """A single OAuth 2.0 flow."""

    authorization_url: str | None = None
    token_url: str | None = None
    refresh_url: str | None = None
    scopes: dict[str, str] = msgspec.field(default_factory=dict)


class OAuth2Scheme(SecurityScheme, kw_only=True):
    """An OAuth 2.0 scheme with one or more flows."""

    implicit: OAuth2Flow | None = None
    password: OAuth2Flow | None = None
    client_credentials: OAuth2Flow | None = None
    authorization_code: OAuth2Flow | None = None


class OpenIdConnectScheme(SecurityScheme, kw_only=True):
    """An OpenID Connect scheme."""

    open_id_connect_url: str


__all__ = (
    "ApiKeyScheme",
    "HttpScheme",
    "OAuth2Flow",
    "OAuth2Scheme",
    "OpenIdConnectScheme",
    "SecurityScheme",
)
