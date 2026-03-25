from __future__ import annotations

import keyword
import re
import typing
from collections import defaultdict
from http import HTTPStatus

import msgspec

from retcon.generators.abc import ABCGenerator
from retcon.schema.enums import Enum as SchemaEnum
from retcon.schema.graph import APISchema
from retcon.schema.objects import Field, Model
from retcon.schema.paths import Endpoint, NamedResponse, Operation, Parameter, RequestBody, Response
from retcon.schema.security import ApiKeyScheme, HttpScheme, SecurityScheme
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

_CAMEL_RE: typing.Final = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|[-\s/{}]+")
_PYTHON_BUILTINS: typing.Final = frozenset(
    {
        "list",
        "dict",
        "set",
        "tuple",
        "str",
        "int",
        "float",
        "bool",
        "bytes",
        "bytearray",
        "type",
        "object",
        "property",
        "date",
        "time",
        "datetime",
        "timedelta",
    },
)


def _raw_string(s: str) -> str:
    if "\\" not in s and '"' not in s:
        return f'r"{s}"'

    if "\\" not in s and "'" not in s:
        return f"r'{s}'"

    return repr(s)


def _to_snake_case(name: str) -> str:
    s = _CAMEL_RE.sub("_", name)
    s = re.sub(r"[^a-zA-Z0-9_]", "", s)
    s = re.sub(r"_+", "_", s)
    return s.strip("_").lower()


def _to_pascal_case(name: str) -> str:
    return "".join(part.capitalize() for part in _to_snake_case(name).split("_"))


def _resolve_method_name_conflicts(
    operations: list[Operation],
    base_path: str,
) -> dict[int, str]:
    def method_prefix(op: Operation) -> str:
        prefix_map = {
            "get": "get",
            "post": "create",
            "put": "replace",
            "patch": "update",
            "delete": "delete",
        }
        return prefix_map.get(op.method.lower(), op.method.lower())

    def get_path_pattern(op: Operation) -> str:
        path = op.path

        if base_path and path.startswith(base_path):
            path = path[len(base_path) :]

        parts = [p for p in path.strip("/").split("/") if p and not p.startswith("{")]
        return "/" + "/".join(parts) if parts else "/"

    def get_first_static_segment(op: Operation) -> str | None:
        path = op.path

        if base_path and path.startswith(base_path):
            path = path[len(base_path) :]

        for part in path.strip("/").split("/"):
            if part and not part.startswith("{"):
                return _to_snake_case(part)

        return None

    initial_names: dict[int, str] = {}
    has_operation_id: dict[int, bool] = {}  # Track which operations have explicit operationId

    for op in operations:
        name = _operation_to_method_name(op, base_path)
        initial_names[id(op)] = name
        has_operation_id[id(op)] = op.operation_id is not None

    for op in operations:
        if has_operation_id[id(op)]:
            continue

        name = initial_names[id(op)]
        if name in _PYTHON_BUILTINS:
            initial_names[id(op)] = f"{method_prefix(op)}_{name}"

    for op in operations:
        if has_operation_id[id(op)]:
            continue

        path = op.path
        if base_path and path.startswith(base_path):
            path = path[len(base_path) :]

        parts = [p for p in path.strip("/").split("/") if p]
        static_parts = [p for p in parts if not p.startswith("{")]
        param_parts = [p.strip("{}") for p in parts if p.startswith("{")]

        if len(static_parts) == 1 and len(param_parts) > 0:
            segment = static_parts[0]
            first_static_idx = next((i for i, p in enumerate(parts) if not p.startswith("{")), None)
            first_param_idx = next((i for i, p in enumerate(parts) if p.startswith("{")), None)

            if first_static_idx is not None and first_param_idx is not None and first_static_idx < first_param_idx:
                pattern_without_params = f"/{segment}"
                has_route_without_params = any(
                    get_path_pattern(o) == pattern_without_params and len([p for p in o.path.split("/") if p.startswith("{")]) == 0
                    for o in operations
                    if o != op
                )

                if not has_route_without_params:
                    simple_name = method_prefix(op)

                    if simple_name not in _PYTHON_BUILTINS:
                        initial_names[id(op)] = simple_name


    name_groups: dict[str, list[Operation]] = {}
    for op in operations:
        name = initial_names[id(op)]

        if name not in name_groups:
            name_groups[name] = []

        name_groups[name].append(op)

    final_names: dict[int, str] = {}

    for name, ops_list in name_groups.items():
        if len(ops_list) == 1:
            final_names[id(ops_list[0])] = name
            continue

        methods = {op.method.lower() for op in ops_list}

        route_prefixes = {id(op): get_first_static_segment(op) for op in ops_list}
        prefixed_names = {
            id(op): f"{route_prefixes[id(op)]}_{name}"
            for op in ops_list
            if route_prefixes[id(op)]
        }
        if len(prefixed_names) == len(ops_list) and len(set(prefixed_names.values())) == len(ops_list):
            for op in ops_list:
                final_names[id(op)] = prefixed_names[id(op)]
            continue

        if len(methods) == len(ops_list):
            for op in ops_list:
                final_names[id(op)] = f"{method_prefix(op)}_{name}"
        else:
            for op in ops_list:
                final_names[id(op)] = f"{method_prefix(op)}_{name}"

    return final_names


def _operation_id_to_method_name(operation_id: str) -> str:
    return _to_snake_case(re.sub(r"^.*Controller_", "", operation_id))


def _operation_to_method_name(op: Operation, base_path: str = "") -> str:
    if op.operation_id and op.operation_id.isascii():
        return _operation_id_to_method_name(op.operation_id)

    path = op.path
    if base_path and path.startswith(base_path):
        path = path[len(base_path) :]

    parts = [p for p in path.strip("/").split("/") if p]
    static_parts = [p for p in parts if not p.startswith("{")]
    param_parts = [p.strip("{}") for p in parts if p.startswith("{")]

    method = op.method.lower()
    prefix_map = {
        "get": "get",
        "post": "create",
        "put": "replace",
        "patch": "update",
        "delete": "delete",
    }
    prefix = prefix_map.get(method, method)

    if not parts:
        return prefix

    if not static_parts:
        param_suffix = "_and_".join(param_parts)
        return f"{prefix}_by_{param_suffix}"

    endpoint_name = "_".join(_to_snake_case(p) for p in static_parts)
    endpoint_lower = endpoint_name.lower()

    if "bulk_update" in endpoint_lower or "bulk-update" in endpoint_lower:
        return "bulk_update"

    if "bulk_delete" in endpoint_lower or "bulk-delete" in endpoint_lower:
        return "bulk_delete"

    if "bulk_replace" in endpoint_lower or "bulk-replace" in endpoint_lower:
        return "bulk_replace"

    if len(static_parts) == 1 and static_parts[0].lower() == "id" and param_parts:
        param_suffix = "_and_".join(param_parts)
        return f"{prefix}_by_{param_suffix}"

    method_name = endpoint_name
    last_static_idx = -1

    for i, part in enumerate(parts):
        if part in static_parts:
            last_static_idx = i

    trailing_params = [p.strip("{}") for p in parts[last_static_idx + 1 :] if p.startswith("{")]

    if trailing_params:
        param_suffix = "_and_".join(trailing_params)
        return f"{method_name}_by_{param_suffix}"

    return method_name


def _is_error_status(code: str) -> bool:
    try:
        return int(code) >= 400
    except ValueError:
        return False


def _is_success_status(code: str) -> bool:
    if code == "default":
        return True

    try:
        return 200 <= int(code) < 300
    except ValueError:
        return False


def _status_to_http_status(code: str) -> str:
    try:
        status = HTTPStatus(int(code))
        return f"HTTPStatus.{status.name}"
    except ValueError:
        return f"HTTPStatus({code})"


def _status_code_to_name(code: str) -> str:
    try:
        return _to_pascal_case(HTTPStatus(int(code)).name)
    except ValueError:
        return f"Status{code}"


def _first_docstring_line(text: str | None) -> str | None:
    if not text:
        return None

    for line in text.splitlines():
        stripped = line.strip()
        if stripped:
            return stripped

    return None


def _singularize_snake_name(name: str) -> str:
    parts = name.split("_")
    result: list[str] = []

    for part in parts:
        if part.endswith("ies") and len(part) > 3:
            result.append(part[:-3] + "y")
        elif part.endswith("s") and not part.endswith("ss") and len(part) > 1:
            result.append(part[:-1])
        else:
            result.append(part)

    return "_".join(result)


def _longest_common_suffix(parts_lists: list[list[str]]) -> list[str]:
    if not parts_lists:
        return []

    suffix: list[str] = []
    for zipped in zip(*(reversed(parts) for parts in parts_lists)):
        if len(set(zipped)) == 1:
            suffix.append(zipped[0])
        else:
            break

    return list(reversed(suffix))


def _longest_common_prefix(parts_lists: list[list[str]]) -> list[str]:
    if not parts_lists:
        return []

    prefix: list[str] = []
    for zipped in zip(*parts_lists):
        if len(set(zipped)) == 1:
            prefix.append(zipped[0])
        else:
            break

    return prefix


def _longest_common_subsequence[T](left: list[T], right: list[T]) -> list[T]:
    if not left or not right:
        return []

    dp: list[list[list[T]]] = [[[] for _ in range(len(right) + 1)] for _ in range(len(left) + 1)]

    for left_idx, left_item in enumerate(left, start=1):
        for right_idx, right_item in enumerate(right, start=1):
            if left_item == right_item:
                dp[left_idx][right_idx] = [*dp[left_idx - 1][right_idx - 1], left_item]
            else:
                top = dp[left_idx - 1][right_idx]
                prev = dp[left_idx][right_idx - 1]
                dp[left_idx][right_idx] = top if len(top) >= len(prev) else prev

    return dp[-1][-1]


def _infer_status_code_from_name(name: str) -> str | None:
    name_lower = name.lower()
    status_map = {
        "badrequest": "400",
        "unauthorized": "401",
        "paymentrequired": "402",
        "forbidden": "403",
        "notfound": "404",
        "methodnotallowed": "405",
        "notacceptable": "406",
        "conflict": "409",
        "gone": "410",
        "unprocessableentity": "422",
        "toomanyrequests": "429",
        "internalservererror": "500",
        "notimplemented": "501",
        "badgateway": "502",
        "serviceunavailable": "503",
        "gatewaytimeout": "504",
    }
    return status_map.get(name_lower)


def _path_to_group(path: str) -> str:
    parts = [p for p in path.strip("/").split("/") if p and not p.startswith("{")]
    return parts[-1] if parts else "default"


def _infer_controller_base_path(operations: list[Operation]) -> str:
    if not operations:
        return "/"

    paths = [op.path for op in operations]

    if len(paths) == 1:
        parts = paths[0].split("/")
        base_parts = [p for p in parts if p and not p.startswith("{")]
        return "/" + "/".join(base_parts) if base_parts else "/"

    split = [p.split("/") for p in paths]
    common: list[str] = []

    for segments in zip(*split):
        if len(set(segments)) == 1 and not segments[0].startswith("{"):
            common.append(segments[0])
        else:
            break

    return "/" + "/".join(s for s in common if s) if common else "/"


def _relative_path(base: str, full: str) -> str:
    base = base.rstrip("/")

    if full.startswith(base):
        rel = full[len(base) :]
        return rel if rel else "/"

    return full


def _route_path_with_snake_case_params(path: str) -> str:
    return path


def _render_all(names: list[str]) -> str:
    if not names:
        return ""

    items = "\n".join(f'    "{n}",' for n in names)
    return f"\n\n__all__ = (\n{items}\n)"


def _ruff_format(code: str, filename: str) -> str:
    import shutil
    import subprocess

    if shutil.which("ruff") is None:
        return code

    basename = filename.rsplit("/", 1)[-1]

    # 1. Sort imports
    proc = subprocess.run(
        ["ruff", "check", "--select", "I", "--fix", "--stdin-filename", basename, "-"],
        input=code,
        capture_output=True,
        text=True,
    )
    if proc.returncode in (0, 1) and proc.stdout:
        code = proc.stdout

    # 2. Sort `__all__`s
    proc = subprocess.run(
        ["ruff", "check", "--select", "RUF022", "--fix", "--stdin-filename", basename, "-"],
        input=code,
        capture_output=True,
        text=True,
    )
    if proc.returncode in (0, 1) and proc.stdout:
        code = proc.stdout

    # 3. Format code
    proc = subprocess.run(
        ["ruff", "format", "--stdin-filename", basename, "-"],
        input=code,
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0 and proc.stdout:
        code = proc.stdout

    return code


class _Imports:
    """Collects Python imports for a single generated file, grouped by origin."""

    def __init__(self, *, enums_module: str | None = None) -> None:
        self._stdlib: dict[str, set[str]] = defaultdict(set)
        self._third_party: dict[str, set[str]] = defaultdict(set)
        self._local: dict[str, set[str]] = defaultdict(set)
        self._bare_stdlib: set[str] = set()
        self._bare_third_party: set[str] = set()
        self._enums_module = enums_module
        self._enums_used = False

    def stdlib(self, module: str, name: str) -> None:
        self._stdlib[module].add(name)

    def bare_stdlib(self, module: str) -> None:
        self._bare_stdlib.add(module)

    def third_party(self, module: str, name: str) -> None:
        self._third_party[module].add(name)

    def bare_third_party(self, module: str) -> None:
        self._bare_third_party.add(module)

    def local(self, module: str, name: str) -> None:
        self._local[module].add(name)

    def mark_enum_used(self) -> None:
        self._enums_used = True

    def render(self, *, future_annotations: bool = True) -> str:
        lines: list[str] = []

        if future_annotations:
            lines += ["from __future__ import annotations", ""]

        for bare, froms in (
            (self._bare_stdlib, self._stdlib),
            (self._bare_third_party, self._third_party),
            (None, self._local),
        ):
            if not bare and not froms:
                continue

            if bare:
                for module in sorted(bare):
                    lines.append(f"import {module}")

            for module in sorted(froms):
                names = ", ".join(sorted(froms[module]))
                lines.append(f"from {module} import {names}")

            if bare or froms:
                lines.append("")

        if self._enums_used and self._enums_module:
            lines.append(f"from {self._enums_module} import *")
            lines.append("")

        return "\n".join(lines).rstrip() + "\n"


class _SignatureFieldSpec(typing.NamedTuple):
    code: str
    description: str | None
    has_default: bool


class _SignatureSpec(typing.NamedTuple):
    decorators: tuple[str, ...]
    fields: tuple[_SignatureFieldSpec, ...]
    imports: _Imports


class PythonGenerator(ABCGenerator):
    """Generates Python client code using saronia (controllers) and msgspex (models).

    Parameters
    ----------
    fmt:
        When ``True`` (default), run ``ruff`` import-sorting and formatting on
        every generated file after generation.  Silently skipped when ruff is
        not installed.

    module_name:
        Name for the API module and variable. Defaults to "api".

    """

    _DATETIME_FORMATS: frozenset[str] = frozenset(("date-time",))
    _FLOAT_FORMATS: frozenset[str | None] = frozenset((None, "float", "float32", "float64", "double"))

    def __init__(self, *, fmt: bool = True, module_name: str = "api") -> None:
        self._fmt = fmt
        self._module_name = module_name
        self._parameter_dtos: dict[str, _SignatureSpec] = {}
        self._controller_response_names: frozenset[str] | None = None
        self._controller_error_names: frozenset[str] | None = None
        self._controller_classes: dict[str, str] = {}

    @staticmethod
    def _enum_signature(enum: SchemaEnum) -> tuple[tuple[tuple[str, str | int | float | bool], ...], str | None]:
        return (tuple((v.name, v.value) for v in enum.values), enum.description)

    def _canonical_enum_name(self, names: list[str], taken: set[str]) -> str:
        token_lists = [_to_snake_case(name).split("_") for name in names]
        shared_tokens = _longest_common_suffix(token_lists)
        if not shared_tokens:
            shared_tokens = _longest_common_prefix(token_lists)
        if not shared_tokens:
            shared_tokens = token_lists[0]

        base = _to_pascal_case("_".join(shared_tokens))
        if not base:
            base = names[0]

        name = base
        counter = 2
        while name in taken:
            name = f"{base}{counter}"
            counter += 1

        return name

    def _rewrite_enum_ref(self, type_ref: TypeRef, enum_name_map: dict[str, str]) -> TypeRef:
        if isinstance(type_ref, EnumRef):
            mapped = enum_name_map.get(type_ref.name, type_ref.name)
            return EnumRef(name=mapped, nullable=type_ref.nullable, constraints=type_ref.constraints)
        if isinstance(type_ref, ArrayType):
            return ArrayType(item_type=self._rewrite_enum_ref(type_ref.item_type, enum_name_map), nullable=type_ref.nullable, constraints=type_ref.constraints)
        if isinstance(type_ref, MapType):
            return MapType(value_type=self._rewrite_enum_ref(type_ref.value_type, enum_name_map), nullable=type_ref.nullable, constraints=type_ref.constraints)
        if isinstance(type_ref, UnionType):
            return UnionType(variants=[self._rewrite_enum_ref(v, enum_name_map) for v in type_ref.variants], nullable=type_ref.nullable, constraints=type_ref.constraints)
        return type_ref

    def _deduplicate_enums(self, schema: APISchema) -> APISchema:
        if not schema.enums:
            return schema

        groups: dict[tuple[tuple[tuple[str, str | int | float | bool], ...], str | None], list[SchemaEnum]] = defaultdict(list)
        for enum in schema.enums:
            groups[self._enum_signature(enum)].append(enum)

        if all(len(group) == 1 for group in groups.values()):
            return schema

        enum_name_map: dict[str, str] = {}
        deduped_enums: list[SchemaEnum] = []
        reserved_names: set[str] = {model.name for model in schema.models}

        for group in groups.values():
            if len(group) == 1:
                enum = group[0]
                deduped_enums.append(enum)
                enum_name_map[enum.name] = enum.name
                reserved_names.add(enum.name)
                continue

            canonical_name = self._canonical_enum_name([enum.name for enum in group], reserved_names)
            reserved_names.add(canonical_name)
            deduped_enums.append(SchemaEnum(name=canonical_name, values=group[0].values, description=group[0].description))
            for enum in group:
                enum_name_map[enum.name] = canonical_name

        rewritten_models: list[Model] = []
        for model in schema.models:
            rewritten_models.append(
                Model(
                    name=model.name,
                    fields=[
                        Field(
                            name=field.name,
                            type=self._rewrite_enum_ref(field.type, enum_name_map),
                            required=field.required,
                            description=field.description,
                            default=field.default,
                            deprecated=field.deprecated,
                        )
                        for field in model.fields
                    ],
                    description=model.description,
                    deprecated=model.deprecated,
                )
            )

        rewritten_endpoints: list[Endpoint] = []
        for endpoint in schema.endpoints:
            rewritten_ops: list[Operation] = []
            for op in endpoint.operations:
                rewritten_ops.append(
                    Operation(
                        method=op.method,
                        path=op.path,
                        operation_id=op.operation_id,
                        summary=op.summary,
                        description=op.description,
                        tags=op.tags,
                        parameters=[
                            Parameter(
                                name=p.name,
                                location=p.location,
                                type=self._rewrite_enum_ref(p.type, enum_name_map),
                                required=p.required,
                                description=p.description,
                                deprecated=p.deprecated,
                            )
                            for p in op.parameters
                        ],
                        request_body=(
                            None
                            if op.request_body is None
                            else RequestBody(
                                content_type=op.request_body.content_type,
                                type=self._rewrite_enum_ref(op.request_body.type, enum_name_map),
                                required=op.request_body.required,
                                description=op.request_body.description,
                            )
                        ),
                        responses=[
                            Response(
                                status_code=resp.status_code,
                                description=resp.description,
                                content={k: self._rewrite_enum_ref(v, enum_name_map) for k, v in resp.content.items()},
                                component_response_ref=resp.component_response_ref,
                            )
                            for resp in op.responses
                        ],
                        deprecated=op.deprecated,
                        security_requirements=op.security_requirements,
                    )
                )
            rewritten_endpoints.append(Endpoint(path=endpoint.path, operations=rewritten_ops, description=endpoint.description))

        rewritten_named_responses = [
            NamedResponse(
                name=nr.name,
                status_codes=nr.status_codes,
                description=nr.description,
                content={k: self._rewrite_enum_ref(v, enum_name_map) for k, v in nr.content.items()},
                schema_ref=nr.schema_ref,
            )
            for nr in schema.named_responses
        ]

        return APISchema(
            title=schema.title,
            version=schema.version,
            description=schema.description,
            servers=schema.servers,
            models=rewritten_models,
            enums=deduped_enums,
            endpoints=rewritten_endpoints,
            webhooks=schema.webhooks,
            named_responses=rewritten_named_responses,
            security_schemes=schema.security_schemes,
            custom_nodes=schema.custom_nodes,
        )

    @staticmethod
    def _field_signature(field: Field) -> tuple[object, ...]:
        default_sig = "__UNSET__" if field.default is msgspec.UNSET else repr(field.default)
        return (field.name, repr(field.type), field.required, field.description, default_sig, field.deprecated)

    def _shared_base_name(self, model_names: list[str], reserved: set[str]) -> str:
        token_lists = [_to_snake_case(name).split("_") for name in model_names]
        generic_tail = {"response", "responses", "dto", "error", "errors", "model", "models", "object", "objects", "signature"}
        generic_head = {"get", "post", "put", "patch", "delete"}

        def trim_tokens(tokens: list[str]) -> list[str]:
            trimmed = list(tokens)
            while trimmed and trimmed[-1] in generic_tail:
                trimmed.pop()
            while len(trimmed) > 1 and trimmed[-1] == "controller":
                trimmed.pop()
            while len(trimmed) > 1 and trimmed[0] in generic_head:
                trimmed.pop(0)
            return trimmed

        shared_tokens = trim_tokens(_longest_common_suffix(token_lists))
        if not shared_tokens:
            shared_tokens = trim_tokens(_longest_common_prefix(token_lists))
        if not shared_tokens:
            shared_tokens = trim_tokens(token_lists[0])
        if not shared_tokens:
            shared_tokens = token_lists[0]
        base = _to_pascal_case("_".join(shared_tokens)) + "Base"
        name = base
        counter = 2
        while name in reserved:
            name = f"{base}{counter}"
            counter += 1
        return name

    def _extract_model_bases(self, models: list[Model]) -> tuple[list[Model], list[Model], dict[str, str]]:
        if len(models) < 2:
            return [], models, {}

        prefix_groups: dict[tuple[tuple[object, ...], ...], list[str]] = defaultdict(list)
        model_by_name = {model.name: model for model in models}
        signatures_by_name = {model.name: [self._field_signature(field) for field in model.fields] for model in models}

        for model in models:
            signatures = signatures_by_name[model.name]
            for size in range(2, len(signatures) + 1):
                prefix_groups[tuple(signatures[:size])].append(model.name)

        candidates = {prefix: names for prefix, names in prefix_groups.items() if len(set(names)) >= 2}
        if not candidates:
            return [], models, {}

        chosen_by_model: dict[str, tuple[tuple[tuple[object, ...], ...], list[str]]] = {}
        for model in models:
            options = [
                (prefix, sorted(set(names)))
                for prefix, names in candidates.items()
                if model.name in names
            ]
            if not options:
                continue
            options.sort(key=lambda item: (len(item[0]), len(item[1])), reverse=True)
            chosen_by_model[model.name] = options[0]

        grouped: dict[tuple[tuple[object, ...], ...], list[str]] = defaultdict(list)
        for model_name, (prefix, names) in chosen_by_model.items():
            grouped[prefix].append(model_name)

        bases: list[Model] = []
        rewritten_models: list[Model] = []
        model_bases: dict[str, str] = {}
        reserved_names = {model.name for model in models}
        group_to_base: dict[tuple[tuple[object, ...], ...], str] = {}

        for prefix, model_names in grouped.items():
            if len(model_names) < 2:
                continue
            base_name = self._shared_base_name(sorted(model_names), reserved_names)
            reserved_names.add(base_name)
            group_to_base[prefix] = base_name
            source_model = model_by_name[model_names[0]]
            prefix_len = len(prefix)
            bases.append(Model(name=base_name, fields=source_model.fields[:prefix_len], description=None, deprecated=False))
            for model_name in model_names:
                model_bases[model_name] = base_name

        for model in models:
            base_name = model_bases.get(model.name)
            if not base_name:
                rewritten_models.append(model)
                continue
            prefix_len = len(chosen_by_model[model.name][0])
            rewritten_models.append(
                Model(
                    name=model.name,
                    fields=model.fields[prefix_len:],
                    description=model.description,
                    deprecated=model.deprecated,
                )
            )

        return bases, rewritten_models, model_bases

    @staticmethod
    def _signature_field_signature(field: _SignatureFieldSpec) -> tuple[object, ...]:
        return (field.code, field.description, field.has_default)

    def _extract_signature_bases(
        self,
        signatures: dict[str, _SignatureSpec],
    ) -> tuple[list[tuple[str, tuple[_SignatureFieldSpec, ...]]], dict[str, tuple[_SignatureFieldSpec, ...]], dict[str, str]]:
        if len(signatures) < 2:
            return [], {name: spec.fields for name, spec in signatures.items()}, {}

        signatures_by_name = {
            name: [self._signature_field_signature(field) for field in spec.fields]
            for name, spec in signatures.items()
        }
        field_lookup = {name: list(spec.fields) for name, spec in signatures.items()}
        candidates: dict[tuple[tuple[object, ...], ...], list[str]] = {}
        signature_names = list(signatures)

        def is_subsequence(
            subsequence: tuple[tuple[object, ...], ...],
            sequence: list[tuple[object, ...]],
        ) -> bool:
            seq_iter = iter(sequence)
            return all(any(item == candidate for item in seq_iter) for candidate in subsequence)

        for left_idx, left_name in enumerate(signature_names):
            for right_name in signature_names[left_idx + 1 :]:
                common = tuple(
                    _longest_common_subsequence(
                        signatures_by_name[left_name],
                        signatures_by_name[right_name],
                    )
                )
                if len(common) < 2:
                    continue

                matching = [
                    name
                    for name, field_signatures in signatures_by_name.items()
                    if is_subsequence(common, field_signatures)
                ]
                if len(matching) < 2:
                    continue

                existing = candidates.get(common)
                if existing is None or len(matching) > len(existing):
                    candidates[common] = matching

        if not candidates:
            return [], {name: spec.fields for name, spec in signatures.items()}, {}

        chosen_by_signature: dict[str, tuple[tuple[tuple[object, ...], ...], list[str]]] = {}
        for name in signatures:
            options = [
                (prefix, sorted(set(names)))
                for prefix, names in candidates.items()
                if name in names
            ]
            if not options:
                continue
            options.sort(key=lambda item: (len(item[0]), len(item[1])), reverse=True)
            chosen_by_signature[name] = options[0]

        grouped: dict[tuple[tuple[object, ...], ...], list[str]] = defaultdict(list)
        for signature_name, (prefix, _) in chosen_by_signature.items():
            grouped[prefix].append(signature_name)

        bases: list[tuple[str, tuple[_SignatureFieldSpec, ...]]] = []
        rewritten_fields: dict[str, tuple[_SignatureFieldSpec, ...]] = {}
        model_bases: dict[str, str] = {}
        chosen_sequences: dict[str, tuple[tuple[object, ...], ...]] = {}
        reserved_names = set(signatures)

        for sequence, grouped_signature_names in grouped.items():
            if len(grouped_signature_names) < 2:
                continue
            base_name = self._shared_base_name(sorted(grouped_signature_names), reserved_names)
            reserved_names.add(base_name)
            base_fields: list[_SignatureFieldSpec] = []
            source_fields = field_lookup[grouped_signature_names[0]]
            sequence_items = list(sequence)
            seq_index = 0
            for field in source_fields:
                if seq_index < len(sequence_items) and self._signature_field_signature(field) == sequence_items[seq_index]:
                    base_fields.append(field)
                    seq_index += 1
                    if seq_index == len(sequence_items):
                        break

            bases.append((base_name, tuple(base_fields)))
            for signature_name in grouped_signature_names:
                model_bases[signature_name] = base_name
                chosen_sequences[signature_name] = sequence

        for name, spec in signatures.items():
            sequence = chosen_sequences.get(name)
            if not sequence:
                rewritten_fields[name] = spec.fields
                continue

            remaining_fields: list[_SignatureFieldSpec] = []
            sequence_items = list(sequence)
            seq_index = 0
            for field in spec.fields:
                if seq_index < len(sequence_items) and self._signature_field_signature(field) == sequence_items[seq_index]:
                    seq_index += 1
                else:
                    remaining_fields.append(field)

            rewritten_fields[name] = tuple(remaining_fields)

        return bases, rewritten_fields, model_bases

    def generate(self, schema: APISchema) -> dict[str, str]:
        schema = self._deduplicate_enums(schema)
        files: dict[str, str] = {}

        self._parameter_dtos = {}
        self._controller_classes = {}

        route_prefix = self._extract_route_prefix(schema)
        response_statuses = self._collect_response_statuses(schema)  # 2xx
        error_statuses = self._collect_error_statuses(schema)  # 3xx-5xx
        response_names = set(response_statuses)
        error_names = set(error_statuses)
        inlined_request_body_names = self._collect_inlined_request_body_models(schema)

        enums = [*schema.enums]
        for node in schema.custom_nodes:
            if isinstance(node, SchemaEnum):
                enums.append(node)

        if enums:
            files["enums.py"] = self._generate_enums_file(enums)

        object_models = [
            m
            for m in schema.models
            if m.name not in response_names and m.name not in error_names and m.name not in inlined_request_body_names
        ]
        for node in schema.custom_nodes:
            if isinstance(node, Model) and node.name not in response_names and node.name not in error_names and node.name not in inlined_request_body_names:
                object_models.append(node)

        if object_models:
            files["objects.py"] = self._generate_objects_file(object_models)

        response_models = [m for m in schema.models if m.name in response_names]
        for node in schema.custom_nodes:
            if isinstance(node, Model) and node.name in response_names:
                response_models.append(node)

        response_named = []
        for nr in schema.named_responses:
            if nr.status_codes and any(_is_success_status(sc) or sc.startswith("3") for sc in nr.status_codes):
                response_named.append(nr)
            elif not nr.status_codes:
                inferred = _infer_status_code_from_name(nr.name)
                if inferred and inferred.startswith(("2", "3")):
                    response_named.append(nr)

        if response_models or response_named:
            files["responses.py"] = self._generate_responses_file(response_models, response_named)

        error_models = [m for m in schema.models if m.name in error_names]
        for node in schema.custom_nodes:
            if isinstance(node, Model) and node.name in error_names:
                error_models.append(node)

        error_named = []
        for nr in schema.named_responses:
            if nr.status_codes and any(sc.startswith(("4", "5")) for sc in nr.status_codes):
                error_named.append(nr)
            elif not nr.status_codes:
                inferred = _infer_status_code_from_name(nr.name)
                if inferred and inferred.startswith(("4", "5")):
                    error_named.append(nr)

        if error_models or error_named:
            files["errors.py"] = self._generate_errors_file(error_models, error_statuses, error_named)

        if schema.security_schemes:
            files["auth.py"] = self._generate_auth_file(schema.security_schemes)

        files[f"{self._module_name}.py"] = self._generate_api_module(route_prefix, schema.security_schemes)

        response_names_with_named = response_names.copy()
        response_names_with_named.update(nr.name for nr in response_named)
        error_names_with_named = error_names.copy()
        error_names_with_named.update(nr.name for nr in error_named)

        files.update(self._generate_controller_files(schema, frozenset(response_names_with_named), frozenset(error_names_with_named), route_prefix))

        if self._parameter_dtos:
            files["signatures.py"] = self._generate_parameters_file()

        for node in schema.custom_nodes:
            if isinstance(node, SchemaEnum | Model):
                continue

            result = self.generate_custom_node(node)

            if result is not None:
                filename = _to_snake_case(type(node).__name__) + ".py"
                files[filename] = result

        files.update(self._generate_init_files(files))

        if self._fmt:
            files = {path: _ruff_format(code, path) for path, code in files.items()}

        return files

    def _extract_route_prefix(self, schema: APISchema) -> str:
        if not schema.endpoints:
            return "/"

        paths = [endpoint.path for endpoint in schema.endpoints]
        if not paths:
            return "/"

        if len(paths) == 1:
            parts = [p for p in paths[0].split("/") if p and not p.startswith("{")]
            return "/" + "/".join(parts) if parts else "/"

        split_paths = [[p for p in path.split("/") if p] for path in paths]
        common = []

        for segments in zip(*split_paths):
            if len(set(segments)) == 1 and not segments[0].startswith("{"):
                common.append(segments[0])
            else:
                break

        return "/" + "/".join(common) if common else "/"

    def _generate_auth_file(self, security_schemes: list[SecurityScheme]) -> str:
        lines = ["from __future__ import annotations", "", "import dataclasses", "", "from saronia.security import *", ""]

        auth_classes: list[str] = []
        auth_fields: list[str] = []

        for scheme in security_schemes:
            class_name = _to_pascal_case(scheme.name)
            field_name = _to_snake_case(class_name).removeprefix("auth_").removesuffix("_auth")

            if isinstance(scheme, HttpScheme):
                if scheme.scheme.lower() == "bearer":
                    auth_classes.append(f"{class_name} = HTTPBearer")
                elif scheme.scheme.lower() == "basic":
                    auth_classes.append(f"{class_name} = HTTPBasic")
                else:
                    other_class_name = _to_pascal_case(scheme.scheme.replace("/", "_").replace("-", "_").replace(" ", "_"))
                    lines.append("")
                    lines.append("")
                    lines.append(f"class HTTP{other_class_name}(HTTPAuthorization):")
                    lines.append(f'    scheme: str = "{scheme.scheme}"')
                    auth_classes.append(f"{class_name} = {other_class_name}")

            elif isinstance(scheme, ApiKeyScheme):
                param_name = scheme.param_name

                if scheme.location == "header":
                    auth_classes.append(f'{class_name} = HeaderAPIKey["{param_name}"]')
                elif scheme.location == "query":
                    auth_classes.append(f'{class_name} = QueryAPIKey["{param_name}"]')
                elif scheme.location == "cookie":
                    auth_classes.append(f'{class_name} = CookieAPIKey["{param_name}"]')

            auth_fields.append(f"    {field_name}: {class_name} | None = None")

        lines.extend(auth_classes)
        lines.append("")
        lines.append("")
        lines.append("@dataclasses.dataclass")
        lines.append("class AuthorizationModel:")
        lines.extend(auth_fields)
        lines.append("")

        all_names = [_to_pascal_case(s.name) for s in security_schemes]
        all_names.append("AuthorizationModel")
        lines.append(_render_all(all_names))
        lines.append("")

        return "\n".join(lines)

    def _generate_api_module(self, route_prefix: str, security_schemes: list[SecurityScheme]) -> str:
        lines = ["from saronia import API", ""]

        if security_schemes:
            lines.append("from .auth import AuthorizationModel")
            lines.append("")

        if security_schemes:
            lines.append(f'{self._module_name} = API.endpoint("{route_prefix}").bind_auth(AuthorizationModel)')
        else:
            lines.append(f'{self._module_name} = API.endpoint("{route_prefix}")')

        lines.append("")
        lines.append(f'__all__ = ("{self._module_name}",)')
        lines.append("")
        return "\n".join(lines)

    def _security_requirements_to_auth_expr(self, requirements: list[dict[str, list[str]]]) -> str | None:
        if not requirements:
            return None

        if len(requirements) == 1:
            schemes = list(requirements[0].keys())
            if not schemes:
                return None

            if len(schemes) == 1:
                return _to_pascal_case(schemes[0])

            return " | ".join(_to_pascal_case(s) for s in schemes)

        parts = []
        for req in requirements:
            schemes = list(req.keys())

            if not schemes:
                continue

            if len(schemes) == 1:
                parts.append(_to_pascal_case(schemes[0]))
            else:
                parts.append(f"({' | '.join(_to_pascal_case(s) for s in schemes)})")

        if not parts:
            return None

        if len(parts) == 1:
            return parts[0]

        return " & ".join(parts)

    def _generate_init_files(self, files: dict[str, str]) -> dict[str, str]:
        result: dict[str, str] = {}

        root_modules = [p.removesuffix(".py") for p in ("enums.py", "objects.py", "responses.py", "errors.py") if p in files]
        lines = []

        for mod in root_modules:
            lines.append(f"from .{mod} import *")

        if "auth.py" in files:
            lines.append("from .auth import *")

        api_module_file = f"{self._module_name}.py"
        if api_module_file in files:
            lines.append(f"from .{self._module_name} import *")

        if any(p.startswith("controllers/") for p in files):
            lines.append("from .controllers import *")

        if lines:
            result["__init__.py"] = "\n".join(lines) + "\n"

        controller_modules = sorted(p.removeprefix("controllers/").removesuffix(".py") for p in files if p.startswith("controllers/") and p.endswith(".py"))

        if controller_modules:
            lines = []
            lines.append("import saronia")
            lines.append("")
            lines.append(f"from ..{self._module_name} import {self._module_name}")
            sorted_controllers = sorted(self._controller_classes.items(), key=lambda x: x[1])

            for class_name, module_name in sorted_controllers:
                lines.append(f"from .{module_name} import {class_name}")

            lines.append("")
            lines.append("")

            lines.append("class APIControllers:")
            lines.append("    def __init__(self, client: saronia.ABCClient) -> None:")

            for class_name, module_name in sorted_controllers:
                attr_name = module_name.removesuffix("_controller")
                lines.append(f"        self.{attr_name} = {class_name}()")

            lines.append("")
            lines.append(f"        {self._module_name}.build(client)")

            lines.append("")
            lines.append("")

            all_names = ["APIControllers"] + [class_name for class_name, _ in sorted_controllers]
            lines.append(_render_all(all_names))
            lines.append("")

            result["controllers/__init__.py"] = "\n".join(lines)

        return result

    def generate_model(self, model: Model) -> str:
        imports = _Imports()
        imports.bare_third_party("msgspex")

        body = self._render_model(model, imports)
        return imports.render() + "\n\n" + body + "\n"

    def generate_enum(self, enum: SchemaEnum) -> str:
        imports = _Imports()
        imports.bare_third_party("msgspex")

        body = self._render_enum(enum)
        return imports.render() + "\n\n" + body + "\n"

    def generate_operation(self, schema: APISchema, operation: Operation) -> str:
        imports = _Imports()
        imports.third_party("saronia", operation.method.lower())
        imports.bare_third_party("saronia")

        base = _infer_controller_base_path([operation])
        body = self._render_operation(schema, operation, base, imports)
        return imports.render() + "\n\n" + body + "\n"

    def type_to_string(self, type_ref: TypeRef) -> str:
        return self._type_str(type_ref, None)

    def _generate_enums_file(self, enums: list[SchemaEnum]) -> str:
        imports = _Imports()
        imports.bare_third_party("msgspex")

        parts = [self._render_enum(e) for e in enums]
        all_decl = _render_all([e.name for e in enums])
        return imports.render(future_annotations=False) + "\n\n" + "\n\n\n".join(parts) + all_decl + "\n"

    def _generate_objects_file(self, models: list[Model]) -> str:
        imports = _Imports(enums_module=".enums")
        imports.bare_third_party("msgspex")
        base_models, rewritten_models, model_bases = self._extract_model_bases(models)

        parts = [self._render_model(m, imports) for m in base_models]
        parts.extend(self._render_model(m, imports, base=model_bases.get(m.name, "msgspex.Model")) for m in rewritten_models)
        all_decl = _render_all([m.name for m in base_models] + [m.name for m in rewritten_models])
        return imports.render() + "\n\n" + "\n\n\n".join(parts) + all_decl + "\n"

    def _generate_parameters_file(self) -> str:
        imports = _Imports(enums_module=".enums")
        imports.bare_third_party("msgspex")
        imports.bare_third_party("saronia")

        rendered_parts: list[str] = []

        for spec in self._parameter_dtos.values():
            dto_imports = spec.imports
            for module, names in dto_imports._stdlib.items():
                for name in names:
                    imports.stdlib(module, name)

            for module, names in dto_imports._third_party.items():
                for name in names:
                    imports.third_party(module, name)

            for module in dto_imports._bare_stdlib:
                imports.bare_stdlib(module)

            for module in dto_imports._bare_third_party:
                imports.bare_third_party(module)

            if dto_imports._enums_used:
                imports.mark_enum_used()

        base_signatures, rewritten_fields, model_bases = self._extract_signature_bases(self._parameter_dtos)
        for base_name, fields in base_signatures:
            rendered_parts.append(self._render_signature_class(base_name, (), fields))

        for dto_name, spec in self._parameter_dtos.items():
            rendered_parts.append(
                self._render_signature_class(
                    dto_name,
                    spec.decorators,
                    rewritten_fields[dto_name],
                    base=model_bases.get(dto_name, "msgspex.Model"),
                )
            )

        all_decl = _render_all([name for name, _ in base_signatures] + list(self._parameter_dtos.keys()))
        return imports.render() + "\n\n" + "\n\n\n".join(rendered_parts) + all_decl + "\n"

    def _generate_responses_file(self, models: list[Model], named_responses: list[NamedResponse]) -> str:
        imports = _Imports(enums_module=".enums")
        imports.bare_third_party("msgspex")
        base_models, rewritten_models, model_bases = self._extract_model_bases(models)

        response_names = {m.name for m in rewritten_models}
        response_names.update(nr.name for nr in named_responses)

        self._controller_response_names = frozenset(response_names)
        self._controller_error_names = frozenset()

        try:
            parts = [self._render_model(m, imports) for m in base_models]
            parts.extend(self._render_model(m, imports, base=model_bases.get(m.name, "msgspex.Model")) for m in rewritten_models)
            parts.extend(self._render_named_response(nr, imports, is_error=False) for nr in named_responses)
            all_names = [m.name for m in base_models] + [m.name for m in rewritten_models] + [nr.name for nr in named_responses]
            all_decl = _render_all(all_names)
            return imports.render() + "\n\n" + "\n\n\n".join(parts) + all_decl + "\n"
        finally:
            self._controller_response_names = None
            self._controller_error_names = None

    def _generate_errors_file(
        self,
        models: list[Model],
        error_statuses: dict[str, set[str]],
        named_responses: list[NamedResponse],
    ) -> str:
        imports = _Imports(enums_module=".enums")
        imports.stdlib("http", "HTTPStatus")
        imports.bare_third_party("msgspex")
        imports.bare_third_party("saronia")
        base_models, rewritten_models, model_bases = self._extract_model_bases(models)

        error_names = {m.name for m in rewritten_models}
        error_names.update(nr.name for nr in named_responses)
        self._controller_response_names = frozenset()
        self._controller_error_names = frozenset(error_names)

        try:
            parts = [self._render_model(m, imports) for m in base_models]
            parts.extend(self._render_error_model(m, error_statuses.get(m.name, set()), imports, data_base=model_bases.get(m.name)) for m in rewritten_models)
            parts.extend(self._render_named_response(nr, imports, is_error=True) for nr in named_responses)
            all_names = [m.name for m in base_models] + [m.name for m in rewritten_models] + [nr.name for nr in named_responses]
            all_decl = _render_all(all_names)
            return imports.render() + "\n\n" + "\n\n\n".join(parts) + all_decl + "\n"
        finally:
            self._controller_response_names = None
            self._controller_error_names = None

    def _generate_controller_files(
        self,
        schema: APISchema,
        response_names: frozenset[str],
        error_names: frozenset[str],
        route_prefix: str,
    ) -> dict[str, str]:
        groups: dict[str, list[Operation]] = defaultdict(list)
        for endpoint in schema.endpoints:
            for op in endpoint.operations:
                group = op.tags[0] if op.tags else _path_to_group(endpoint.path)
                groups[group].append(op)

        files: dict[str, str] = {}

        for group, ops in groups.items():
            class_name, content = self._generate_controller_file(schema, group, ops, response_names, error_names, route_prefix)
            file_name = _to_snake_case(class_name) + ".py"
            module_name = _to_snake_case(class_name)
            path = f"controllers/{file_name}"
            files[path] = content
            self._controller_classes[class_name] = module_name

        return files

    def _generate_controller_file(
        self,
        schema: APISchema,
        group: str,
        operations: list[Operation],
        response_names: frozenset[str],
        error_names: frozenset[str],
        route_prefix: str,
    ) -> tuple[str, str]:
        imports = _Imports(enums_module="..enums")
        imports.local(f"..{self._module_name}", self._module_name)
        imports.bare_third_party("saronia")

        self._controller_response_names = response_names
        self._controller_error_names = error_names

        try:
            base_path = _infer_controller_base_path(operations)
            relative_base = _route_path_with_snake_case_params(_relative_path(route_prefix, base_path))
            base_parts = [p for p in relative_base.strip("/").split("/") if p and not p.startswith("{")]

            if base_parts:
                controller_base_name = "_".join(base_parts)
                class_name = _to_pascal_case(controller_base_name) + "Controller"
            else:
                class_name = "APIController" if group == "default" else _to_pascal_case(group).removeprefix("Controller") + "Controller"

            controller_auth: str | None = None
            auth_alias: str | None = None
            auth_classes_used: set[str] = set()

            if operations:
                from collections import Counter

                auth_counts = Counter(self._security_requirements_to_auth_expr(op.security_requirements) for op in operations)

                for op in operations:
                    auth_expr = self._security_requirements_to_auth_expr(op.security_requirements)
                    if auth_expr:
                        for part in auth_expr.replace("(", "").replace(")", "").split():
                            if part not in ("|", "&", "~"):
                                auth_classes_used.add(part)

                non_none_auths = [(auth, count) for auth, count in auth_counts.items() if auth is not None]

                if non_none_auths:
                    most_common_auth, most_common_count = max(non_none_auths, key=lambda x: x[1])

                    if most_common_count > len(operations) / 2:
                        controller_auth = most_common_auth
                        auth_alias = f"{_to_snake_case(group).upper()}_AUTH"

            if auth_classes_used:
                for auth_class in sorted(auth_classes_used):
                    imports.local("..auth", auth_class)

            final_method_names = _resolve_method_name_conflicts(operations, base_path)

            method_blocks: list[str] = []
            inline_error_class_plan = self._build_inline_error_class_plan(operations, final_method_names, class_name)

            for op in operations:
                method_name = final_method_names[id(op)]
                src = self._render_operation(schema, op, base_path, imports, controller_auth, method_name, inline_error_class_plan)
                indented = "\n".join("    " + line for line in src.splitlines())
                method_blocks.append(indented)
        finally:
            self._controller_response_names = None
            self._controller_error_names = None

        methods = "\n\n".join(method_blocks)
        exported_names = [class_name]
        exported_names.extend(class_name for class_name, _ in inline_error_class_plan.values())
        all_decl = _render_all(exported_names)

        decorator_args = [f'"{relative_base}"']
        if controller_auth and auth_alias:
            decorator_args.append(f"auth={auth_alias}")

        body = f"@{self._module_name}({', '.join(decorator_args)})\nclass {class_name}:\n{methods}\n{all_decl}\n"

        result = imports.render(future_annotations=False) + "\n\n"

        if auth_alias and controller_auth:
            result += f"{auth_alias} = {controller_auth}\n\n\n"

        if inline_error_class_plan:
            result += "\n\n\n".join(class_src for _, class_src in inline_error_class_plan.values()) + "\n\n\n"

        result += body
        return (class_name, result)

    def _enum_base_class(self, enum: SchemaEnum) -> str:
        if not enum.values:
            return "StrEnum"

        types = {type(v.value) for v in enum.values}

        if types <= {int}:
            return "IntEnum"

        if types <= {float} or types == {int, float}:
            return "FloatEnum"

        return "StrEnum"

    def _render_enum(self, enum: SchemaEnum) -> str:
        base_class = self._enum_base_class(enum)
        lines: list[str] = []
        lines.append(f"class {enum.name}(msgspex.{base_class}, metaclass=msgspex.BaseEnumMeta):")

        if enum.description:
            lines.append(f'    """{enum.description}"""')
            lines.append("")

        if not enum.values:
            lines.append("    pass")
        else:
            for val in enum.values:
                lines.append(f"    {val.name} = {self._dquote_repr(val.value)}")

        return "\n".join(lines)

    def _has_python_default(self, field: Field) -> bool:
        if not field.required:
            return True

        if field.default is not msgspec.UNSET:
            return True

        return bool(field.type.nullable)

    def _render_deprecated_initvar_field(self, field: Field, imports: _Imports) -> str:
        is_union = isinstance(field.type, UnionType)
        py_name = _to_snake_case(field.name)

        if keyword.iskeyword(py_name):
            py_name = py_name + "_"

        json_name_arg = f', name="{field.name}"' if py_name != field.name else f', name="{py_name}"'
        needs_quotes = self._from_needs_quotes(field.type)
        hint = None if is_union else self._name_hint(field.name, field.type, imports)

        if hint is not None:
            base, from_type = hint
            conv_str = f"{base} | None" if field.type.nullable else base

            if field.type.constraints is not None and not field.type.constraints.is_empty():
                imports.bare_stdlib("typing")
                imports.bare_third_party("msgspec")
                meta_args = self._render_meta_args(field.type.constraints)
                base = f"typing.Annotated[{base}, msgspec.Meta({meta_args})]"

            type_str = f"{base} | None" if field.type.nullable else base
        else:
            type_str = self._type_str(field.type, imports)
            conv_str = self._type_str(field.type, imports, for_converter=True)
            from_type = self._from_input_type(field.type, imports)

        def _from(ct: str) -> str:
            return f'msgspex.From["{ct}"]' if needs_quotes else f"msgspex.From[{ct}]"

        imports.bare_stdlib("dataclasses")

        if not field.required:
            imports.bare_third_party("msgspex")

            if field.type.nullable:
                imports.third_party("kungfu.library.monad.option", "NOTHING")
                option_type = "msgspex.NullableOption"
                default_value = "NOTHING"
                option_inner_type = base if hint is not None else self._type_str(field.type, imports, strip_nullable=True)
            else:
                option_type = "msgspex.Option"
                default_value = "..."
                option_inner_type = type_str

            if is_union:
                raw = self._plain_union_str(field.type, imports)  # type: ignore
                converter_type = f"{raw} | None"
            elif from_type:
                converter_type = f"{from_type} | None"
            elif field.type.nullable:
                converter_type = conv_str
            else:
                converter_type = f"{conv_str} | None"

            return f"deprecated_{py_name}_: dataclasses.InitVar[{option_type}[{option_inner_type}]] = msgspex.field(default={default_value}{json_name_arg}, converter={_from(converter_type)})"

        if is_union:
            imports.bare_third_party("msgspex")
            raw = self._plain_union_str(field.type, imports)  # type: ignore
            default_repr = self._dquote_repr(field.default) if field.default is not msgspec.UNSET else None

            if default_repr is not None:
                return f"deprecated_{py_name}_: dataclasses.InitVar[{type_str}] = msgspex.field({json_name_arg}, converter={_from(raw)}, default={default_repr})"
            return f"deprecated_{py_name}_: dataclasses.InitVar[{type_str}] = msgspex.field({json_name_arg}, converter={_from(raw)})"

        if field.type.nullable:
            if from_type:
                imports.bare_third_party("msgspex")
                imports.third_party("kungfu.library.monad.option", "NOTHING")
                nullable_inner_type = base if hint is not None else self._type_str(field.type, imports, strip_nullable=True)
                return f"deprecated_{py_name}_: dataclasses.InitVar[msgspex.NullableOption[{nullable_inner_type}]] = msgspex.field(default=NOTHING{json_name_arg}, converter={_from(f'{from_type} | None')})"

            if field.default is not msgspec.UNSET:
                default_repr = self._dquote_repr(field.default)
                imports.bare_third_party("msgspex")
                return f"deprecated_{py_name}_: dataclasses.InitVar[{type_str}] = msgspex.field(default={default_repr}{json_name_arg})"

            imports.bare_third_party("msgspex")
            imports.third_party("kungfu.library.monad.option", "NOTHING")
            nullable_inner_type = base if hint is not None else self._type_str(field.type, imports, strip_nullable=True)
            return f"deprecated_{py_name}_: dataclasses.InitVar[msgspex.NullableOption[{nullable_inner_type}]] = msgspex.field(default=NOTHING{json_name_arg})"

        if from_type:
            imports.bare_third_party("msgspex")

            if field.default is not msgspec.UNSET:
                default_repr = self._dquote_repr(field.default)
                return f"deprecated_{py_name}_: dataclasses.InitVar[{type_str}] = msgspex.field(default={default_repr}{json_name_arg}, converter={_from(from_type)})"

            field_args = f"converter={_from(from_type)}"
            if json_name_arg:
                field_args = f'name="{field.name if py_name != field.name else py_name}", ' + field_args
            return f"deprecated_{py_name}_: dataclasses.InitVar[{type_str}] = msgspex.field({field_args})"

        if field.default is not msgspec.UNSET:
            default_repr = self._dquote_repr(field.default)
            imports.bare_third_party("msgspex")
            return f"deprecated_{py_name}_: dataclasses.InitVar[{type_str}] = msgspex.field(default={default_repr}{json_name_arg})"

        imports.bare_third_party("msgspex")
        return f'deprecated_{py_name}_: dataclasses.InitVar[{type_str}] = msgspex.field(name="{field.name if py_name != field.name else py_name}")'

    def _render_deprecated_property(self, field: Field, model_name: str, imports: _Imports) -> str:
        py_name = _to_snake_case(field.name)
        if keyword.iskeyword(py_name):
            py_name = py_name + "_"

        is_union = isinstance(field.type, UnionType)
        hint = None if is_union else self._name_hint(field.name, field.type, imports)

        if hint is not None:
            base, _ = hint
            if field.type.constraints is not None and not field.type.constraints.is_empty():
                imports.bare_stdlib("typing")
                imports.bare_third_party("msgspec")
                meta_args = self._render_meta_args(field.type.constraints)
                base = f"typing.Annotated[{base}, msgspec.Meta({meta_args})]"
            type_str = f"{base} | None" if field.type.nullable else base
        else:
            type_str = self._type_str(field.type, imports)

        if not field.required:
            if field.type.nullable:
                option_inner_type = base if hint is not None else self._type_str(field.type, imports, strip_nullable=True)
                type_str = f"msgspex.NullableOption[{option_inner_type}]"
            else:
                type_str = f"msgspex.Option[{type_str}]"
        elif field.type.nullable and hint is not None:
            nullable_inner_type = base if hint is not None else self._type_str(field.type, imports, strip_nullable=True)
            type_str = f"msgspex.NullableOption[{nullable_inner_type}]"

        message = self._get_field_deprecation_message(field, model_name)

        lines: list[str] = []
        lines.append(f"@property")
        lines.append(f"@msgspex.field_deprecation({self._dquote_repr(message)})")
        lines.append(f"def {py_name}(self) -> {type_str}:")
        lines.append(f"    return self.__{py_name}")
        lines.append("")
        lines.append(f"@{py_name}.setter")
        lines.append(f"@msgspex.field_deprecation({self._dquote_repr(message)})")
        lines.append(f"def {py_name}(self, value: {type_str}):")
        lines.append(f"    self.__{py_name} = value")
        lines.append("")
        lines.append(f"@{py_name}.deleter")
        lines.append(f"@msgspex.field_deprecation({self._dquote_repr(message)})")
        lines.append(f"def {py_name}(self):")
        lines.append(f"    del self.__{py_name}")

        return "\n".join(lines)

    def _get_model_deprecation_message(self, model: Model) -> str:
        if model.description:
            return model.description
        return f"Model `{model.name}` is deprecated and will be removed in future releases."

    def _get_field_deprecation_message(self, field: Field, model_name: str) -> str:
        if field.description:
            return field.description
        return f"Field `{field.name}` of `{model_name}` is deprecated and will be removed in future releases."

    def _render_model(self, model: Model, imports: _Imports, *, base: str = "msgspex.Model") -> str:
        lines: list[str] = []
        deprecated_fields: list[Field] = []

        if model.deprecated:
            imports.bare_third_party("msgspex")
            message = self._get_model_deprecation_message(model)
            lines.append(f"@msgspex.model_deprecated({self._dquote_repr(message)})")

        lines.append(f"class {model.name}({base}, kw_only=True):")

        if model.description:
            lines.append(f'    """{model.description}"""')
            lines.append("")

        if not model.fields:
            lines.append("    pass")
        else:
            regular_fields = [f for f in model.fields if not f.deprecated]
            deprecated_fields = [f for f in model.fields if f.deprecated]
            sorted_regular = sorted(regular_fields, key=self._has_python_default)

            for field in sorted_regular:
                lines.append("    " + self._render_field(field, imports))

                if field.description:
                    desc_lines = [line for line in field.description.split("\n") if line.strip()]

                    if len(desc_lines) == 1:
                        lines.append(f'    """{field.description.strip()}"""')
                    else:
                        lines.append(f'    """{desc_lines[0]}')
                        for desc_line in desc_lines[1:]:
                            lines.append(f"    {desc_line}")
                        lines.append('    """')

                    lines.append("")

            if deprecated_fields:
                imports.bare_stdlib("dataclasses")
                imports.bare_third_party("msgspex")

                for field in deprecated_fields:
                    lines.append("    " + self._render_deprecated_initvar_field(field, imports))

                    if field.description:
                        desc_lines = [line for line in field.description.split("\n") if line.strip()]

                        if len(desc_lines) == 1:
                            lines.append(f'    """{field.description.strip()}"""')
                        else:
                            lines.append(f'    """{desc_lines[0]}')

                            for desc_line in desc_lines[1:]:
                                lines.append(f"    {desc_line}")
                            lines.append('    """')

                        lines.append("")

                lines.append("")

                post_init_params_list: list[str] = []
                for field in deprecated_fields:
                    py_name = _to_snake_case(field.name)

                    if keyword.iskeyword(py_name):
                        py_name = py_name + "_"

                    is_union = isinstance(field.type, UnionType)
                    hint = None if is_union else self._name_hint(field.name, field.type, imports)

                    if hint is not None:
                        base, _ = hint

                        if field.type.constraints is not None and not field.type.constraints.is_empty():
                            imports.bare_stdlib("typing")
                            imports.bare_third_party("msgspec")
                            meta_args = self._render_meta_args(field.type.constraints)
                            base = f"typing.Annotated[{base}, msgspec.Meta({meta_args})]"

                        type_str = f"{base} | None" if field.type.nullable else base
                    else:
                        type_str = self._type_str(field.type, imports)

                    if not field.required:
                        if field.type.nullable:
                            option_inner_type = base if hint is not None else self._type_str(field.type, imports, strip_nullable=True)
                            type_str = f"msgspex.NullableOption[{option_inner_type}]"
                        else:
                            type_str = f"msgspex.Option[{type_str}]"

                    elif field.type.nullable and hint is not None:
                        nullable_inner_type = base if hint is not None else self._type_str(field.type, imports, strip_nullable=True)
                        type_str = f"msgspex.NullableOption[{nullable_inner_type}]"

                    post_init_params_list.append(f"deprecated_{py_name}_: {type_str}")

                post_init_params = ", ".join(post_init_params_list)
                lines.append(f"    def __post_init__(self, {post_init_params}) -> None:")

                for field in deprecated_fields:
                    py_name = _to_snake_case(field.name)

                    if keyword.iskeyword(py_name):
                        py_name = py_name + "_"

                    lines.append(f"        self.__{py_name} = deprecated_{py_name}_")

        result = "\n".join(lines)

        if deprecated_fields:
            for field in deprecated_fields:
                result += "\n\n" + "    " + self._render_deprecated_property(field, model.name, imports).replace("\n", "\n    ")

        return result

    def _render_error_model(
        self,
        model: Model,
        statuses: set[str],
        imports: _Imports,
        *,
        data_base: str | None = None,
    ) -> str:
        base_parts: list[str] = [data_base] if data_base else ["msgspex.Model"]
        if statuses:
            status_args = ", ".join(_status_to_http_status(c) for c in sorted(statuses))
            base_parts.append(f"saronia.ModelStatusError[{status_args}]")

        base = ", ".join(base_parts)

        lines: list[str] = []
        lines.append(f"class {model.name}({base}, kw_only=True):")

        if model.description:
            lines.append(f'    """{model.description}"""')
            lines.append("")

        if not model.fields:
            lines.append("    pass")

        else:
            sorted_fields = sorted(model.fields, key=self._has_python_default)
            for field in sorted_fields:
                lines.append("    " + self._render_field(field, imports))

                if field.description:
                    desc_lines = [line for line in field.description.split("\n") if line.strip()]

                    if len(desc_lines) == 1:
                        lines.append(f'    """{field.description.strip()}"""')
                    else:
                        lines.append(f'    """{desc_lines[0]}')

                        for desc_line in desc_lines[1:]:
                            lines.append(f"    {desc_line}")
                        lines.append('    """')

                    lines.append("")

        return "\n".join(lines)

    def _render_named_response(
        self,
        named_response: NamedResponse,
        imports: _Imports,
        is_error: bool,
    ) -> str:
        bases: list[str] = []

        if named_response.schema_ref:
            bases.append(named_response.schema_ref)

            if (
                (   is_error
                    and self._controller_error_names
                    and named_response.schema_ref in self._controller_error_names
                )
                or (
                    not is_error
                    and self._controller_response_names
                    and named_response.schema_ref in self._controller_response_names
                )
            ):
                pass
            elif self._controller_error_names and named_response.schema_ref in self._controller_error_names:
                imports.local(".errors", named_response.schema_ref)
            elif self._controller_response_names and named_response.schema_ref in self._controller_response_names:
                imports.local(".responses", named_response.schema_ref)
            else:
                imports.local(".objects", named_response.schema_ref)

        if is_error:
            if named_response.status_codes:
                error_codes = [sc for sc in named_response.status_codes if sc.startswith(("4", "5"))]
            else:
                inferred = _infer_status_code_from_name(named_response.name)
                error_codes = [inferred] if inferred and inferred.startswith(("4", "5")) else []

            if error_codes:
                status_args = ", ".join(_status_to_http_status(c) for c in sorted(error_codes))
                bases.append(f"saronia.ModelStatusError[{status_args}]")

        if not bases:
            bases.append("msgspex.Model")

        base_str = ", ".join(bases)
        lines: list[str] = [f"class {named_response.name}({base_str}, kw_only=True):"]

        if named_response.description:
            lines.append(f'    """{named_response.description}"""')

        lines.append("    pass")

        return "\n".join(lines)

    def _from_needs_quotes(self, type_ref: TypeRef) -> bool:
        """Return True if the From[...] argument must be quoted (contains a forward ref).

        ModelRef and EnumRef names are defined in the same generated file and may
        not be visible yet at the point where the field default is evaluated.
        """
        if isinstance(type_ref, (ModelRef, EnumRef)):
            return True

        if isinstance(type_ref, UnionType):
            return any(self._from_needs_quotes(v) for v in type_ref.variants)

        if isinstance(type_ref, ArrayType):
            return self._from_needs_quotes(type_ref.item_type)

        if isinstance(type_ref, MapType):
            return self._from_needs_quotes(type_ref.value_type)

        return False

    @staticmethod
    def _dquote_repr(val: object) -> str:
        if isinstance(val, str):
            escaped = val.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'

        return repr(val)

    def _render_field(self, field: Field, imports: _Imports) -> str:  # noqa: PLR0915
        is_union = isinstance(field.type, UnionType)
        py_name = _to_snake_case(field.name)

        if keyword.iskeyword(py_name):
            py_name = py_name + "_"

        if py_name != field.name:
            json_name_arg = f', name="{field.name}"'
            json_name_lead = f'name="{field.name}", '
        else:
            json_name_arg = ""
            json_name_lead = ""

        needs_quotes = self._from_needs_quotes(field.type)
        hint = None if is_union else self._name_hint(field.name, field.type, imports)

        if hint is not None:
            base, from_type = hint
            conv_str = f"{base} | None" if field.type.nullable else base
            if field.type.constraints is not None and not field.type.constraints.is_empty():
                imports.bare_stdlib("typing")
                imports.bare_third_party("msgspec")

                meta_args = self._render_meta_args(field.type.constraints)
                base = f"typing.Annotated[{base}, msgspec.Meta({meta_args})]"

            type_str = f"{base} | None" if field.type.nullable else base
        else:
            type_str = self._type_str(field.type, imports)
            conv_str = self._type_str(field.type, imports, for_converter=True)
            from_type = self._from_input_type(field.type, imports)

        def _from(ct: str) -> str:
            return f'msgspex.From["{ct}"]' if needs_quotes else f"msgspex.From[{ct}]"

        if not field.required:
            imports.bare_third_party("msgspex")

            if field.type.nullable:
                imports.third_party("kungfu.library.monad.option", "NOTHING")
                option_type = "msgspex.NullableOption"
                default_value = "NOTHING"
                option_inner_type = base if hint is not None else self._type_str(field.type, imports, strip_nullable=True)
            else:
                option_type = "msgspex.Option"
                default_value = "..."
                option_inner_type = type_str

            if is_union:
                raw = self._plain_union_str(field.type, imports)  # type: ignore[arg-type]
                converter_type = f"{raw} | None"
            elif from_type:
                converter_type = f"{from_type} | None"
            elif field.type.nullable:
                # conv_str already ends with "| None"
                converter_type = conv_str
            else:
                converter_type = f"{conv_str} | None"

            return f"{py_name}: {option_type}[{option_inner_type}] = msgspex.field(default={default_value}{json_name_arg}, converter={_from(converter_type)})"

        if is_union:
            imports.bare_third_party("msgspex")
            raw = self._plain_union_str(field.type, imports)  # type: ignore[arg-type]
            default_repr = self._dquote_repr(field.default) if field.default is not msgspec.UNSET else None

            if default_repr is not None:
                return f"{py_name}: {type_str} = msgspex.field({json_name_lead}converter={_from(raw)}, default={default_repr})"
            return f"{py_name}: {type_str} = msgspex.field({json_name_lead}converter={_from(raw)})"

        if field.type.nullable:
            if from_type:
                imports.bare_third_party("msgspex")

                imports.third_party("kungfu.library.monad.option", "NOTHING")
                nullable_inner_type = base if hint is not None else self._type_str(field.type, imports, strip_nullable=True)
                return f"{py_name}: msgspex.NullableOption[{nullable_inner_type}] = msgspex.field(default=NOTHING{json_name_arg}, converter={_from(f'{from_type} | None')})"

            if field.default is not msgspec.UNSET:
                default_repr = self._dquote_repr(field.default)
                imports.bare_third_party("msgspex")
                return f"{py_name}: {type_str} = msgspex.field(default={default_repr}{json_name_arg})"

            imports.bare_third_party("msgspex")

            imports.third_party("kungfu.library.monad.option", "NOTHING")
            nullable_inner_type = base if hint is not None else self._type_str(field.type, imports, strip_nullable=True)
            return f"{py_name}: msgspex.NullableOption[{nullable_inner_type}] = msgspex.field(default=NOTHING{json_name_arg})"

        if from_type:
            imports.bare_third_party("msgspex")

            if field.default is not msgspec.UNSET:
                default_repr = self._dquote_repr(field.default)
                return f"{py_name}: {type_str} = msgspex.field(default={default_repr}{json_name_arg}, converter={_from(from_type)})"

            field_args = f"converter={_from(from_type)}"
            if json_name_lead:
                field_args = json_name_lead + field_args
            return f"{py_name}: {type_str} = msgspex.field({field_args})"

        if field.default is not msgspec.UNSET:
            default_repr = self._dquote_repr(field.default)
            imports.bare_third_party("msgspex")
            return f"{py_name}: {type_str} = msgspex.field(default={default_repr}{json_name_arg})"

        if json_name_arg:
            imports.bare_third_party("msgspex")
            return f"{py_name}: {type_str} = msgspex.field({json_name_lead.removesuffix(', ')})"

        return f"{py_name}: {type_str}"

    def _is_simple_type(self, type_ref: TypeRef) -> bool:
        from retcon.schema.types import AnyType, ArrayType, BooleanType, IntegerType, MapType, ModelRef, NumberType, StringType

        if isinstance(type_ref, (IntegerType, NumberType, BooleanType)):
            return True

        if isinstance(type_ref, StringType):
            return type_ref.format not in ("date", "date-time", "email", "idn-email", "uri", "uri-reference", "hostname", "ipv4", "ipv6")

        if isinstance(type_ref, ModelRef) and type_ref.name == "UUID":
            return True

        if isinstance(type_ref, MapType) and isinstance(type_ref.value_type, AnyType):
            return True

        return bool(isinstance(type_ref, ArrayType) and isinstance(type_ref.item_type, AnyType))

    def _render_operation(
        self,
        schema: APISchema,
        op: Operation,
        base_path: str,
        imports: _Imports,
        controller_auth: str | None = None,
        method_name: str | None = None,
        inline_error_class_plan: dict[tuple[str, str], tuple[str, str]] | None = None,
    ) -> str:
        method = op.method.lower()
        imports.bare_third_party("saronia")

        rel_path = _route_path_with_snake_case_params(_relative_path(base_path, op.path))

        path_params = [self._effective_param_for_signature(p, op.deprecated) for p in op.parameters if p.location == "path"]
        query_params = [self._effective_param_for_signature(p, op.deprecated) for p in op.parameters if p.location == "query"]
        header_params = [self._effective_param_for_signature(p, op.deprecated) for p in op.parameters if p.location == "header"]

        total_params = len(path_params) + len(query_params) + len(header_params)
        use_dto = total_params > 3

        decorator_args: list[str] = [repr(rel_path)]
        func_params: list[str] = ["self"]

        has_request_body_model = op.request_body is not None and isinstance(op.request_body.type, ModelRef)
        request_body_model_name = op.request_body.type.name if has_request_body_model else None  # type: ignore
        has_complex_params = any(not self._is_simple_type(p.type) for p in path_params + query_params + header_params)
        use_dto = total_params > 3 or (has_request_body_model and total_params > 0) or has_complex_params

        if use_dto:
            dto_name = self._generate_parameter_dto(
                schema,
                op,
                method,
                method_name or _operation_to_method_name(op, base_path),
                path_params,
                query_params,
                header_params,
                imports,
                request_body_model_name,
            )
            decorator_args.append(dto_name)
            imports.local("..signatures", dto_name)

        elif has_request_body_model:
            for p in path_params:
                py_name = self._controller_param_name(p)
                t = self._controller_param_type(p, imports)
                annotation = self._controller_param_annotation(p, t)
                func_params.append(f"{py_name}: {annotation}")

            for p in query_params:
                py_name = self._controller_param_name(p)
                t = self._controller_param_type(p, imports)
                annotation = self._controller_param_annotation(p, t)

                if p.required:
                    func_params.append(f"{py_name}: {annotation}")
                else:
                    func_params.append(f"{py_name}: {self._controller_optional_annotation(annotation)} = None")

            for p in header_params:
                py_name = self._controller_param_name(p)
                t = self._controller_param_type(p, imports)
                annotation = self._controller_param_annotation(p, t)

                if p.required:
                    func_params.append(f"{py_name}: {annotation}")
                else:
                    func_params.append(f"{py_name}: {self._controller_optional_annotation(annotation)} = None")
        else:
            param_counts = {
                "path": len(path_params),
                "query": len(query_params),
                "header": len(header_params),
            }
            dominant_type = max(param_counts, key=param_counts.get) if total_params > 0 else "path"  # type: ignore

            if dominant_type != "path" and param_counts[dominant_type] > 0:
                decorator_args.append(f"{dominant_type}=True")

            for p in path_params:
                py_name = self._controller_param_name(p)
                t = self._controller_param_type(p, imports)
                annotation = self._controller_param_annotation(p, t, dominant_type=dominant_type)
                func_params.append(f"{py_name}: {annotation}")

            for p in query_params:
                py_name = self._controller_param_name(p)
                t = self._controller_param_type(p, imports)
                annotation = self._controller_param_annotation(p, t, dominant_type=dominant_type)

                if p.required:
                    func_params.append(f"{py_name}: {annotation}")
                else:
                    func_params.append(f"{py_name}: {self._controller_optional_annotation(annotation)} = None")

            for p in header_params:
                py_name = self._controller_param_name(p)
                t = self._controller_param_type(p, imports)
                annotation = self._controller_param_annotation(p, t, dominant_type=dominant_type)

                if p.required:
                    func_params.append(f"{py_name}: {annotation}")
                else:
                    func_params.append(f"{py_name}: {self._controller_optional_annotation(annotation)} = None")

        if has_request_body_model and not use_dto:
            model_name = op.request_body.type.name  # type: ignore
            decorator_args.append(model_name)

            if self._controller_response_names is not None and self._controller_error_names is not None:
                if model_name in self._controller_error_names:
                    module = "..errors"
                elif model_name in self._controller_response_names:
                    module = "..responses"
                else:
                    module = "..objects"

                imports.local(module, model_name)

        op_auth = self._security_requirements_to_auth_expr(op.security_requirements)

        if op_auth != controller_auth:
            if op_auth is None:
                decorator_args.append("auth=None")
            else:
                decorator_args.append(f"auth={op_auth}")

        success_type = self._get_success_type(op.responses, imports)
        error_parts = self._get_error_types(op.responses, imports, method_name or _operation_to_method_name(op, base_path), inline_error_class_plan)
        if error_parts:
            error_union = " | ".join(error_parts)
            return_type = f"saronia.APIResult[{success_type}, {error_union},]" if len(error_parts) > 1 else f"saronia.APIResult[{success_type}, {error_union}]"
        else:
            return_type = f"saronia.APIResult[{success_type}]"

        params_str = ", ".join(["self", "*", *func_params[1:]]) + ("," if len(func_params) > 1 else "self")
        decorators: list[str] = []

        if op.deprecated:
            if op.description:
                decorators.append(f"@saronia.route_deprecated({self._dquote_repr(op.description)})")
            else:
                decorators.append("@saronia.route_deprecated()")

        decorators.append(f"@saronia.{method}({', '.join(decorator_args)})")

        if method_name is None:
            method_name = _operation_to_method_name(op, base_path)

        lines = [*decorators, f"async def {method_name}({params_str}) -> {return_type}:"]
        docstring_parts: list[str] = []

        if op.description:
            desc_lines = [line for line in op.description.split("\n") if line.strip()]
            docstring_parts.extend(desc_lines)

        if not use_dto:
            param_descriptions: list[str] = []

            for p in path_params + query_params + header_params:
                if p.description:
                    py_name = _to_snake_case(p.name)
                    if keyword.iskeyword(py_name):
                        py_name = py_name + "_"

                    desc_lines = [line for line in p.description.split("\n") if line.strip()]
                    if len(desc_lines) == 1:
                        param_descriptions.append(f"    {py_name}: {desc_lines[0]}")
                    else:
                        param_descriptions.append(f"    {py_name}: {desc_lines[0]} \\")

                        for desc_line in desc_lines[1:-1]:
                            param_descriptions.append(f"    {desc_line} \\")

                        param_descriptions.append(f"    {desc_lines[-1]}")

            if param_descriptions:
                if docstring_parts:
                    docstring_parts.append("")

                docstring_parts.append("Args:")
                docstring_parts.extend(param_descriptions)
                docstring_parts.append("")

        if docstring_parts:
            if len(docstring_parts) == 1 and "\n" not in docstring_parts[0]:
                lines.append(f'    """{docstring_parts[0]}"""')
            else:
                lines.append(f'    """{docstring_parts[0]}')

                for part in docstring_parts[1:]:
                    if part == "":
                        lines.append("    ")
                    else:
                        lines.append(f"    {part}")
                lines.append('    """')

        lines.append("    ...")
        return "\n".join(lines)

    def _type_str(self, type_ref: TypeRef, imports: _Imports | None, *, for_converter: bool = False, strip_nullable: bool = False) -> str:  # noqa: PLR0915
        def add_stdlib(module: str, name: str) -> None:
            if imports is not None:
                imports.stdlib(module, name)

        def add_bare_stdlib(module: str) -> None:
            if imports is not None:
                imports.bare_stdlib(module)

        def add_tp(module: str, name: str) -> None:
            if imports is not None:
                imports.third_party(module, name)

        if isinstance(type_ref, StringType):
            fmt = type_ref.format

            if fmt == "date-time":
                base = "msgspex.isodatetime"
            elif fmt == "date":
                add_stdlib("datetime", "date")
                base = "date"
            elif fmt == "uuid":
                add_stdlib("uuid", "UUID")
                base = "UUID"
            elif fmt == "email":
                base = "msgspex.Email"
            elif fmt == "idn-email":
                base = "msgspex.IDNEmail"
            elif fmt in ("uri", "url"):
                base = "msgspex.URI"
            elif fmt == "uri-reference":
                base = "msgspex.URIReference"
            elif fmt == "iri":
                base = "msgspex.IRI"
            elif fmt == "iri-reference":
                base = "msgspex.IRIReference"
            elif fmt == "hostname":
                base = "msgspex.Hostname"
            elif fmt == "idn-hostname":
                base = "msgspex.IDNHostname"
            elif fmt == "ipv4":
                base = "msgspex.IPv4"
            elif fmt == "ipv6":
                base = "msgspex.IPv6"
            elif fmt == "json-pointer":
                base = "msgspex.JsonPointer"
            elif fmt == "relative-json-pointer":
                base = "msgspex.RelativeJsonPointer"
            else:
                base = "str"

        elif isinstance(type_ref, IntegerType):
            fmt = type_ref.format
            if fmt == "int32":
                base = "msgspex.Int32"
            elif fmt == "int64":
                base = "msgspex.Int64"
            else:
                base = "int"

        elif isinstance(type_ref, NumberType):
            fmt = type_ref.format

            if fmt in ("float", "float32"):
                base = "msgspex.Float32"
            elif fmt in ("double", "float64"):
                base = "msgspex.Float64"
            else:
                base = "float"

        elif isinstance(type_ref, BooleanType):
            base = "bool"

        elif isinstance(type_ref, ArrayType):
            base = f"list[{self._type_str(type_ref.item_type, imports)}]"

        elif isinstance(type_ref, MapType):
            base = f"dict[str, {self._type_str(type_ref.value_type, imports)}]"

        elif isinstance(type_ref, UnionType):
            if imports is not None:
                imports.bare_third_party("kungfu")

            variant_parts = [self._type_str(v, imports) for v in type_ref.variants]
            base = f"kungfu.Sum[{', '.join(variant_parts)}]"

        elif isinstance(type_ref, ModelRef):
            base = type_ref.name
            if imports is not None and self._controller_response_names is not None and self._controller_error_names is not None:
                if base in self._controller_error_names:
                    module = "..errors"
                elif base in self._controller_response_names:
                    module = "..responses"
                else:
                    module = "..objects"

                # Adjust module path for responses.py and errors.py (they use .objects not ..objects)
                if module == "..objects" and imports._enums_module == ".enums":
                    module = ".objects"
                elif module == "..responses" and imports._enums_module == ".enums":
                    module = ".responses"
                elif module == "..errors" and imports._enums_module == ".enums":
                    module = ".errors"

                imports.local(module, base)

        elif isinstance(type_ref, EnumRef):
            base = type_ref.name
            if imports is not None:
                imports.mark_enum_used()

        elif isinstance(type_ref, AnyType):
            add_bare_stdlib("typing")
            base = "typing.Any"

        else:
            add_bare_stdlib("typing")
            base = "typing.Any"

        if not for_converter and type_ref.constraints is not None and not type_ref.constraints.is_empty():
            add_bare_stdlib("typing")

            if imports is not None:
                imports.bare_third_party("msgspec")

            meta_args = self._render_meta_args(type_ref.constraints)
            base = f"typing.Annotated[{base}, msgspec.Meta({meta_args})]"

        return f"{base} | None" if (type_ref.nullable and not strip_nullable) else base

    def _plain_union_str(self, type_ref: UnionType, imports: _Imports | None) -> str:
        parts = [self._type_str(v, imports, for_converter=True) for v in type_ref.variants]
        return " | ".join(parts)

    def _from_input_type(self, type_ref: TypeRef, imports: _Imports | None) -> str | None:
        def add_tp(module: str, name: str) -> None:
            if imports is not None:
                imports.third_party(module, name)

        if isinstance(type_ref, ModelRef) and type_ref.name == "UUID":
            if imports is not None:
                imports.stdlib("uuid", "UUID")
            return "str | UUID"

        if isinstance(type_ref, StringType):
            fmt = type_ref.format

            if fmt == "uuid":
                if imports is not None:
                    imports.stdlib("uuid", "UUID")
                return "str | UUID"

            if fmt == "date":
                if imports is not None:
                    imports.stdlib("datetime", "date")
                return "str | date"

            if fmt in self._DATETIME_FORMATS:
                if imports is not None:
                    imports.stdlib("datetime", "datetime")
                return "str | datetime"

            if fmt == "email":

                return "str | msgspex.Email"

            if fmt == "idn-email":

                return "str | msgspex.IDNEmail"

            if fmt in ("uri", "url"):

                return "str | msgspex.URI"
            if fmt == "uri-reference":

                return "str | msgspex.URIReference"
            if fmt == "iri":

                return "str | msgspex.IRI"
            if fmt == "iri-reference":

                return "str | msgspex.IRIReference"
            if fmt == "hostname":

                return "str | msgspex.Hostname"
            if fmt == "idn-hostname":

                return "str | msgspex.IDNHostname"
            if fmt == "ipv4":

                return "str | msgspex.IPv4"
            if fmt == "ipv6":

                return "str | msgspex.IPv6"
            if fmt == "json-pointer":

                return "str | msgspex.JsonPointer"
            if fmt == "relative-json-pointer":

                return "str | msgspex.RelativeJsonPointer"

        if isinstance(type_ref, IntegerType):
            if type_ref.format == "int32":

                return "int | msgspex.Int32"

            if type_ref.format == "int64":

                return "int | msgspex.Int64"

        if isinstance(type_ref, NumberType):
            if type_ref.format == "float32":

                return "float | msgspex.Float32"

            if type_ref.format in ("float64", "double"):

                return "float | msgspex.Float64"

        if isinstance(type_ref, ArrayType):
            item_input_type = self._from_input_type(type_ref.item_type, imports)
            if item_input_type is not None:
                return f"list[{item_input_type}]"

        return None

    def _name_hint(
        self,
        name: str,
        type_ref: TypeRef,
        imports: _Imports,
    ) -> tuple[str, str | None] | None:
        if name == "uuid" and isinstance(type_ref, StringType) and type_ref.format is None:
            imports.stdlib("uuid", "UUID")
            return "UUID", "str | UUID"

        if name == "date" and isinstance(type_ref, StringType) and type_ref.format is None:
            imports.stdlib("datetime", "date")
            return "date", "str | date"

        if name == "timestamp":
            if isinstance(type_ref, StringType) and type_ref.format is None:

                imports.stdlib("datetime", "datetime")
                return "msgspex.StringTimestampDatetime", "str | datetime"

            if isinstance(type_ref, IntegerType) and type_ref.format is None:

                imports.stdlib("datetime", "datetime")
                return "msgspex.IntTimestampDatetime", "int | datetime"

            if isinstance(type_ref, NumberType) and type_ref.format in self._FLOAT_FORMATS:

                imports.stdlib("datetime", "datetime")
                return "msgspex.FloatTimestampDatetime", "float | datetime"

        return None

    def _render_meta_args(self, c: Constraints) -> str:
        parts: list[str] = []

        for field in msgspec.structs.fields(c):
            val = getattr(c, field.name)

            if val is None:
                continue
            if field.name == "pattern" and isinstance(val, str):
                parts.append(f"pattern={_raw_string(val)}")
            elif isinstance(val, float) and val.is_integer():
                parts.append(f"{field.name}={int(val)}")
            else:
                parts.append(f"{field.name}={val!r}")

        return ", ".join(parts)

    def _collect_model_refs(self, type_ref: TypeRef, result: set[str]) -> None:
        if isinstance(type_ref, ModelRef):
            result.add(type_ref.name)
        elif isinstance(type_ref, ArrayType):
            self._collect_model_refs(type_ref.item_type, result)
        elif isinstance(type_ref, MapType):
            self._collect_model_refs(type_ref.value_type, result)
        elif isinstance(type_ref, UnionType):
            for variant in type_ref.variants:
                self._collect_model_refs(variant, result)

    def _collect_inlined_request_body_models(self, schema: APISchema) -> set[str]:
        result: set[str] = set()
        models_used_as_fields: set[str] = set()

        for model in schema.models:
            for field in model.fields:
                self._collect_model_refs(field.type, models_used_as_fields)

        for endpoint in schema.endpoints:
            for op in endpoint.operations:
                if op.request_body is None or not isinstance(op.request_body.type, ModelRef):
                    continue

                path_params = [p for p in op.parameters if p.location == "path"]
                query_params = [p for p in op.parameters if p.location == "query"]
                header_params = [p for p in op.parameters if p.location == "header"]
                total_params = len(path_params) + len(query_params) + len(header_params)

                if total_params > 0:
                    model_name = op.request_body.type.name
                    if model_name not in models_used_as_fields:
                        result.add(model_name)

        return result

    def _collect_response_statuses(self, schema: APISchema) -> dict[str, set[str]]:
        result: dict[str, set[str]] = defaultdict(set)

        for endpoint in schema.endpoints:
            for op in endpoint.operations:
                for resp in op.responses:
                    try:
                        status_int = int(resp.status_code)
                    except ValueError:
                        if resp.status_code != "default":
                            continue

                    if _is_success_status(resp.status_code):
                        for type_ref in resp.content.values():
                            if isinstance(type_ref, ModelRef):
                                result[type_ref.name].add(resp.status_code)

        return dict(result)

    def _collect_error_statuses(self, schema: APISchema) -> dict[str, set[str]]:
        result: dict[str, set[str]] = defaultdict(set)

        for endpoint in schema.endpoints:
            for op in endpoint.operations:
                for resp in op.responses:
                    try:
                        status_int = int(resp.status_code)
                        if status_int >= 300:
                            for type_ref in resp.content.values():
                                if isinstance(type_ref, ModelRef):
                                    result[type_ref.name].add(resp.status_code)
                    except ValueError:
                        pass

        return dict(result)

    def _get_success_type(self, responses: list[Response], imports: _Imports) -> str:
        for resp in responses:
            if _is_success_status(resp.status_code):
                for type_ref in resp.content.values():
                    return self._type_str(type_ref, imports)

        return "None"

    def _get_error_types(
        self,
        responses: list[Response],
        imports: _Imports,
        method_name: str,
        inline_error_class_plan: dict[tuple[str, str], tuple[str, str]] | None,
    ) -> list[str]:
        seen: set[str] = set()
        types: list[str] = []

        for resp in responses:
            if _is_error_status(resp.status_code):
                if resp.component_response_ref:
                    if resp.component_response_ref not in seen:
                        seen.add(resp.component_response_ref)
                        types.append(resp.component_response_ref)
                        # Import from errors module
                        if self._controller_error_names and resp.component_response_ref in self._controller_error_names:
                            imports.local("..errors", resp.component_response_ref)
                else:  # noqa
                    if resp.content:
                        for type_ref in resp.content.values():
                            t = self._type_str(type_ref, imports)
                            if t not in seen:
                                seen.add(t)
                                types.append(t)
                    else:
                        key = (resp.status_code, _first_docstring_line(resp.description) or "")
                        if inline_error_class_plan is not None and key in inline_error_class_plan:
                            class_name = inline_error_class_plan[key][0]
                        else:
                            class_name = f"{_to_pascal_case(method_name)}{_status_code_to_name(resp.status_code)}Error"
                        if class_name not in seen:
                            seen.add(class_name)
                            types.append(class_name)

        return types

    def _render_dto_field(self, param: Parameter, temp_imports: _Imports, dominant_type: str, has_request_body: bool = False) -> tuple[str, str | None, bool]:
        py_name = _to_snake_case(param.name)

        if keyword.iskeyword(py_name):
            py_name = py_name + "_"

        json_name_arg = f', name="{param.name}"' if py_name != param.name else ""
        hint = None if isinstance(param.type, UnionType) else self._name_hint(param.name, param.type, temp_imports)
        if hint is not None:
            base, from_type = hint

            if param.type.constraints is not None and not param.type.constraints.is_empty():
                temp_imports.bare_stdlib("typing")
                temp_imports.bare_third_party("msgspec")
                meta_args = self._render_meta_args(param.type.constraints)
                base = f"typing.Annotated[{base}, msgspec.Meta({meta_args})]"

            t = f"{base} | None" if param.type.nullable else base
        else:
            t = self._type_str(param.type, temp_imports)
            from_type = self._from_input_type(param.type, temp_imports)

        param_location = None
        if hasattr(param, "location") and (has_request_body or param.location != dominant_type):
            if param.location == "path":
                param_location = "saronia.Path"
            elif param.location == "query":
                param_location = "saronia.Query"
            elif param.location == "header":
                param_location = "saronia.Header"

        def decorate_type(annotation: str) -> str:
            if not param.deprecated:
                return annotation

            deprecated_arg = self._dquote_repr(param.description) if param.description else "..."
            return f"msgspex.Deprecated[{annotation}, {deprecated_arg}]"

        if from_type:
            temp_imports.bare_third_party("msgspex")

            if param_location:
                if param.required:
                    converter = f"msgspex.From[{from_type}]"
                    annotation = decorate_type(f"{param_location}[{t}]")
                    return (f"    {py_name}: {annotation} = msgspex.field(converter={converter}{json_name_arg})", param.description, True)
                else:
                    converter = f"msgspex.From[{from_type} | None]"
                    annotation = decorate_type(f"{param_location}[{t}]")
                    return (f"    {py_name}: {annotation} | None = msgspex.field(default=None, converter={converter}{json_name_arg})", param.description, True)
            elif param.required:
                converter = f"msgspex.From[{from_type}]"
                annotation = decorate_type(t)
                return (f"    {py_name}: {annotation} = msgspex.field(converter={converter}{json_name_arg})", param.description, True)
            else:
                converter = f"msgspex.From[{from_type} | None]"
                annotation = decorate_type(t)
                return (f"    {py_name}: {annotation} | None = msgspex.field(default=None, converter={converter}{json_name_arg})", param.description, True)

        elif param_location:
            if param.required:
                if json_name_arg:
                    temp_imports.bare_third_party("msgspex")
                    annotation = decorate_type(f"{param_location}[{t}]")
                    return (f'    {py_name}: {annotation} = msgspex.field(name="{param.name}")', param.description, True)

                annotation = decorate_type(f"{param_location}[{t}]")
                return (f"    {py_name}: {annotation}", param.description, False)
            else:
                annotation = decorate_type(f"{param_location}[{t}]")
                return (f"    {py_name}: {annotation} | None = " + (f"msgspex.field(default=None{json_name_arg})" if json_name_arg else "None"), param.description, True)

        elif param.required:
            if json_name_arg:
                temp_imports.bare_third_party("msgspex")
                annotation = decorate_type(t)
                return (f'    {py_name}: {annotation} = msgspex.field(name="{param.name}")', param.description, True)

            annotation = decorate_type(t)
            return (f"    {py_name}: {annotation}", param.description, False)
        else:
            if json_name_arg:
                temp_imports.bare_third_party("msgspex")
                annotation = decorate_type(t)
                return (f"    {py_name}: {annotation} | None = msgspex.field(default=None{json_name_arg})", param.description, True)

            annotation = decorate_type(t)
            return (f"    {py_name}: {annotation} | None = None", param.description, True)

    def _render_signature_class(
        self,
        name: str,
        decorators: tuple[str, ...],
        fields: tuple[_SignatureFieldSpec, ...],
        *,
        base: str = "msgspex.Model",
    ) -> str:
        lines = [*decorators, f"class {name}({base}, kw_only=True):"]

        if not fields:
            lines.append("    pass")
            return "\n".join(lines)

        for field in fields:
            lines.append(field.code)

            if field.description:
                desc_lines = [line for line in field.description.split("\n") if line.strip()]

                if len(desc_lines) == 1:
                    lines.append(f'    """{field.description.strip()}"""')
                else:
                    lines.append(f'    """{desc_lines[0]}')

                    for desc_line in desc_lines[1:]:
                        lines.append(f"    {desc_line}")

                    lines.append('    """')

                lines.append("")

        return "\n".join(lines)

    def _controller_param_name(self, param: Parameter) -> str:
        py_name = _to_snake_case(param.name)

        if keyword.iskeyword(py_name):
            py_name = py_name + "_"

        return py_name

    def _controller_param_annotation(self, param: Parameter, type_str: str, *, dominant_type: str | None = None) -> str:
        location_map = {
            "path": "saronia.Path",
            "query": "saronia.Query",
            "header": "saronia.Header",
        }
        location = location_map[param.location]
        py_name = self._controller_param_name(param)
        is_alias = py_name != param.name
        is_deprecated = param.deprecated

        deprecated_arg = None
        if is_deprecated:
            deprecated_arg = f"saronia.Deprecated({self._dquote_repr(param.description)})" if param.description else "saronia.Deprecated()"

        if deprecated_arg:
            param_args = [type_str, location]

            if is_alias:
                param_args.append(self._dquote_repr(param.name))

            param_args.append(deprecated_arg)
            return f"saronia.Param[{', '.join(param_args)}]"

        if dominant_type == param.location:
            if is_alias:
                return f'saronia.Param[{type_str}, {location}, "{param.name}"]'
            return type_str

        if not is_alias:
            return f"{location}[{type_str}]"

        return f'saronia.Param[{type_str}, {location}, "{param.name}"]'

    def _controller_param_type(self, param: Parameter, imports: _Imports) -> str:
        hint = None if isinstance(param.type, UnionType) else self._name_hint(param.name, param.type, imports)
        if hint is not None:
            return hint[0]

        return self._type_str(param.type, imports)

    @staticmethod
    def _controller_optional_annotation(annotation: str) -> str:
        if annotation.startswith("saronia.Param[") and annotation.endswith("]"):
            inner = annotation[len("saronia.Param[") : -1]
            type_part, rest = inner.split(", ", 1)
            return f"saronia.Param[{type_part} | None, {rest}]"

        return f"{annotation} | None"

    @staticmethod
    def _effective_param_for_signature(param: Parameter, route_deprecated: bool) -> Parameter:
        if not route_deprecated or not param.deprecated:
            return param

        return Parameter(
            name=param.name,
            location=param.location,
            type=param.type,
            required=param.required,
            description=param.description,
            deprecated=False,
        )

    @staticmethod
    def _status_only_error_key(resp: Response) -> tuple[str, str] | None:
        if not _is_error_status(resp.status_code):
            return None
        if resp.component_response_ref or resp.content:
            return None
        return (resp.status_code, _first_docstring_line(resp.description) or "")

    def _build_inline_error_class_plan(
        self,
        operations: list[Operation],
        final_method_names: dict[int, str],
        controller_class_name: str,
    ) -> dict[tuple[str, str], tuple[str, str]]:
        occurrences: dict[tuple[str, str], list[str]] = defaultdict(list)

        for op in operations:
            method_name = final_method_names[id(op)]
            for resp in op.responses:
                key = self._status_only_error_key(resp)
                if key is not None:
                    occurrences[key].append(method_name)

        controller_base = _to_snake_case(controller_class_name.removesuffix("Controller"))
        controller_base = _singularize_snake_name(controller_base)

        plan: dict[tuple[str, str], tuple[str, str]] = {}
        used_names: set[str] = set()

        for key, method_names in occurrences.items():
            status_code, description = key
            shared = len(method_names) > 1
            if shared and controller_base:
                class_name = f"{_to_pascal_case(controller_base)}{_status_code_to_name(status_code)}Error"
            else:
                class_name = f"{_to_pascal_case(method_names[0])}{_status_code_to_name(status_code)}Error"

            if class_name in used_names:
                class_name = f"{_to_pascal_case(method_names[0])}{_status_code_to_name(status_code)}Error"

            used_names.add(class_name)

            lines = [f"class {class_name}(saronia.StatusError[{status_code}]):"]
            if description:
                lines.append(f'    """{description}"""')
            else:
                lines.append("    ...")

            plan[key] = (class_name, "\n".join(lines))

        return plan

    def _generate_parameter_dto(
        self,
        schema: APISchema,
        op: Operation,
        http_method: str,
        method_name: str,
        path_params: list[Parameter],
        query_params: list[Parameter],
        header_params: list[Parameter],
        imports: _Imports,
        request_body_model: str | None = None,
    ) -> str:
        method_prefix = http_method.upper()

        controller_context = ""
        if op.tags:
            controller_context = _to_pascal_case(op.tags[0])
        else:
            path_parts = [p for p in op.path.strip("/").split("/") if p and not p.startswith("{")]

            if path_parts:
                controller_context = _to_pascal_case(path_parts[0])

        clean_method_name = _to_pascal_case(method_name)

        for prefix in ("Get", "Post", "Put", "Patch", "Delete"):
            if clean_method_name.startswith(prefix) and method_prefix.lower() == prefix.lower():
                clean_method_name = clean_method_name[len(prefix) :]
                break

        if controller_context and controller_context != clean_method_name:
            dto_name = f"{method_prefix.capitalize()}{controller_context}{clean_method_name}Signature"
        else:
            dto_name = f"{method_prefix.capitalize()}{clean_method_name}Signature"

        param_counts = {
            "path": len(path_params),
            "query": len(query_params),
            "header": len(header_params),
        }
        dominant_type = max(param_counts, key=param_counts.get) if sum(param_counts.values()) > 0 else "path"  # type: ignore
        decorators: list[str] = []

        if request_body_model:
            decorators.append("@saronia.json")
        elif dominant_type == "query":
            decorators.append("@saronia.query")
        elif dominant_type == "header":
            decorators.append("@saronia.header")
        elif dominant_type == "path":
            decorators.append("@saronia.path")

        fields: list[tuple[str, str | None, bool]] = []

        temp_imports = _Imports(enums_module=".enums")
        temp_imports.bare_third_party("msgspex")

        has_body = request_body_model is not None

        for p in path_params:
            fields.append(self._render_dto_field(p, temp_imports, dominant_type, has_body))

        for p in query_params:
            fields.append(self._render_dto_field(p, temp_imports, dominant_type, has_body))

        for p in header_params:
            fields.append(self._render_dto_field(p, temp_imports, dominant_type, has_body))

        if request_body_model:
            inline_model = None
            for model in schema.models:
                if model.name == request_body_model:
                    inline_model = model
                    break

            if inline_model:
                for field in inline_model.fields:
                    py_name = _to_snake_case(field.name)

                    if keyword.iskeyword(py_name):
                        py_name = py_name + "_"

                    json_name_arg = f', name="{field.name}"' if py_name != field.name else ""
                    hint = None if isinstance(field.type, UnionType) else self._name_hint(field.name, field.type, temp_imports)
                    if hint is not None:
                        base, from_type = hint

                        if field.type.constraints is not None and not field.type.constraints.is_empty():
                            temp_imports.bare_stdlib("typing")
                            temp_imports.bare_third_party("msgspec")
                            meta_args = self._render_meta_args(field.type.constraints)
                            base = f"typing.Annotated[{base}, msgspec.Meta({meta_args})]"

                        t = f"{base} | None" if field.type.nullable else base
                    else:
                        t = self._type_str(field.type, temp_imports)
                        from_type = self._from_input_type(field.type, temp_imports)

                    if from_type:
                        temp_imports.bare_third_party("msgspex")

                        if field.required:
                            converter = f"msgspex.From[{from_type}]"
                            fields.append((f"    {py_name}: {t} = msgspex.field(converter={converter}{json_name_arg})", field.description, True))
                        else:
                            converter = f"msgspex.From[{from_type} | None]"
                            fields.append((f"    {py_name}: {t} | None = msgspex.field(default=None, converter={converter}{json_name_arg})", field.description, True))

                    elif field.required:
                        if json_name_arg:
                            temp_imports.bare_third_party("msgspex")
                            fields.append((f'    {py_name}: {t} = msgspex.field(name="{field.name}")', field.description, True))
                        else:
                            fields.append((f"    {py_name}: {t}", field.description, False))

                    elif json_name_arg:
                        temp_imports.bare_third_party("msgspex")
                        fields.append((f"    {py_name}: {t} | None = msgspex.field(default=None{json_name_arg})", field.description, True))

                    else:
                        fields.append((f"    {py_name}: {t} | None = None", field.description, True))

        fields.sort(key=lambda f: f[2])
        self._parameter_dtos[dto_name] = _SignatureSpec(
            decorators=tuple(decorators),
            fields=tuple(_SignatureFieldSpec(*field) for field in fields),
            imports=temp_imports,
        )
        return dto_name


__all__ = ("PythonGenerator",)
