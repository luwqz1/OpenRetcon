from __future__ import annotations

import dataclasses
import re
import typing

import msgspec

from retcon.openapi.parser import (
    OpenAPIDocument,
    OpenAPIParseError,
    decode_openapi_document,
)
from retcon.openapi.v3 import oas300, oas310, oas320
from retcon.schema.enums import Enum, EnumValue
from retcon.schema.errors import ConversionError
from retcon.schema.graph import APISchema
from retcon.schema.objects import Field, Model
from retcon.schema.paths import Endpoint, NamedResponse, Operation, Parameter, RequestBody, Response
from retcon.schema.security import ApiKeyScheme, HttpScheme, OAuth2Flow, OAuth2Scheme, OpenIdConnectScheme, SecurityScheme
from retcon.schema.types import (
    AnyType,
    ArrayType,
    BooleanType,
    Constraints,
    EnumRef,
    IntegerType,
    MapType,
    ModelRef,
    NumberType,
    StringType,
    TypeRef,
    UnionType,
)
from retcon.schema.webhook import Webhook

type OAS3 = oas300.OpenAPI | oas310.OpenAPI | oas320.OpenAPI

_OPERATION_FIELDS: typing.Final = ("get", "put", "post", "delete", "options", "head", "patch", "trace", "query")
_PATH_OPERATIONS_PREFIX: typing.Final = "#/paths/"
_SCHEMA_REF_PREFIX: typing.Final = "#/components/schemas/"
_RESPONSE_REF_PREFIX: typing.Final = "#/components/responses/"
_TYPE_MAP: typing.Final = {
    "string": StringType,
    "integer": IntegerType,
    "number": NumberType,
    "boolean": BooleanType,
    "array": ArrayType,
    "object": MapType,
}
_PASCAL_SPLIT_RE: typing.Final = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|[^a-zA-Z0-9]+")


@dataclasses.dataclass
class _ConversionContext:
    enum_names: set[str]
    model_names: set[str]
    component_responses: dict[str, typing.Any] = dataclasses.field(default_factory=dict)
    inline_enums: dict[str, Enum] = dataclasses.field(default_factory=dict)
    inline_models: dict[str, Model] = dataclasses.field(default_factory=dict)
    model_signatures: dict[str, str] = dataclasses.field(default_factory=dict)
    named_responses: dict[str, NamedResponse] = dataclasses.field(default_factory=dict)


def from_openapi_document(document: OpenAPIDocument, document_type: typing.Literal["json", "yaml"]) -> APISchema:
    try:
        spec = decode_openapi_document(document, document_type)
    except OpenAPIParseError as exc:
        raise ConversionError(str(exc)) from exc

    return from_openapi(spec)


def from_openapi(spec: OAS3) -> APISchema:
    if isinstance(spec, oas300.OpenAPI):
        return from_openapi_30x(spec)

    if isinstance(spec, oas310.OpenAPI):
        return from_openapi_31x(spec)

    if isinstance(spec, oas320.OpenAPI):
        return from_openapi_32x(spec)

    raise ConversionError(f"Unsupported OpenAPI version: {spec.openapi}")


def from_openapi_30x(spec: oas300.OpenAPI) -> APISchema:
    return _convert_openapi(spec)


def from_openapi_31x(spec: oas310.OpenAPI) -> APISchema:
    return _convert_openapi(spec)


def from_openapi_32x(spec: oas320.OpenAPI) -> APISchema:
    return _convert_openapi(spec)


def _convert_openapi(spec: oas300.OpenAPI | oas310.OpenAPI | oas320.OpenAPI) -> APISchema:
    schemas = _extract_component_schemas(spec)
    component_responses = _extract_component_responses(spec)
    enum_names = {name for name, schema in schemas.items() if _schema_is_enum(schema)}
    model_names = {name for name, schema in schemas.items() if _schema_is_model(schema) and name not in enum_names}
    context = _ConversionContext(enum_names=enum_names, model_names=model_names, component_responses=component_responses)

    api_schema = APISchema(
        title=spec.info.title,
        version=spec.info.version,
        description=getattr(spec.info, "description", None),
        servers=[s.url for s in spec.servers] if hasattr(spec, "servers") and spec.servers else [],
    )

    for enum_name in sorted(enum_names):
        api_schema.enums.append(_convert_enum(enum_name, schemas[enum_name]))

    for model_name in sorted(model_names):
        signature = _compute_model_signature(schemas[model_name])
        context.model_signatures[signature] = model_name

    for model_name in sorted(model_names):
        model = _convert_model(model_name, schemas[model_name], context)
        api_schema.models.append(model)

    for response_name in sorted(component_responses.keys()):
        response_obj = component_responses[response_name]
        resolved_content: dict[str, TypeRef] = {}
        schema_ref: str | None = None

        for content_type, media in (getattr(response_obj, "content", None) or {}).items():
            type_ref = _to_type_ref(getattr(media, "schema", None), context, name_hint=None)
            resolved_content[content_type] = type_ref

            if schema_ref is None and isinstance(type_ref, ModelRef):
                schema_ref = type_ref.name

        context.named_responses[response_name] = NamedResponse(
            name=response_name,
            status_codes=[],
            description=getattr(response_obj, "description", None),
            content=resolved_content,
            schema_ref=schema_ref,
        )

    api_schema.endpoints.extend(_convert_paths(spec, context))
    api_schema.webhooks.extend(_convert_webhooks(spec, context))
    api_schema.security_schemes.extend(_convert_security_schemes(spec))

    for inline_enum in context.inline_enums.values():
        api_schema.enums.append(inline_enum)

    for inline_model in context.inline_models.values():
        api_schema.models.append(inline_model)

    for named_response in context.named_responses.values():
        api_schema.named_responses.append(named_response)

    return api_schema


def _extract_component_schemas(spec: OAS3, /) -> dict[str, typing.Any]:
    components = getattr(spec, "components", None)

    if components is None:
        return {}

    schemas = getattr(components, "schemas", None)

    if not schemas:
        return {}

    return typing.cast("dict[str, typing.Any]", schemas)


def _extract_component_responses(spec: OAS3, /) -> dict[str, typing.Any]:
    components = getattr(spec, "components", None)

    if components is None:
        return {}

    responses = getattr(components, "responses", None)

    if not responses:
        return {}

    return typing.cast("dict[str, typing.Any]", responses)


def _convert_enum(name: str, schema: typing.Any) -> Enum:
    raw_values = getattr(schema, "enum", None) or []
    members: list[EnumValue] = []
    used_names: set[str] = set()

    for index, value in enumerate(raw_values):
        member_name = _to_enum_member_name(value, index)

        while member_name in used_names:
            member_name = f"{member_name}_{index}"

        used_names.add(member_name)
        members.append(EnumValue(name=member_name, value=value))

    return Enum(
        name=name,
        values=members,
        description=getattr(schema, "description", None),
    )


def _convert_model(name: str, schema: typing.Any, context: _ConversionContext) -> Model:
    properties = typing.cast("dict[str, typing.Any]", getattr(schema, "properties", None) or {})
    required = set(getattr(schema, "required", None) or [])
    fields: list[Field] = []

    for prop_name, prop_schema in properties.items():
        field_default = getattr(prop_schema, "default", msgspec.UNSET)
        field_desc = getattr(prop_schema, "description", None)
        field_deprecated = bool(getattr(prop_schema, "deprecated", False))
        name_hint = name + _to_pascal_case_simple(prop_name)
        field_kwargs: dict[str, typing.Any] = {
            "name": prop_name,
            "type": _to_type_ref(prop_schema, context, name_hint=name_hint, field_description=field_desc),
            "required": prop_name in required,
            "description": field_desc,
            "deprecated": field_deprecated,
        }

        if field_default is not msgspec.UNSET and field_default is not None:
            field_kwargs["default"] = field_default

        fields.append(Field(**field_kwargs))

    return Model(
        name=name,
        fields=fields,
        description=getattr(schema, "description", None),
        deprecated=bool(getattr(schema, "deprecated", False)),
    )


def _convert_paths(spec: OAS3, context: _ConversionContext) -> list[Endpoint]:
    path_items = typing.cast("dict[str, typing.Any]", getattr(spec, "paths", None) or {})
    endpoints: list[Endpoint] = []

    for path, path_item in path_items.items():
        operations = _convert_path_item(path, path_item, context, is_webhook=False)

        if not operations:
            continue

        endpoints.append(
            Endpoint(
                path=path,
                operations=operations,
                description=getattr(path_item, "description", None),
            )
        )

    return endpoints


def _convert_webhooks(spec: OAS3, context: _ConversionContext) -> list[Webhook]:
    raw_webhooks = typing.cast("dict[str, typing.Any]", getattr(spec, "webhooks", None) or {})
    webhooks: list[Webhook] = []

    for name, path_item in raw_webhooks.items():
        operations = _convert_path_item(name, path_item, context, is_webhook=True)

        if not operations:
            continue

        webhooks.append(
            Webhook(
                name=name,
                operations=operations,
                description=getattr(path_item, "description", None),
            )
        )

    return webhooks


def _convert_security_schemes(spec: OAS3, /) -> list[SecurityScheme]:
    components = getattr(spec, "components", None)

    if components is None:
        return []

    raw_schemes = typing.cast("dict[str, typing.Any]", getattr(components, "securitySchemes", None) or {})
    result: list[SecurityScheme] = []

    for scheme_name, raw in raw_schemes.items():
        if getattr(raw, "ref", None):
            continue

        scheme_type = getattr(raw, "type", None)
        description = getattr(raw, "description", None)

        if scheme_type == "apiKey":
            param_name = getattr(raw, "name", None) or scheme_name
            location = getattr(raw, "in_", None) or "header"
            result.append(ApiKeyScheme(name=scheme_name, param_name=param_name, location=location, description=description))

        elif scheme_type == "http":
            http_scheme = getattr(raw, "scheme", None) or "bearer"
            bearer_format = getattr(raw, "bearerFormat", None)
            result.append(HttpScheme(name=scheme_name, scheme=http_scheme, bearer_format=bearer_format, description=description))

        elif scheme_type == "oauth2":
            raw_flows = getattr(raw, "flows", None)
            result.append(
                OAuth2Scheme(
                    name=scheme_name,
                    description=description,
                    implicit=_convert_oauth2_flow(getattr(raw_flows, "implicit", None)) if raw_flows else None,
                    password=_convert_oauth2_flow(getattr(raw_flows, "password", None)) if raw_flows else None,
                    client_credentials=_convert_oauth2_flow(getattr(raw_flows, "clientCredentials", None)) if raw_flows else None,
                    authorization_code=_convert_oauth2_flow(getattr(raw_flows, "authorizationCode", None)) if raw_flows else None,
                )
            )

        elif scheme_type == "openIdConnect":
            url = getattr(raw, "openIdConnectUrl", "") or ""
            result.append(OpenIdConnectScheme(name=scheme_name, open_id_connect_url=url, description=description))

    return result


def _convert_oauth2_flow(raw: typing.Any, /) -> OAuth2Flow | None:
    if raw is None:
        return None

    raw_scopes = typing.cast("dict[str, str]", getattr(raw, "scopes", None) or {})
    return OAuth2Flow(
        authorization_url=getattr(raw, "authorizationUrl", None),
        token_url=getattr(raw, "tokenUrl", None),
        refresh_url=getattr(raw, "refreshUrl", None),
        scopes=raw_scopes,
    )


def _convert_path_item(
    path: str,
    path_item: typing.Any,
    context: _ConversionContext,
    *,
    is_webhook: bool = False,
) -> list[Operation]:
    operations: list[Operation] = []
    path_level_parameters = typing.cast("list[typing.Any]", getattr(path_item, "parameters", None) or [])

    for method in _OPERATION_FIELDS:
        raw_operation = getattr(path_item, method, None)

        if raw_operation is None:
            continue

        operations.append(_convert_operation(method, path, raw_operation, path_level_parameters, context, is_webhook=is_webhook))

    additional_ops = typing.cast("dict[str, typing.Any]", getattr(path_item, "additionalOperations", None) or {})

    for method, raw_operation in additional_ops.items():
        operations.append(_convert_operation(method.lower(), path, raw_operation, path_level_parameters, context, is_webhook=is_webhook))

    return operations


def _convert_operation(
    method: str,
    path: str,
    operation: typing.Any,
    path_level_parameters: list[typing.Any],
    context: _ConversionContext,
    *,
    is_webhook: bool = False,
) -> Operation:
    operation_level_parameters = typing.cast("list[typing.Any]", getattr(operation, "parameters", None) or [])
    parameters = _merge_parameters(path_level_parameters, operation_level_parameters, context)

    responses: list[Response] = []
    operation_id = getattr(operation, "operationId", None)

    for status_code, raw_response in (getattr(operation, "responses", None) or {}).items():
        response_hint = None
        is_error = False

        try:
            status_int = int(status_code)
            is_error = status_int >= 300
        except ValueError:
            pass

        if operation_id:
            base_name = _to_pascal_case_simple(operation_id)

            for prefix in ("Get", "Post", "Put", "Patch", "Delete"):
                if base_name.startswith(prefix):
                    base_name = base_name[len(prefix) :]
                    break

            if is_error:
                response_hint = base_name + "Error" if not base_name.endswith("Error") else base_name
            else:
                response_hint = base_name + "Response" if not base_name.endswith("Response") else base_name
        else:
            path_parts = [p for p in path.strip("/").split("/") if p and not p.startswith("{")]
            path_params = [p.strip("{}") for p in path.strip("/").split("/") if p.startswith("{")]

            if path_parts:
                base_name = (
                    "".join(_to_pascal_case_simple(p) for p in path_parts[-2:])
                    if len(path_parts) >= 2
                    else _to_pascal_case_simple(path_parts[-1])
                )

                if path_params and method.upper() == "GET":
                    base_name = base_name + "ById"

                if method.upper() != "GET":
                    method_prefix_map = {
                        "POST": "Create",
                        "PUT": "Replace",
                        "PATCH": "Update",
                        "DELETE": "Delete",
                    }
                    prefix = method_prefix_map.get(method.upper(), _to_pascal_case_simple(method))
                    base_name = prefix + base_name

                if is_error:
                    response_hint = base_name + "Error" if not base_name.endswith("Error") else base_name
                else:
                    response_hint = base_name + "Response" if not base_name.endswith("Response") else base_name

        converted_response = _convert_response(status_code, raw_response, context, name_hint=response_hint)

        if converted_response is not None:
            responses.append(converted_response)

    request_body_hint = None

    if operation_id:
        base_name = _to_pascal_case_simple(operation_id)

        for prefix in ("Get", "Post", "Put", "Patch", "Delete"):
            if base_name.startswith(prefix):
                base_name = base_name[len(prefix) :]
                break

        request_body_hint = base_name + "Request" if not base_name.endswith("Request") else base_name
    else:
        path_parts = [p for p in path.strip("/").split("/") if p and not p.startswith("{")]

        if path_parts:
            base_name = "".join(_to_pascal_case_simple(p) for p in path_parts[-2:]) if len(path_parts) >= 2 else _to_pascal_case_simple(path_parts[-1])

            if method.upper() != "GET":
                method_prefix_map = {
                    "POST": "Create",
                    "PUT": "Replace",
                    "PATCH": "Update",
                    "DELETE": "Delete",
                }
                prefix = method_prefix_map.get(method.upper(), _to_pascal_case_simple(method))
                base_name = prefix + base_name

            request_body_hint = base_name + "Request" if not base_name.endswith("Request") else base_name

    request_body = _convert_request_body(getattr(operation, "requestBody", None), context, name_hint=request_body_hint)

    security_requirements: list[dict[str, list[str]]] = []
    raw_security = getattr(operation, "security", None)

    if raw_security is not None:
        for requirement in raw_security:
            security_requirements.append(dict(requirement))

    return Operation(
        method=method.lower(),
        path=path,
        operation_id=operation_id,
        summary=getattr(operation, "summary", None),
        description=getattr(operation, "description", None),
        tags=list(getattr(operation, "tags", None) or []),
        parameters=parameters,
        request_body=request_body,
        responses=responses,
        deprecated=bool(getattr(operation, "deprecated", False)),
        security_requirements=security_requirements,
    )


def _merge_parameters(
    path_level_parameters: list[typing.Any],
    operation_level_parameters: list[typing.Any],
    context: _ConversionContext,
) -> list[Parameter]:
    merged: list[Parameter] = []
    index_by_key: dict[tuple[str, str], int] = {}

    for raw_parameter in [*path_level_parameters, *operation_level_parameters]:
        parameter = _convert_parameter(raw_parameter, context)

        if parameter is None:
            continue

        key = (parameter.name, parameter.location)
        existing_index = index_by_key.get(key)

        if existing_index is None:
            index_by_key[key] = len(merged)
            merged.append(parameter)
            continue

        merged[existing_index] = parameter

    return merged


def _convert_parameter(parameter: typing.Any, context: _ConversionContext) -> Parameter | None:
    if parameter is None or getattr(parameter, "ref", None):
        return None

    name = getattr(parameter, "name", None)
    location = getattr(parameter, "in_", None)

    if not name or not location:
        return None

    param_hint = _to_pascal_case_simple(name) if name else None
    type_ref = _to_type_ref(getattr(parameter, "schema", None), context, name_hint=param_hint)

    if isinstance(type_ref, AnyType):
        media_type = _pick_primary_media_type(getattr(parameter, "content", None) or {})

        if media_type is not None:
            _, media = media_type
            type_ref = _to_type_ref(getattr(media, "schema", None), context, name_hint=param_hint)

    required = bool(getattr(parameter, "required", False))
    if location == "path":
        required = True

    return Parameter(
        name=name,
        location=location,
        type=type_ref,
        required=required,
        description=getattr(parameter, "description", None),
        deprecated=bool(getattr(parameter, "deprecated", False)),
    )


def _convert_request_body(request_body: typing.Any, context: _ConversionContext, name_hint: str | None = None) -> RequestBody | None:
    if request_body is None or getattr(request_body, "ref", None):
        return None

    media_type = _pick_primary_media_type(getattr(request_body, "content", None) or {})
    if media_type is None:
        return None

    content_type, media = media_type
    return RequestBody(
        content_type=content_type,
        type=_to_type_ref(getattr(media, "schema", None), context, name_hint=name_hint),
        required=bool(getattr(request_body, "required", False)),
        description=getattr(request_body, "description", None),
    )


def _convert_response(status_code: str, response: typing.Any, context: _ConversionContext, name_hint: str | None = None) -> Response | None:
    if response is None:
        return None

    ref = getattr(response, "ref", None)
    if ref and ref.startswith(_RESPONSE_REF_PREFIX):
        response_name = ref[len(_RESPONSE_REF_PREFIX) :]
        if response_name in context.named_responses:
            # Add status_code to existing NamedResponse
            named_response = context.named_responses[response_name]
            if str(status_code) not in named_response.status_codes:
                named_response.status_codes.append(str(status_code))

            return Response(
                status_code=str(status_code),
                description=named_response.description,
                content=named_response.content,
                component_response_ref=response_name,
            )
        return None

    if ref:
        return None

    response_description = getattr(response, "description", None)
    content: dict[str, TypeRef] = {}
    for content_type, media in (getattr(response, "content", None) or {}).items():
        content[content_type] = _to_type_ref(
            getattr(media, "schema", None),
            context,
            name_hint=name_hint,
            field_description=response_description,
        )

    return Response(
        status_code=str(status_code),
        description=response_description,
        content=content,
    )


def _pick_primary_media_type(content: dict[str, typing.Any]) -> tuple[str, typing.Any] | None:
    if not content:
        return None

    if "application/json" in content:
        return ("application/json", content["application/json"])

    first_content_type = next(iter(content))
    return (first_content_type, content[first_content_type])


def _to_pascal_case_simple(name: str) -> str:
    parts = _PASCAL_SPLIT_RE.split(name)
    return "".join(p.capitalize() for p in parts if p)


def _compute_model_signature(schema: typing.Any) -> str:
    properties = typing.cast("dict[str, typing.Any]", getattr(schema, "properties", None) or {})
    required = set(getattr(schema, "required", None) or [])
    field_sigs: list[str] = []

    for name in sorted(properties.keys()):
        prop = properties[name]
        field_type = getattr(prop, "type", None) or "any"
        field_format = getattr(prop, "format", None) or ""
        is_required = name in required
        ref = getattr(prop, "ref", None) or ""
        nullable = getattr(prop, "nullable", False)

        nested_props = ""
        if field_type == "object" or getattr(prop, "properties", None):
            nested_props = _compute_model_signature(prop)

        field_sigs.append(f"{name}:{field_type}:{field_format}:{is_required}:{ref}:{nullable}:{nested_props}")

    return "|".join(field_sigs)


def _unique_inline_enum_name(base: str, context: _ConversionContext) -> str:
    all_taken = context.enum_names | context.model_names
    name = base
    counter = 2

    while name in all_taken or name in context.inline_enums or name in context.inline_models:
        name = f"{base}{counter}"
        counter += 1

    return name


def _unique_inline_model_name(base: str, context: _ConversionContext) -> str:
    all_taken = context.enum_names | context.model_names
    name = base
    counter = 2

    while name in all_taken or name in context.inline_enums or name in context.inline_models:
        name = f"{base}{counter}"
        counter += 1

    return name


def _extract_constraints(schema: typing.Any) -> Constraints | None:
    minimum = getattr(schema, "minimum", None)
    maximum = getattr(schema, "maximum", None)
    exc_min = getattr(schema, "exclusiveMinimum", None)
    exc_max = getattr(schema, "exclusiveMaximum", None)

    gt: float | None = None
    ge: float | None = None
    lt: float | None = None
    le: float | None = None

    if isinstance(exc_min, bool):
        if minimum is not None:
            gt, ge = (minimum, None) if exc_min else (None, minimum)
    else:
        if exc_min is not None:
            gt = exc_min

        if minimum is not None:
            ge = minimum

    if isinstance(exc_max, bool):
        if maximum is not None:
            lt, le = (maximum, None) if exc_max else (None, maximum)
    else:
        if exc_max is not None:
            lt = exc_max

        if maximum is not None:
            le = maximum

    c = Constraints(
        gt=gt,
        ge=ge,
        lt=lt,
        le=le,
        multiple_of=getattr(schema, "multipleOf", None),
        pattern=getattr(schema, "pattern", None),
        min_length=getattr(schema, "minLength", None) or getattr(schema, "minItems", None),
        max_length=getattr(schema, "maxLength", None) or getattr(schema, "maxItems", None),
    )
    return None if c.is_empty() else c


def _numeric_examples(schema: typing.Any) -> list[int | float]:
    values: list[object] = []

    example = getattr(schema, "example", msgspec.UNSET)
    if example is not msgspec.UNSET and example is not None:
        values.append(example)

    examples = getattr(schema, "examples", None)

    if isinstance(examples, list):
        values.extend(examples)
    elif isinstance(examples, dict):
        for ex in examples.values():
            val = getattr(ex, "value", None)
            if val is not None:
                values.append(val)

    return [v for v in values if isinstance(v, (int, float))]


def _number_without_format_is_float(schema: typing.Any) -> bool:
    numerics = _numeric_examples(schema)

    if numerics:
        return all(isinstance(v, float) for v in numerics)

    bounds = [
        getattr(schema, "minimum", None),
        getattr(schema, "maximum", None),
        getattr(schema, "exclusiveMinimum", None),
        getattr(schema, "exclusiveMaximum", None),
    ]

    return any(isinstance(bound, float) and not bound.is_integer() for bound in bounds)


def _to_type_ref(schema: typing.Any, context: _ConversionContext, name_hint: str | None = None, field_description: str | None = None) -> TypeRef:
    if schema is None or isinstance(schema, bool):
        return AnyType()

    ref = getattr(schema, "ref", None)

    if isinstance(ref, str):
        ref_name = _extract_schema_ref_name(ref)

        if ref_name:
            if ref_name in context.enum_names:
                return EnumRef(name=ref_name)

            if ref_name in context.model_names:
                return ModelRef(name=ref_name)

            return AnyType()

        return AnyType()

    if name_hint and _schema_is_enum(schema):
        nullable, _ = _extract_nullable_type(schema)
        enum_name = _unique_inline_enum_name(name_hint, context)
        enum_node = _convert_enum(enum_name, schema)
        # Use field description if schema doesn't have one
        if field_description and not enum_node.description:
            enum_node = Enum(name=enum_node.name, values=enum_node.values, description=field_description)
        context.inline_enums[enum_name] = enum_node
        context.enum_names.add(enum_name)
        return EnumRef(name=enum_name, nullable=nullable)

    nullable, type_name = _extract_nullable_type(schema)
    constraints = _extract_constraints(schema)
    union_variants: list[TypeRef] = []

    for keyword in ("oneOf", "anyOf", "allOf"):
        variants = typing.cast("list[typing.Any]", getattr(schema, keyword, None) or [])
        for variant in variants:
            union_variants.append(_to_type_ref(variant, context, name_hint=name_hint))

    if union_variants:
        return UnionType(variants=union_variants, nullable=nullable)

    if type_name == "array":
        item_schema = getattr(schema, "items", None)
        item_type = _to_type_ref(item_schema, context, name_hint=name_hint)
        return ArrayType(item_type=item_type, nullable=nullable, constraints=constraints)

    if type_name == "object" or getattr(schema, "properties", None) is not None or getattr(schema, "additionalProperties", None) is not None:
        properties = getattr(schema, "properties", None)

        if properties and name_hint:
            signature = _compute_model_signature(schema)

            if signature in context.model_signatures:
                canonical_name = context.model_signatures[signature]
                return ModelRef(name=canonical_name, nullable=nullable)

            model_name = _unique_inline_model_name(name_hint, context)
            inline_model = _convert_model(model_name, schema, context)
            # Use field description if schema doesn't have one
            if field_description and not inline_model.description:
                inline_model = Model(name=inline_model.name, fields=inline_model.fields, description=field_description)
            context.inline_models[model_name] = inline_model
            context.model_names.add(model_name)
            context.model_signatures[signature] = model_name
            return ModelRef(name=model_name, nullable=nullable)

        additional = getattr(schema, "additionalProperties", None)

        if additional is None or additional is True or additional is False:
            return MapType(value_type=AnyType(), nullable=nullable)

        return MapType(value_type=_to_type_ref(additional, context, name_hint=name_hint), nullable=nullable)

    if type_name in ("integer", "string"):
        return _TYPE_MAP[type_name](
            format=getattr(schema, "format", None),
            nullable=nullable,
            constraints=constraints,
        )

    if type_name == "number":
        fmt = getattr(schema, "format", None)

        if fmt is None:
            if _number_without_format_is_float(schema):
                return NumberType(nullable=nullable, constraints=constraints)

            return IntegerType(nullable=nullable, constraints=constraints)

        return NumberType(format=fmt, nullable=nullable, constraints=constraints)

    return BooleanType(nullable=nullable) if type_name == "boolean" else AnyType(nullable=nullable)


def _extract_nullable_type(schema: typing.Any) -> tuple[bool, str | None]:
    nullable = bool(getattr(schema, "nullable", False))
    raw_type = getattr(schema, "type", None)

    if isinstance(raw_type, list):
        non_null_types: list[str] = []

        for value in raw_type:
            if value == "null":
                nullable = True
                continue

            if isinstance(value, str):
                non_null_types.append(value)

        return (nullable, non_null_types[0] if non_null_types else None)

    if isinstance(raw_type, str):
        return (nullable, raw_type)

    return (nullable, None)


def _schema_is_enum(schema: typing.Any) -> bool:
    if getattr(schema, "ref", None):
        return False

    values = getattr(schema, "enum", None)

    if not values:
        return False

    return all(isinstance(value, (str, int, float, bool)) for value in values)


def _schema_is_model(schema: typing.Any, /) -> bool:
    if getattr(schema, "ref", None) or _schema_is_enum(schema):
        return False

    return bool(_extract_nullable_type(schema)[0] == "object" or getattr(schema, "properties", None))


def _to_enum_member_name(value: typing.Any, index: int) -> str:
    candidate = re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_").upper() if isinstance(value, str) else ""

    if not candidate:
        candidate = f"VALUE_{index}"

    if candidate[0].isdigit():
        candidate = f"VALUE_{candidate}"

    return candidate


def _extract_schema_ref_name(ref: str) -> str | None:
    if ref.startswith(_SCHEMA_REF_PREFIX):
        return ref[len(_SCHEMA_REF_PREFIX) :]
    return None


__all__ = (
    "OAS3",
    "from_openapi",
    "from_openapi_30x",
    "from_openapi_31x",
    "from_openapi_32x",
    "from_openapi_document",
)
