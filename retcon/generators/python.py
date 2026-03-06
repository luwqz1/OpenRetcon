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
from retcon.schema.paths import Operation, Response
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


def _raw_string(s: str) -> str:
    """Render *s* as a raw Python string literal (``r"..."`` or ``r'...'``).

    Falls back to ``repr`` only when the string contains both quote characters
    or a backslash that would be misinterpreted in a raw literal.
    """
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


def _operation_to_method_name(op: Operation) -> str:
    if op.operation_id:
        return _to_snake_case(op.operation_id)
    path_part = re.sub(r"[^a-zA-Z0-9]+", "_", op.path).strip("_")
    return f"{op.method.lower()}_{path_part}".strip("_")


def _is_error_status(code: str) -> bool:
    try:
        return int(code) >= 400
    except ValueError:
        return False


def _status_to_http_status(code: str) -> str:
    """Convert "404" to "HTTPStatus.NOT_FOUND"."""
    try:
        status = HTTPStatus(int(code))
        return f"HTTPStatus.{status.name}"
    except ValueError:
        return f"HTTPStatus({code})"


def _path_to_group(path: str) -> str:
    """/api/v1/books/{id} -> books."""
    parts = [p for p in path.strip("/").split("/") if p and not p.startswith("{")]
    return parts[-1] if parts else "default"


def _infer_controller_base_path(operations: list[Operation]) -> str:
    """Find the longest common static path prefix for a group of operations."""
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
        rel = full[len(base):]
        return rel if rel else "/"
    return full


def _render_all(names: list[str]) -> str:
    """Render an ``__all__`` tuple for *names*."""
    if not names:
        return ""
    items = "\n".join(f'    "{n}",' for n in names)
    return f"\n\n__all__ = (\n{items}\n)"


def _ruff_format(code: str, filename: str) -> str:
    """Run ruff isort + format on *code* via stdin.

    Returns the formatted code unchanged when ruff is not installed or fails.
    """
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

    # 2. Format
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

    def __init__(self) -> None:
        self._stdlib: dict[str, set[str]] = defaultdict(set)
        self._third_party: dict[str, set[str]] = defaultdict(set)
        self._local: dict[str, set[str]] = defaultdict(set)
        self._bare_stdlib: set[str] = set()
        self._bare_third_party: set[str] = set()

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
        return "\n".join(lines).rstrip() + "\n"


class PythonGenerator(ABCGenerator):
    """Generates Python client code using saronia (controllers) and msgspex (models).

    Parameters
    ----------
    fmt:
        When ``True`` (default), run ``ruff`` import-sorting and formatting on
        every generated file after generation.  Silently skipped when ruff is
        not installed.
    """

    _DATETIME_FORMATS: frozenset[str] = frozenset(("date-time",))
    _FLOAT_FORMATS: frozenset[str | None] = frozenset((None, "float", "float32", "float64", "double"))

    def __init__(self, *, fmt: bool = True) -> None:
        self._fmt = fmt
        # Set during controller file generation to enable local model imports.
        self._controller_error_names: frozenset[str] | None = None

    def generate(self, schema: APISchema) -> dict[str, str]:
        files: dict[str, str] = {}

        # Which models are error models (appear in 4xx/5xx responses)
        error_statuses = self._collect_error_statuses(schema)
        error_names = set(error_statuses)

        # enums.py — schema enums + custom SchemaEnum nodes
        enums = [*schema.enums]
        for node in schema.custom_nodes:
            if isinstance(node, SchemaEnum):
                enums.append(node)
        if enums:
            files["enums.py"] = self._generate_enums_file(enums)

        # objects.py — non-error models + custom Model nodes
        object_models = [m for m in schema.models if m.name not in error_names]
        for node in schema.custom_nodes:
            if isinstance(node, Model) and node.name not in error_names:
                object_models.append(node)
        if object_models:
            files["objects.py"] = self._generate_objects_file(object_models)

        # errors.py — models used in error responses
        error_models = [m for m in schema.models if m.name in error_names]
        for node in schema.custom_nodes:
            if isinstance(node, Model) and node.name in error_names:
                error_models.append(node)
        if error_models:
            files["errors.py"] = self._generate_errors_file(error_models, error_statuses)

        # controllers/<tag>_controller.py
        files.update(self._generate_controller_files(schema, frozenset(error_names)))

        # Truly custom nodes (not Enum / Model)
        for node in schema.custom_nodes:
            if isinstance(node, SchemaEnum | Model):
                continue
            result = self.generate_custom_node(node)
            if result is not None:
                filename = _to_snake_case(type(node).__name__) + ".py"
                files[filename] = result

        # __init__.py files
        files.update(self._generate_init_files(files))

        if self._fmt:
            files = {path: _ruff_format(code, path) for path, code in files.items()}

        return files

    def _generate_init_files(self, files: dict[str, str]) -> dict[str, str]:
        result: dict[str, str] = {}

        # Root __init__.py — import from enums / objects / errors if present
        root_modules = [
            p.removesuffix(".py")
            for p in ("enums.py", "objects.py", "errors.py")
            if p in files
        ]
        if root_modules:
            lines = ["from __future__ import annotations", ""]
            for mod in root_modules:
                lines.append(f"from .{mod} import *")
            result["__init__.py"] = "\n".join(lines) + "\n"

        # controllers/__init__.py — import from every generated controller
        controller_modules = sorted(
            p.removeprefix("controllers/").removesuffix(".py")
            for p in files
            if p.startswith("controllers/") and p.endswith(".py")
        )
        if controller_modules:
            lines = ["from __future__ import annotations", ""]
            for mod in controller_modules:
                lines.append(f"from .{mod} import *")
            result["controllers/__init__.py"] = "\n".join(lines) + "\n"

        return result

    def generate_model(self, model: Model) -> str:
        imports = _Imports()
        imports.third_party("msgspex", "Model")
        body = self._render_model(model, imports)
        return imports.render() + "\n\n" + body + "\n"

    def generate_enum(self, enum: SchemaEnum) -> str:
        imports = _Imports()
        imports.third_party("msgspex", self._enum_base_class(enum))
        imports.third_party("msgspex", "BaseEnumMeta")
        body = self._render_enum(enum)
        return imports.render() + "\n\n" + body + "\n"

    def generate_operation(self, operation: Operation) -> str:
        imports = _Imports()
        imports.third_party("saronia", operation.method.lower())
        imports.third_party("saronia", "APIResult")
        base = _infer_controller_base_path([operation])
        body = self._render_operation(operation, base, imports)
        return imports.render() + "\n\n" + body + "\n"

    def type_to_string(self, type_ref: TypeRef) -> str:
        return self._type_str(type_ref, None)

    def _generate_enums_file(self, enums: list[SchemaEnum]) -> str:
        imports = _Imports()
        imports.third_party("msgspex", "BaseEnumMeta")
        for enum in enums:
            imports.third_party("msgspex", self._enum_base_class(enum))
        parts = [self._render_enum(e) for e in enums]
        all_decl = _render_all([e.name for e in enums])
        return imports.render(future_annotations=False) + "\n\n" + "\n\n\n".join(parts) + all_decl + "\n"

    def _generate_objects_file(self, models: list[Model]) -> str:
        imports = _Imports()
        imports.third_party("msgspex", "Model")
        parts = [self._render_model(m, imports) for m in models]
        all_decl = _render_all([m.name for m in models])
        return imports.render() + "\n\n" + "\n\n\n".join(parts) + all_decl + "\n"

    def _generate_errors_file(
        self,
        models: list[Model],
        error_statuses: dict[str, set[str]],
    ) -> str:
        imports = _Imports()
        imports.stdlib("http", "HTTPStatus")
        imports.third_party("msgspex", "Model")
        imports.third_party("saronia", "StatusError")
        parts = [
            self._render_error_model(m, error_statuses.get(m.name, set()), imports)
            for m in models
        ]
        all_decl = _render_all([m.name for m in models])
        return imports.render() + "\n\n" + "\n\n\n".join(parts) + all_decl + "\n"

    def _generate_controller_files(
        self,
        schema: APISchema,
        error_names: frozenset[str],
    ) -> dict[str, str]:
        groups: dict[str, list[Operation]] = defaultdict(list)
        for endpoint in schema.endpoints:
            for op in endpoint.operations:
                group = op.tags[0] if op.tags else _path_to_group(endpoint.path)
                groups[group].append(op)

        files: dict[str, str] = {}
        for group, ops in groups.items():
            path = f"controllers/{_to_snake_case(group)}_controller.py"
            files[path] = self._generate_controller_file(group, ops, error_names)

        return files

    def _generate_controller_file(
        self,
        group: str,
        operations: list[Operation],
        error_names: frozenset[str],
    ) -> str:
        imports = _Imports()
        imports.third_party("saronia", "API")
        imports.third_party("saronia", "APIResult")

        self._controller_error_names = error_names

        try:
            base_path = _infer_controller_base_path(operations)
            class_name = _to_pascal_case(group) + "Controller"

            method_blocks: list[str] = []
            for op in operations:
                src = self._render_operation(op, base_path, imports)
                indented = "\n".join("    " + line for line in src.splitlines())
                method_blocks.append(indented)
        finally:
            self._controller_error_names = None

        methods = "\n\n".join(method_blocks)
        all_decl = _render_all([class_name])
        body = (
            'api = API.endpoint("")\n\n\n'
            f"@api({base_path!r})\n"
            f"class {class_name}:\n"
            f"{methods}\n"
            f"{all_decl}\n"
        )
        return imports.render(future_annotations=False) + "\n\n" + body

    def _enum_base_class(self, enum: SchemaEnum) -> str:
        """Return 'StrEnum', 'IntEnum', or 'FloatEnum' based on the enum's value types."""
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
        lines.append(f"class {enum.name}({base_class}, metaclass=BaseEnumMeta):")
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
        """Return True if this field will render with a Python-level default (``= ...``).

        Fields with defaults must come after fields without in a class body.
        """
        if not field.required:
            return True  # Option[T] = field(default=..., ...)

        if field.default is not msgspec.UNSET:
            return True  # concrete default value

        if isinstance(field.type, UnionType):
            return True  # Sum[...] = field(converter=...)

        if keyword.iskeyword(field.name):
            return True  # needs field(default=..., name="...")

        if self._from_input_type(field.type, None) is not None:
            return True  # custom type → From converter → field(default=..., converter=...)

        # Name-based hints that add a From converter
        if field.name == "timestamp" and isinstance(field.type, (StringType, IntegerType, NumberType)):
            return True

        return False

    def _render_model(self, model: Model, imports: _Imports) -> str:
        lines: list[str] = []
        lines.append(f"class {model.name}(Model):")

        if model.description:
            lines.append(f'    """{model.description}"""')
            lines.append("")

        if not model.fields:
            lines.append("    pass")
        else:
            sorted_fields = sorted(model.fields, key=self._has_python_default)
            for field in sorted_fields:
                lines.append("    " + self._render_field(field, imports))

        return "\n".join(lines)

    def _render_error_model(
        self,
        model: Model,
        statuses: set[str],
        imports: _Imports,
    ) -> str:
        if statuses:
            status_args = ", ".join(_status_to_http_status(c) for c in sorted(statuses))
            base = f"Model, StatusError[{status_args}]"
        else:
            base = "Model"

        lines: list[str] = []
        lines.append(f"class {model.name}({base}):")

        if model.description:
            lines.append(f'    """{model.description}"""')
            lines.append("")

        if not model.fields:
            lines.append("    pass")

        else:
            sorted_fields = sorted(model.fields, key=self._has_python_default)
            for field in sorted_fields:
                lines.append("    " + self._render_field(field, imports))

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
        """repr() that always uses double quotes for string values."""
        if isinstance(val, str):
            escaped = val.replace("\\", "\\\\").replace('"', '\\"')
            return f'"{escaped}"'
        return repr(val)

    def _render_field(self, field: Field, imports: _Imports) -> str:
        is_union = isinstance(field.type, UnionType)

        # Rename Python keywords (e.g. "from" → "from_") and preserve the JSON name.
        py_name = field.name + "_" if keyword.iskeyword(field.name) else field.name
        # json_name_arg  — used after "..."  e.g. field(..., name="from", converter=...)
        # json_name_lead — used as first kwarg e.g. field(name="from", converter=...)
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
            # Apply constraints and nullable on top of the hinted base type.
            if field.type.constraints is not None and not field.type.constraints.is_empty():
                imports.stdlib("typing", "Annotated")
                imports.bare_third_party("msgspec")
                meta_args = self._render_meta_args(field.type.constraints)
                base = f"Annotated[{base}, msgspec.Meta({meta_args})]"

            type_str = f"{base} | None" if field.type.nullable else base
        else:
            type_str = self._type_str(field.type, imports)
            conv_str = self._type_str(field.type, imports, for_converter=True)
            from_type = self._from_input_type(field.type, imports)

        def _from(ct: str) -> str:
            return f'From["{ct}"]' if needs_quotes else f"From[{ct}]"

        if not field.required:
            imports.third_party("msgspex", "From")
            imports.third_party("msgspex", "field")
            imports.third_party("msgspex.custom_types.option", "Option")

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

            return f"{py_name}: Option[{type_str}] = field(default=...{json_name_arg}, converter={_from(converter_type)})"

        if is_union:
            # Required union: Sum[T1, T2] = field(converter=From[T1 | T2])
            imports.third_party("msgspex", "From")
            imports.third_party("msgspex", "field")
            raw = self._plain_union_str(field.type, imports)  # type: ignore[arg-type]
            default_repr = self._dquote_repr(field.default) if field.default is not msgspec.UNSET else None

            if default_repr is not None:
                return f"{py_name}: {type_str} = field({json_name_lead}converter={_from(raw)}, default={default_repr})"
            return f"{py_name}: {type_str} = field({json_name_lead}converter={_from(raw)})"

        if field.type.nullable:
            if from_type:
                imports.third_party("msgspex", "From")
                imports.third_party("msgspex", "field")
                # type_str already ends with "| None" (added by _type_str for nullable)
                return f"{py_name}: {type_str} = field(default=...{json_name_arg}, converter={_from(f'{from_type} | None')})"

            if field.default is not msgspec.UNSET:
                default_repr = self._dquote_repr(field.default)

                if json_name_arg:
                    imports.third_party("msgspex", "field")
                    return f"{py_name}: {type_str} = field(default={default_repr}{json_name_arg})"
                return f"{py_name}: {type_str} = {default_repr}"

            if json_name_arg:
                imports.third_party("msgspex", "field")
                return f"{py_name}: {type_str} = field(default=...{json_name_arg})"

            return f"{py_name}: {type_str}"

        if from_type:
            imports.third_party("msgspex", "From")
            imports.third_party("msgspex", "field")

            if field.default is not msgspec.UNSET:
                default_repr = self._dquote_repr(field.default)
                return f"{py_name}: {type_str} = field(default={default_repr}{json_name_arg}, converter={_from(from_type)})"

            return f"{py_name}: {type_str} = field(default=...{json_name_arg}, converter={_from(from_type)})"

        if field.default is not msgspec.UNSET:
            default_repr = self._dquote_repr(field.default)
            imports.third_party("msgspex", "field")
            return f"{py_name}: {type_str} = field(default={default_repr}{json_name_arg})"

        if json_name_arg:
            imports.third_party("msgspex", "field")
            return f"{py_name}: {type_str} = field(default=...{json_name_arg})"

        return f"{py_name}: {type_str}"

    def _render_operation(
        self,
        op: Operation,
        base_path: str,
        imports: _Imports,
    ) -> str:
        method = op.method.lower()
        imports.third_party("saronia", method)

        rel_path = _relative_path(base_path, op.path)

        path_params = [p for p in op.parameters if p.location == "path"]
        query_params = [p for p in op.parameters if p.location == "query"]
        header_params = [p for p in op.parameters if p.location == "header"]

        func_params: list[str] = ["self"]

        for p in path_params:
            t = self._type_str(p.type, imports)
            func_params.append(f"{p.name}: {t}")

        for p in query_params:
            t = self._type_str(p.type, imports)
            imports.third_party("saronia.parameters", "Query")
            if p.required:
                func_params.append(f"{p.name}: Query[{t}]")
            else:
                func_params.append(f"{p.name}: Query[{t}] | None = None")

        for p in header_params:
            t = self._type_str(p.type, imports)
            imports.third_party("saronia.parameters", "Header")
            func_params.append(f"{p.name}: Header[{t}]")

        decorator_args: list[str] = [repr(rel_path)]
        if op.request_body is not None and isinstance(op.request_body.type, ModelRef):
            model_name = op.request_body.type.name
            decorator_args.append(model_name)
            if self._controller_error_names is not None:
                module = "..errors" if model_name in self._controller_error_names else "..objects"
                imports.local(module, model_name)

        success_type = self._get_success_type(op.responses, imports)
        error_parts = self._get_error_types(op.responses, imports)
        if error_parts:
            return_type = f"APIResult[{success_type}, {' | '.join(error_parts)}]"
        else:
            return_type = f"APIResult[{success_type}, None]"

        params_str = ", ".join(func_params)
        decorator = f"@{method}({', '.join(decorator_args)})"
        method_name = _operation_to_method_name(op)

        return "\n".join([decorator, f"async def {method_name}({params_str}) -> {return_type}:", "    ..."])

    def _type_str(self, type_ref: TypeRef, imports: _Imports | None, *, for_converter: bool = False) -> str:
        def add_stdlib(module: str, name: str) -> None:
            if imports is not None:
                imports.stdlib(module, name)

        def add_tp(module: str, name: str) -> None:
            if imports is not None:
                imports.third_party(module, name)

        if isinstance(type_ref, StringType):
            fmt = type_ref.format

            if fmt == "date-time":
                add_tp("msgspex.custom_types.datetime", "ISODatetime")
                base = "ISODatetime"
            elif fmt == "date":
                add_stdlib("datetime", "date")
                base = "date"
            elif fmt == "uuid":
                add_stdlib("uuid", "UUID")
                base = "UUID"
            elif fmt == "email":
                add_tp("msgspex.custom_types.email", "Email")
                base = "Email"
            elif fmt == "idn-email":
                add_tp("msgspex.custom_types.email", "IDNEmail")
                base = "IDNEmail"
            elif fmt in ("uri", "url"):
                add_tp("msgspex.custom_types.uri", "URI")
                base = "URI"
            elif fmt == "uri-reference":
                add_tp("msgspex.custom_types.uri", "URIReference")
                base = "URIReference"
            elif fmt == "iri":
                add_tp("msgspex.custom_types.uri", "IRI")
                base = "IRI"
            elif fmt == "iri-reference":
                add_tp("msgspex.custom_types.uri", "IRIReference")
                base = "IRIReference"
            elif fmt == "hostname":
                add_tp("msgspex.custom_types.hostname", "Hostname")
                base = "Hostname"
            elif fmt == "idn-hostname":
                add_tp("msgspex.custom_types.hostname", "IDNHostname")
                base = "IDNHostname"
            elif fmt == "ipv4":
                add_tp("msgspex.custom_types.ip", "IPv4")
                base = "IPv4"
            elif fmt == "ipv6":
                add_tp("msgspex.custom_types.ip", "IPv6")
                base = "IPv6"
            elif fmt == "json-pointer":
                add_tp("msgspex.custom_types.json_pointer", "JsonPointer")
                base = "JsonPointer"
            elif fmt == "relative-json-pointer":
                add_tp("msgspex.custom_types.json_pointer", "RelativeJsonPointer")
                base = "RelativeJsonPointer"
            else:
                base = "str"

        elif isinstance(type_ref, IntegerType):
            fmt = type_ref.format
            if fmt == "int32":
                add_tp("msgspex.custom_types.numeric", "Int32")
                base = "Int32"
            elif fmt == "int64":
                add_tp("msgspex.custom_types.numeric", "Int64")
                base = "Int64"
            else:
                base = "int"

        elif isinstance(type_ref, NumberType):
            fmt = type_ref.format
            if fmt in ("float", "float32"):
                add_tp("msgspex.custom_types.numeric", "Float32")
                base = "Float32"
            elif fmt in ("double", "float64"):
                add_tp("msgspex.custom_types.numeric", "Float64")
                base = "Float64"
            else:
                base = "float"

        elif isinstance(type_ref, BooleanType):
            base = "bool"

        elif isinstance(type_ref, ArrayType):
            base = f"list[{self._type_str(type_ref.item_type, imports)}]"

        elif isinstance(type_ref, MapType):
            base = f"dict[str, {self._type_str(type_ref.value_type, imports)}]"

        elif isinstance(type_ref, UnionType):
            add_tp("kungfu", "Sum")
            variant_parts = [self._type_str(v, imports) for v in type_ref.variants]
            base = f"Sum[{', '.join(variant_parts)}]"

        elif isinstance(type_ref, ModelRef):
            base = type_ref.name
            if imports is not None and self._controller_error_names is not None:
                module = "..errors" if base in self._controller_error_names else "..objects"
                imports.local(module, base)

        elif isinstance(type_ref, EnumRef):
            base = type_ref.name

        elif isinstance(type_ref, AnyType):
            add_stdlib("typing", "Any")
            base = "Any"

        else:
            add_stdlib("typing", "Any")
            base = "Any"

        if not for_converter and type_ref.constraints is not None and not type_ref.constraints.is_empty():
            add_stdlib("typing", "Annotated")
            if imports is not None:
                imports.bare_third_party("msgspec")
            meta_args = self._render_meta_args(type_ref.constraints)
            base = f"Annotated[{base}, msgspec.Meta({meta_args})]"

        return f"{base} | None" if type_ref.nullable else base

    def _plain_union_str(self, type_ref: UnionType, imports: _Imports | None) -> str:
        """Return 'T1 | T2 | ...' without Sum wrapping, for use in From[...] converters."""
        parts = [self._type_str(v, imports, for_converter=True) for v in type_ref.variants]
        return " | ".join(parts)

    def _from_input_type(self, type_ref: TypeRef, imports: _Imports | None) -> str | None:
        """Return the From[...] converter input type, or None if no converter is needed.

        For datetime subtypes returns only the stdlib ``datetime`` base type.
        For other custom msgspex types returns ``base | CustomType`` so both raw
        values and pre-validated instances are accepted.
        """
        def add_tp(module: str, name: str) -> None:
            if imports is not None:
                imports.third_party(module, name)

        if isinstance(type_ref, StringType):
            fmt = type_ref.format
            if fmt in self._DATETIME_FORMATS:
                if imports is not None:
                    imports.stdlib("datetime", "datetime")
                return "str | datetime"
            if fmt == "email":
                add_tp("msgspex.custom_types.email", "Email")
                return "str | Email"
            if fmt == "idn-email":
                add_tp("msgspex.custom_types.email", "IDNEmail")
                return "str | IDNEmail"
            if fmt in ("uri", "url"):
                add_tp("msgspex.custom_types.uri", "URI")
                return "str | URI"
            if fmt == "uri-reference":
                add_tp("msgspex.custom_types.uri", "URIReference")
                return "str | URIReference"
            if fmt == "iri":
                add_tp("msgspex.custom_types.uri", "IRI")
                return "str | IRI"
            if fmt == "iri-reference":
                add_tp("msgspex.custom_types.uri", "IRIReference")
                return "str | IRIReference"
            if fmt == "hostname":
                add_tp("msgspex.custom_types.hostname", "Hostname")
                return "str | Hostname"
            if fmt == "idn-hostname":
                add_tp("msgspex.custom_types.hostname", "IDNHostname")
                return "str | IDNHostname"
            if fmt == "ipv4":
                add_tp("msgspex.custom_types.ip", "IPv4")
                return "str | IPv4"
            if fmt == "ipv6":
                add_tp("msgspex.custom_types.ip", "IPv6")
                return "str | IPv6"
            if fmt == "json-pointer":
                add_tp("msgspex.custom_types.json_pointer", "JsonPointer")
                return "str | JsonPointer"
            if fmt == "relative-json-pointer":
                add_tp("msgspex.custom_types.json_pointer", "RelativeJsonPointer")
                return "str | RelativeJsonPointer"

        if isinstance(type_ref, IntegerType):
            if type_ref.format == "int32":
                add_tp("msgspex.custom_types.numeric", "Int32")
                return "int | Int32"
            if type_ref.format == "int64":
                add_tp("msgspex.custom_types.numeric", "Int64")
                return "int | Int64"

        if isinstance(type_ref, NumberType):
            if type_ref.format == "float32":
                add_tp("msgspex.custom_types.numeric", "Float32")
                return "float | Float32"
            if type_ref.format in ("float64", "double"):
                add_tp("msgspex.custom_types.numeric", "Float64")
                return "float | Float64"

        return None

    def _name_hint(
        self,
        name: str,
        type_ref: TypeRef,
        imports: _Imports,
    ) -> tuple[str, str | None] | None:
        """Return ``(base_type_str, from_type)`` based on field name heuristics.

        Constraints and nullable are applied by the caller on top of *base_type_str*.
        Returns ``None`` when no heuristic applies.
        """
        if name == "date" and isinstance(type_ref, StringType) and type_ref.format is None:
            imports.stdlib("datetime", "date")
            return "date", None

        if name == "timestamp":
            if isinstance(type_ref, StringType) and type_ref.format is None:
                imports.third_party("msgspex.custom_types.datetime", "StringTimestampDatetime")
                imports.stdlib("datetime", "datetime")
                return "StringTimestampDatetime", "str | datetime"

            if isinstance(type_ref, IntegerType) and type_ref.format is None:
                imports.third_party("msgspex.custom_types.datetime", "IntTimestampDatetime")
                imports.stdlib("datetime", "datetime")
                return "IntTimestampDatetime", "int | datetime"

            if isinstance(type_ref, NumberType) and type_ref.format in self._FLOAT_FORMATS:
                imports.third_party("msgspex.custom_types.datetime", "FloatTimestampDatetime")
                imports.stdlib("datetime", "datetime")
                return "FloatTimestampDatetime", "float | datetime"

        return None

    def _render_meta_args(self, c: Constraints) -> str:
        parts: list[str] = []
        for field in msgspec.structs.fields(c):
            val = getattr(c, field.name)
            if val is None:
                continue
            if field.name == "pattern" and isinstance(val, str):
                parts.append(f"pattern={_raw_string(val)}")
            else:
                parts.append(f"{field.name}={val!r}")
        return ", ".join(parts)

    def _collect_error_statuses(self, schema: APISchema) -> dict[str, set[str]]:
        result: dict[str, set[str]] = defaultdict(set)

        for endpoint in schema.endpoints:
            for op in endpoint.operations:
                for resp in op.responses:
                    if _is_error_status(resp.status_code):
                        for type_ref in resp.content.values():
                            if isinstance(type_ref, ModelRef):
                                result[type_ref.name].add(resp.status_code)

        return dict(result)

    def _get_success_type(self, responses: list[Response], imports: _Imports) -> str:
        for resp in responses:
            if resp.status_code.startswith("2"):
                for type_ref in resp.content.values():
                    return self._type_str(type_ref, imports)

        return "None"

    def _get_error_types(self, responses: list[Response], imports: _Imports) -> list[str]:
        seen: set[str] = set()
        types: list[str] = []
        for resp in responses:
            if _is_error_status(resp.status_code):
                for type_ref in resp.content.values():
                    t = self._type_str(type_ref, imports)
                    if t not in seen:
                        seen.add(t)
                        types.append(t)

        return types


__all__ = ("PythonGenerator",)
