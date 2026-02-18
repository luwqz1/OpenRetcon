from __future__ import annotations

import re
import typing

import msgspec

from retcon.openapi.parser import (
    OpenAPIDocument,
    OpenAPIObject,
    OpenAPIParseError,
    decode_openapi_document,
)
from retcon.openapi.v3 import oas300, oas310, oas320
from retcon.schema.enums import Enum, EnumValue
from retcon.schema.errors import ConversionError
from retcon.schema.graph import APISchema
from retcon.schema.objects import Field, Model
from retcon.schema.paths import Endpoint, Operation, Parameter, RequestBody, Response
from retcon.schema.types import (
    AnyType,
    ArrayType,
    BooleanType,
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

_OPERATION_FIELDS: typing.Final = ("get", "put", "post", "delete", "options", "head", "patch", "trace", "query")
_PATH_OPERATIONS_PREFIX: typing.Final = "#/paths/"
_SCHEMA_REF_PREFIX: typing.Final = "#/components/schemas/"
_TYPE_MAP: typing.Final = {
    "string": StringType,
    "integer": IntegerType,
    "number": NumberType,
    "boolean": BooleanType,
    "array": ArrayType,
    "object": MapType,
}


class _ConversionContext(msgspec.Struct, kw_only=True):
    enum_names: set[str]
    model_names: set[str]


def from_openapi_document(document: OpenAPIDocument) -> APISchema:
    """Decode and convert raw OpenAPI document into :class:`APISchema`."""
    try:
        spec = decode_openapi_document(document)
    except OpenAPIParseError as exc:
        raise ConversionError(str(exc)) from exc
    return from_openapi(spec)


def from_openapi(spec: OpenAPIObject) -> APISchema:
    """Convert a typed OpenAPI model into :class:`APISchema`."""
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
    enum_names = {name for name, schema in schemas.items() if _schema_is_enum(schema)}
    model_names = {name for name, schema in schemas.items() if _schema_is_model(schema) and name not in enum_names}
    context = _ConversionContext(enum_names=enum_names, model_names=model_names)

    api_schema = APISchema(
        title=spec.info.title,
        version=spec.info.version,
        description=getattr(spec.info, "description", None),
    )

    for enum_name in sorted(enum_names):
        api_schema.enums.append(_convert_enum(enum_name, schemas[enum_name]))

    for model_name in sorted(model_names):
        api_schema.models.append(_convert_model(model_name, schemas[model_name], context))

    api_schema.endpoints.extend(_convert_paths(spec, context))
    api_schema.webhooks.extend(_convert_webhooks(spec, context))
    return api_schema


def _extract_component_schemas(
    spec: oas300.OpenAPI | oas310.OpenAPI | oas320.OpenAPI,
) -> dict[str, typing.Any]:
    components = getattr(spec, "components", None)
    if components is None:
        return {}
    schemas = getattr(components, "schemas", None)
    if not schemas:
        return {}
    return typing.cast(dict[str, typing.Any], schemas)


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
    properties = typing.cast(dict[str, typing.Any], getattr(schema, "properties", None) or {})
    required = set(getattr(schema, "required", None) or [])
    fields: list[Field] = []

    for prop_name, prop_schema in properties.items():
        field_default = getattr(prop_schema, "default", msgspec.UNSET)
        field_kwargs: dict[str, typing.Any] = {
            "name": prop_name,
            "type": _to_type_ref(prop_schema, context),
            "required": prop_name in required,
            "description": getattr(prop_schema, "description", None),
        }
        if field_default is not msgspec.UNSET and field_default is not None:
            field_kwargs["default"] = field_default
        fields.append(Field(**field_kwargs))

    return Model(
        name=name,
        fields=fields,
        description=getattr(schema, "description", None),
    )


def _convert_paths(
    spec: oas300.OpenAPI | oas310.OpenAPI | oas320.OpenAPI,
    context: _ConversionContext,
) -> list[Endpoint]:
    path_items = typing.cast(dict[str, typing.Any], getattr(spec, "paths", None) or {})
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


def _convert_webhooks(
    spec: oas300.OpenAPI | oas310.OpenAPI | oas320.OpenAPI,
    context: _ConversionContext,
) -> list[Webhook]:
    raw_webhooks = typing.cast(dict[str, typing.Any], getattr(spec, "webhooks", None) or {})
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


def _convert_path_item(
    path: str,
    path_item: typing.Any,
    context: _ConversionContext,
    *,
    is_webhook: bool,
) -> list[Operation]:
    operations: list[Operation] = []
    path_level_parameters = typing.cast(list[typing.Any], getattr(path_item, "parameters", None) or [])

    for method in _OPERATION_FIELDS:
        raw_operation = getattr(path_item, method, None)
        if raw_operation is None:
            continue
        operations.append(_convert_operation(method, path, raw_operation, path_level_parameters, context, is_webhook=is_webhook))

    additional_ops = typing.cast(dict[str, typing.Any], getattr(path_item, "additionalOperations", None) or {})
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
    is_webhook: bool,
) -> Operation:
    operation_level_parameters = typing.cast(list[typing.Any], getattr(operation, "parameters", None) or [])
    parameters = _merge_parameters(path_level_parameters, operation_level_parameters, context)

    responses: list[Response] = []
    for status_code, raw_response in (getattr(operation, "responses", None) or {}).items():
        converted_response = _convert_response(status_code, raw_response, context)
        if converted_response is not None:
            responses.append(converted_response)

    request_body = _convert_request_body(getattr(operation, "requestBody", None), context)
    operation_id = getattr(operation, "operationId", None) or _build_default_operation_id(method, path, is_webhook=is_webhook)

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

    type_ref = _to_type_ref(getattr(parameter, "schema", None), context)
    if isinstance(type_ref, AnyType):
        media_type = _pick_primary_media_type(getattr(parameter, "content", None) or {})
        if media_type is not None:
            _, media = media_type
            type_ref = _to_type_ref(getattr(media, "schema", None), context)

    required = bool(getattr(parameter, "required", False))
    if location == "path":
        required = True

    return Parameter(
        name=name,
        location=location,
        type=type_ref,
        required=required,
        description=getattr(parameter, "description", None),
    )


def _convert_request_body(request_body: typing.Any, context: _ConversionContext) -> RequestBody | None:
    if request_body is None or getattr(request_body, "ref", None):
        return None

    media_type = _pick_primary_media_type(getattr(request_body, "content", None) or {})
    if media_type is None:
        return None

    content_type, media = media_type
    return RequestBody(
        content_type=content_type,
        type=_to_type_ref(getattr(media, "schema", None), context),
        required=bool(getattr(request_body, "required", False)),
        description=getattr(request_body, "description", None),
    )


def _convert_response(status_code: str, response: typing.Any, context: _ConversionContext) -> Response | None:
    if response is None or getattr(response, "ref", None):
        return None

    content: dict[str, TypeRef] = {}
    for content_type, media in (getattr(response, "content", None) or {}).items():
        content[content_type] = _to_type_ref(getattr(media, "schema", None), context)

    return Response(
        status_code=str(status_code),
        description=getattr(response, "description", None),
        content=content,
    )


def _pick_primary_media_type(content: dict[str, typing.Any]) -> tuple[str, typing.Any] | None:
    if not content:
        return None

    if "application/json" in content:
        return ("application/json", content["application/json"])

    first_content_type = next(iter(content))
    return (first_content_type, content[first_content_type])


def _to_type_ref(schema: typing.Any, context: _ConversionContext) -> TypeRef:
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

    nullable, type_name = _extract_nullable_type(schema)

    union_variants: list[TypeRef] = []

    for keyword in ("oneOf", "anyOf", "allOf"):
        variants = typing.cast(list[typing.Any], getattr(schema, keyword, None) or [])
        for variant in variants:
            union_variants.append(_to_type_ref(variant, context))

    if union_variants:
        return UnionType(variants=union_variants, nullable=nullable)

    if type_name == "array":
        item_schema = getattr(schema, "items", None)
        item_type = _to_type_ref(item_schema, context)
        return ArrayType(item_type=item_type, nullable=nullable)

    if type_name == "object" or getattr(schema, "properties", None) is not None or getattr(schema, "additionalProperties", None) is not None:
        additional = getattr(schema, "additionalProperties", None)
        if additional is None or additional is True or additional is False:
            return MapType(value_type=AnyType(), nullable=nullable)
        return MapType(value_type=_to_type_ref(additional, context), nullable=nullable)

    if type_name in ("integer", "number", "string"):
        return _TYPE_MAP[type_name](format=getattr(schema, "format", None), nullable=nullable)

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

    if _extract_nullable_type(schema)[0] == "object" or getattr(schema, "properties", None):
        return True

    return False


def _to_enum_member_name(value: typing.Any, index: int) -> str:
    if isinstance(value, str):
        candidate = re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_").upper()
    else:
        candidate = ""

    if not candidate:
        candidate = f"VALUE_{index}"

    if candidate[0].isdigit():
        candidate = f"VALUE_{candidate}"

    return candidate


def _extract_schema_ref_name(ref: str) -> str | None:
    if ref.startswith(_SCHEMA_REF_PREFIX):
        return ref[len(_SCHEMA_REF_PREFIX) :]
    return None


def _build_default_operation_id(method: str, path: str, *, is_webhook: bool) -> str:
    prefix = "webhook" if is_webhook else "op"
    normalized_path = path

    if normalized_path.startswith(_PATH_OPERATIONS_PREFIX):
        normalized_path = normalized_path[len(_PATH_OPERATIONS_PREFIX) :]

    base = f"{prefix}_{method}_{normalized_path}"
    base = base.replace("{", "").replace("}", "")
    base = re.sub(r"[^0-9A-Za-z_]+", "_", base)
    return base.strip("_").lower()


__all__ = (
    "from_openapi",
    "from_openapi_document",
    "from_openapi_30x",
    "from_openapi_31x",
    "from_openapi_32x",
)
