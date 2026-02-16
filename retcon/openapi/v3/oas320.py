"""OpenAPI 3.2.0 specification models.

Typed models for the OpenAPI Specification version 3.2.0,
based on ``msgspec.Struct`` for high-performance serialization and deserialization.

OpenAPI 3.2.0 is backward-compatible with 3.1.x and introduces:

* Enhanced Tag system: ``summary``, ``parent``, ``kind`` fields.
* ``$self`` field on the root OpenAPI Object for document identity.
* ``name`` field on Server Object.
* ``additionalOperations`` on Path Item Object for custom HTTP methods.
* ``querystring`` on Operation Object.
* ``query`` as a new value for the ``in`` field in Parameter Object.
* ``itemSchema`` on Media Type Object for sequential / streaming data.
* ``dataValue`` and ``serializedValue`` on Example Object.
* ``defaultMapping`` on Discriminator Object.
* ``mediaTypes`` in Components Object.
* OAuth2 ``deviceAuthorization`` flow, ``oauth2MetadataUrl``, and
  ``deprecated`` on Security Scheme Object.

Objects that may appear as a ``$ref`` reference include an optional ``ref``
field (mapped to ``$ref`` in JSON).

See: https://spec.openapis.org/oas/v3.2.0
"""

from __future__ import annotations

import typing

import msgspec


class Contact(msgspec.Struct, kw_only=True, omit_defaults=True):
    """Contact information for the exposed API.

    See: https://spec.openapis.org/oas/v3.2.0#contact-object
    """

    name: str | None = None
    url: str | None = None
    email: str | None = None


class License(msgspec.Struct, kw_only=True, omit_defaults=True):
    """License information for the exposed API.

    ``identifier`` and ``url`` are mutually exclusive.

    See: https://spec.openapis.org/oas/v3.2.0#license-object
    """

    name: str
    identifier: str | None = None
    url: str | None = None


class Info(msgspec.Struct, kw_only=True, omit_defaults=True):
    """Metadata about the API.

    See: https://spec.openapis.org/oas/v3.2.0#info-object
    """

    title: str
    version: str
    summary: str | None = None
    description: str | None = None
    termsOfService: str | None = None
    contact: Contact | None = None
    license: License | None = None


class ServerVariable(msgspec.Struct, kw_only=True, omit_defaults=True):
    """An object representing a Server Variable for server URL template substitution.

    See: https://spec.openapis.org/oas/v3.2.0#server-variable-object
    """

    default: str
    enum: list[str] | None = None
    description: str | None = None


class Server(msgspec.Struct, kw_only=True, omit_defaults=True):
    """An object representing a Server.

    In 3.2.0, the optional ``name`` field provides a unique string identifier
    for the server.

    See: https://spec.openapis.org/oas/v3.2.0#server-object
    """

    url: str
    description: str | None = None
    name: str | None = None
    variables: dict[str, ServerVariable] | None = None


class ExternalDocumentation(msgspec.Struct, kw_only=True, omit_defaults=True):
    """Allows referencing an external resource for extended documentation.

    See: https://spec.openapis.org/oas/v3.2.0#external-documentation-object
    """

    url: str
    description: str | None = None


class Tag(msgspec.Struct, kw_only=True, omit_defaults=True):
    """Adds metadata to a single tag used by the Operation Object.

    In 3.2.0, tags gain ``summary`` (replacing ``x-displayName``), ``parent``
    for hierarchical organisation, and ``kind`` for classification.

    See: https://spec.openapis.org/oas/v3.2.0#tag-object
    """

    name: str
    summary: str | None = None
    description: str | None = None
    parent: str | None = None
    kind: str | None = None
    externalDocs: ExternalDocumentation | None = None


class Reference(msgspec.Struct, kw_only=True, omit_defaults=True):
    """A simple object to allow referencing other components in the specification.

    ``summary`` and ``description`` may accompany ``$ref`` and act as overrides
    of the referenced object's values.

    See: https://spec.openapis.org/oas/v3.2.0#reference-object
    """

    ref: str = msgspec.field(name="$ref")
    summary: str | None = None
    description: str | None = None


class Discriminator(msgspec.Struct, kw_only=True, omit_defaults=True):
    """Aids in serialization, deserialization, and validation when request bodies
    or response payloads may be one of a number of different schemas.

    In 3.2.0, ``defaultMapping`` provides a fallback schema when no mapping
    matches.

    See: https://spec.openapis.org/oas/v3.2.0#discriminator-object
    """

    propertyName: str
    mapping: dict[str, str] | None = None
    defaultMapping: str | None = None


class XML(msgspec.Struct, kw_only=True, omit_defaults=True):
    """A metadata object that allows for more fine-tuned XML model definitions.

    See: https://spec.openapis.org/oas/v3.2.0#xml-object
    """

    name: str | None = None
    namespace: str | None = None
    prefix: str | None = None
    attribute: bool = False
    wrapped: bool = False


class Schema(msgspec.Struct, kw_only=True, omit_defaults=True):
    """The Schema Object allows the definition of input and output data types.

    Fully compatible with JSON Schema Draft 2020-12 (same as 3.1.0).

    When ``ref`` is set the object represents a ``$ref`` reference.

    See: https://spec.openapis.org/oas/v3.2.0#schema-object
    """

    ref: str | None = msgspec.field(name="$ref", default=None)
    id: str | None = msgspec.field(name="$id", default=None)
    schema: str | None = msgspec.field(name="$schema", default=None)
    anchor: str | None = msgspec.field(name="$anchor", default=None)
    dynamicRef: str | None = msgspec.field(name="$dynamicRef", default=None)
    dynamicAnchor: str | None = msgspec.field(name="$dynamicAnchor", default=None)
    vocabulary: dict[str, bool] | None = msgspec.field(name="$vocabulary", default=None)
    comment: str | None = msgspec.field(name="$comment", default=None)
    defs: dict[str, Schema] | None = msgspec.field(name="$defs", default=None)
    type: str | list[str] | None = None
    enum: list[typing.Any] | None = None
    const: typing.Any = msgspec.UNSET
    multipleOf: float | None = None
    maximum: float | None = None
    exclusiveMaximum: float | None = None
    minimum: float | None = None
    exclusiveMinimum: float | None = None
    maxLength: int | None = None
    minLength: int | None = None
    pattern: str | None = None
    maxItems: int | None = None
    minItems: int | None = None
    uniqueItems: bool | None = None
    maxContains: int | None = None
    minContains: int | None = None
    maxProperties: int | None = None
    minProperties: int | None = None
    required: list[str] | None = None
    dependentRequired: dict[str, list[str]] | None = None
    allOf: list[Schema] | None = None
    anyOf: list[Schema] | None = None
    oneOf: list[Schema] | None = None
    not_: Schema | None = msgspec.field(name="not", default=None)
    if_: Schema | None = msgspec.field(name="if", default=None)
    then_: Schema | None = msgspec.field(name="then", default=None)
    else_: Schema | None = msgspec.field(name="else", default=None)
    dependentSchemas: dict[str, Schema] | None = None
    prefixItems: list[Schema] | None = None
    items: Schema | None = None
    contains: Schema | None = None
    properties: dict[str, Schema] | None = None
    patternProperties: dict[str, Schema] | None = None
    additionalProperties: Schema | bool | None = None
    propertyNames: Schema | None = None
    unevaluatedItems: Schema | None = None
    unevaluatedProperties: Schema | None = None
    title: str | None = None
    description: str | None = None
    default: typing.Any = None
    deprecated: bool | None = None
    readOnly: bool | None = None
    writeOnly: bool | None = None
    examples: list[typing.Any] | None = None
    format: str | None = None
    contentEncoding: str | None = None
    contentMediaType: str | None = None
    contentSchema: Schema | None = None
    discriminator: Discriminator | None = None
    xml: XML | None = None
    externalDocs: ExternalDocumentation | None = None
    example: typing.Any = None  # Deprecated in favour of ``examples``


class Example(msgspec.Struct, kw_only=True, omit_defaults=True):
    """Holds a reusable example value.

    In 3.2.0, ``dataValue`` and ``serializedValue`` provide structured and
    serialized example representations alongside the existing ``value``.

    When ``ref`` is set the object represents a ``$ref`` reference.

    See: https://spec.openapis.org/oas/v3.2.0#example-object
    """

    ref: str | None = msgspec.field(name="$ref", default=None)
    summary: str | None = None
    description: str | None = None
    value: typing.Any = None
    dataValue: typing.Any = None
    serializedValue: str | None = None
    externalValue: str | None = None


class Encoding(msgspec.Struct, kw_only=True, omit_defaults=True):
    """A single encoding definition applied to a single schema property.

    See: https://spec.openapis.org/oas/v3.2.0#encoding-object
    """

    contentType: str | None = None
    headers: dict[str, Header] | None = None
    style: str | None = None
    explode: bool | None = None
    allowReserved: bool = False


class MediaType(msgspec.Struct, kw_only=True, omit_defaults=True):
    """Each Media Type Object provides schema and examples for the media type
    identified by its key.

    In 3.2.0, ``itemSchema`` describes the schema of individual items in
    sequential / streaming media types (e.g. ``application/jsonl``,
    ``text/event-stream``).

    When ``ref`` is set the object represents a ``$ref`` reference.

    See: https://spec.openapis.org/oas/v3.2.0#media-type-object
    """

    ref: str | None = msgspec.field(name="$ref", default=None)
    schema: Schema | None = None
    example: typing.Any = None
    examples: dict[str, Example] | None = None
    encoding: dict[str, Encoding] | None = None
    itemSchema: Schema | None = None


class Header(msgspec.Struct, kw_only=True, omit_defaults=True):
    """Follows the structure of the Parameter Object with some differences.

    When ``ref`` is set the object represents a ``$ref`` reference.

    See: https://spec.openapis.org/oas/v3.2.0#header-object
    """

    ref: str | None = msgspec.field(name="$ref", default=None)
    description: str | None = None
    required: bool = False
    deprecated: bool = False
    allowEmptyValue: bool = False
    style: str = "simple"
    explode: bool = False
    allowReserved: bool = False
    schema: Schema | None = None
    example: typing.Any = None
    examples: dict[str, Example] | None = None
    content: dict[str, MediaType] | None = None


class Parameter(msgspec.Struct, kw_only=True, omit_defaults=True):
    """Describes a single operation parameter.

    In 3.2.0, ``in`` may also be ``"querystring"`` for an Operation's
    ``querystring`` field.

    When ``ref`` is set the object represents a ``$ref`` reference.
    When not a reference, ``name`` and ``in_`` are REQUIRED.

    See: https://spec.openapis.org/oas/v3.2.0#parameter-object
    """

    ref: str | None = msgspec.field(name="$ref", default=None)
    name: str | None = None
    in_: str | None = msgspec.field(name="in", default=None)
    description: str | None = None
    required: bool = False
    deprecated: bool = False
    allowEmptyValue: bool = False
    style: str | None = None
    explode: bool | None = None
    allowReserved: bool = False
    schema: Schema | None = None
    example: typing.Any = None
    examples: dict[str, Example] | None = None
    content: dict[str, MediaType] | None = None


class Link(msgspec.Struct, kw_only=True, omit_defaults=True):
    """Represents a possible design-time link for a response.

    When ``ref`` is set the object represents a ``$ref`` reference.

    See: https://spec.openapis.org/oas/v3.2.0#link-object
    """

    ref: str | None = msgspec.field(name="$ref", default=None)
    operationRef: str | None = None
    operationId: str | None = None
    parameters: dict[str, typing.Any] | None = None
    requestBody: typing.Any = None
    description: str | None = None
    server: Server | None = None


class Response(msgspec.Struct, kw_only=True, omit_defaults=True):
    """Describes a single response from an API Operation.

    When ``ref`` is set the object represents a ``$ref`` reference.
    When not a reference, ``description`` is REQUIRED.

    See: https://spec.openapis.org/oas/v3.2.0#response-object
    """

    ref: str | None = msgspec.field(name="$ref", default=None)
    description: str | None = None
    headers: dict[str, Header] | None = None
    content: dict[str, MediaType] | None = None
    links: dict[str, Link] | None = None


class RequestBody(msgspec.Struct, kw_only=True, omit_defaults=True):
    """Describes a single request body.

    When ``ref`` is set the object represents a ``$ref`` reference.
    When not a reference, ``content`` is REQUIRED.

    See: https://spec.openapis.org/oas/v3.2.0#request-body-object
    """

    ref: str | None = msgspec.field(name="$ref", default=None)
    content: dict[str, MediaType] | None = None
    description: str | None = None
    required: bool = False


class OAuthFlow(msgspec.Struct, kw_only=True, omit_defaults=True):
    """Configuration details for a supported OAuth Flow.

    Depending on the flow type, ``authorizationUrl`` and/or ``tokenUrl``
    may be REQUIRED.

    See: https://spec.openapis.org/oas/v3.2.0#oauth-flow-object
    """

    scopes: dict[str, str]
    authorizationUrl: str | None = None
    tokenUrl: str | None = None
    refreshUrl: str | None = None


class OAuthFlows(msgspec.Struct, kw_only=True, omit_defaults=True):
    """Allows configuration of the supported OAuth Flows.

    In 3.2.0, ``deviceAuthorization`` is added for OAuth 2.0 Device
    Authorization Grant (RFC 8628).

    See: https://spec.openapis.org/oas/v3.2.0#oauth-flows-object
    """

    implicit: OAuthFlow | None = None
    password: OAuthFlow | None = None
    clientCredentials: OAuthFlow | None = None
    authorizationCode: OAuthFlow | None = None
    deviceAuthorization: OAuthFlow | None = None


class SecurityScheme(msgspec.Struct, kw_only=True, omit_defaults=True):
    """Defines a security scheme that can be used by the operations.

    In 3.2.0, ``deprecated`` marks a scheme as deprecated, and
    ``oauth2MetadataUrl`` provides metadata discovery.

    When ``ref`` is set the object represents a ``$ref`` reference.
    When not a reference, ``type`` is REQUIRED.

    See: https://spec.openapis.org/oas/v3.2.0#security-scheme-object
    """

    ref: str | None = msgspec.field(name="$ref", default=None)
    type: str | None = None
    description: str | None = None
    name: str | None = None
    in_: str | None = msgspec.field(name="in", default=None)
    scheme: str | None = None
    bearerFormat: str | None = None
    flows: OAuthFlows | None = None
    openIdConnectUrl: str | None = None
    oauth2MetadataUrl: str | None = None
    deprecated: bool = False


class Operation(msgspec.Struct, kw_only=True, omit_defaults=True):
    """Describes a single API operation on a path.

    In 3.2.0, ``querystring`` allows defining all query parameters as a single
    Schema Object.

    See: https://spec.openapis.org/oas/v3.2.0#operation-object
    """

    tags: list[str] | None = None
    summary: str | None = None
    description: str | None = None
    externalDocs: ExternalDocumentation | None = None
    operationId: str | None = None
    parameters: list[Parameter] | None = None
    querystring: Schema | None = None
    requestBody: RequestBody | None = None
    responses: dict[str, Response] | None = None
    callbacks: dict[str, typing.Any] | None = None
    deprecated: bool = False
    security: list[dict[str, list[str]]] | None = None
    servers: list[Server] | None = None


class PathItem(msgspec.Struct, kw_only=True, omit_defaults=True):
    """Describes the operations available on a single path.

    In 3.2.0, ``additionalOperations`` allows defining operations for custom
    HTTP methods not covered by the fixed fields.

    See: https://spec.openapis.org/oas/v3.2.0#path-item-object
    """

    ref: str | None = msgspec.field(name="$ref", default=None)
    summary: str | None = None
    description: str | None = None
    get: Operation | None = None
    put: Operation | None = None
    post: Operation | None = None
    delete: Operation | None = None
    options: Operation | None = None
    head: Operation | None = None
    patch: Operation | None = None
    trace: Operation | None = None
    query: Operation | None = None
    additionalOperations: dict[str, Operation] | None = None
    servers: list[Server] | None = None
    parameters: list[Parameter] | None = None


class Components(msgspec.Struct, kw_only=True, omit_defaults=True):
    """Holds a set of reusable objects for different aspects of the OAS.

    All objects defined within the Components Object will have no effect on the
    API unless they are explicitly referenced from properties outside the
    Components Object.

    In 3.2.0, ``mediaTypes`` is added for reusable Media Type Objects.

    See: https://spec.openapis.org/oas/v3.2.0#components-object
    """

    schemas: dict[str, Schema] | None = None
    responses: dict[str, Response] | None = None
    parameters: dict[str, Parameter] | None = None
    examples: dict[str, Example] | None = None
    requestBodies: dict[str, RequestBody] | None = None
    headers: dict[str, Header] | None = None
    securitySchemes: dict[str, SecurityScheme] | None = None
    links: dict[str, Link] | None = None
    callbacks: dict[str, typing.Any] | None = None
    pathItems: dict[str, PathItem] | None = None
    mediaTypes: dict[str, MediaType] | None = None


class OpenAPI(msgspec.Struct, kw_only=True, omit_defaults=True):
    """Root document object of the OpenAPI definition.

    In 3.2.0, ``$self`` provides the self-assigned URI (and base URI) of the
    document.  ``paths`` is optional — at least one of ``paths``, ``webhooks``,
    or ``components`` MUST be present.

    See: https://spec.openapis.org/oas/v3.2.0#openapi-object
    """

    openapi: str
    info: Info
    self_: str | None = msgspec.field(name="$self", default=None)
    jsonSchemaDialect: str | None = None
    servers: list[Server] | None = None
    paths: dict[str, PathItem] | None = None
    webhooks: dict[str, PathItem] | None = None
    components: Components | None = None
    security: list[dict[str, list[str]]] | None = None
    tags: list[Tag] | None = None
    externalDocs: ExternalDocumentation | None = None


__all__ = (
    "Contact",
    "License",
    "Info",
    "ServerVariable",
    "Server",
    "ExternalDocumentation",
    "Tag",
    "Reference",
    "Discriminator",
    "XML",
    "Schema",
    "Example",
    "Encoding",
    "MediaType",
    "Header",
    "Parameter",
    "Link",
    "Response",
    "RequestBody",
    "OAuthFlow",
    "OAuthFlows",
    "SecurityScheme",
    "Operation",
    "PathItem",
    "Components",
    "OpenAPI",
)
