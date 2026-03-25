import json
import unittest

from retcon.generators.python import PythonGenerator
from retcon.schema.pipeline import run_generation_pipeline


class RequiredFieldRenderingTests(unittest.TestCase):
    def test_required_fields_do_not_get_ellipsis_defaults(self) -> None:
        spec = {
            "openapi": "3.1.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {},
            "components": {
                "schemas": {
                    "SampleModel": {
                        "type": "object",
                        "properties": {
                            "createdAt": {"type": "string", "format": "date-time"},
                            "userId": {"type": "string", "format": "uuid"},
                            "displayName": {"type": "string"},
                            "nickname": {"type": "string"},
                        },
                        "required": ["createdAt", "userId", "displayName"],
                    }
                }
            },
        }

        result = run_generation_pipeline(
            json.dumps(spec).encode(),
            PythonGenerator(fmt=False, module_name="api"),
            document_type="json",
        )

        objects_py = result.files["objects.py"]

        self.assertIn("class SampleModel(msgspex.Model, kw_only=True):", objects_py)
        self.assertIn('created_at: msgspex.isodatetime = msgspex.field(name="createdAt", converter=msgspex.From[str | datetime])', objects_py)
        self.assertIn('user_id: UUID = msgspex.field(name="userId", converter=msgspex.From[str | UUID])', objects_py)
        self.assertIn('display_name: str = msgspex.field(name="displayName")', objects_py)
        self.assertIn('nickname: msgspex.Option[str] = msgspex.field(default=..., converter=msgspex.From[str | None])', objects_py)
        self.assertNotIn('created_at: msgspex.isodatetime = msgspex.field(default=..., name="createdAt"', objects_py)
        self.assertNotIn('user_id: UUID = msgspex.field(default=..., name="userId"', objects_py)
        self.assertNotIn('display_name: str = msgspex.field(default=..., name="displayName")', objects_py)
        self.assertLess(objects_py.index('created_at: msgspex.isodatetime = msgspex.field(name="createdAt", converter=msgspex.From[str | datetime])'), objects_py.index('nickname: msgspex.Option[str] = msgspex.field(default=..., converter=msgspex.From[str | None])'))

    def test_required_dto_fields_do_not_get_ellipsis_defaults(self) -> None:
        spec = {
            "openapi": "3.1.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/items/{itemId}": {
                    "post": {
                        "operationId": "createItem",
                        "parameters": [
                            {
                                "name": "itemId",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"},
                            },
                            {
                                "name": "clientType",
                                "in": "query",
                                "required": True,
                                "schema": {"type": "string"},
                            },
                            {
                                "name": "traceId",
                                "in": "header",
                                "required": False,
                                "schema": {"type": "string"},
                            },
                        ],
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "createdAt": {"type": "string", "format": "date-time"},
                                            "displayName": {"type": "string"},
                                            "nickname": {"type": "string"},
                                        },
                                        "required": ["createdAt", "displayName"],
                                    }
                                }
                            },
                        },
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }

        result = run_generation_pipeline(
            json.dumps(spec).encode(),
            PythonGenerator(fmt=False, module_name="api"),
            document_type="json",
        )

        dto_py = result.files["signatures.py"]

        self.assertIn("class PostItemsCreateItemSignature(msgspex.Model, kw_only=True):", dto_py)
        self.assertIn('item_id: saronia.Path[str] = msgspex.field(name="itemId")', dto_py)
        self.assertIn('client_type: saronia.Query[str] = msgspex.field(name="clientType")', dto_py)
        self.assertIn('created_at: msgspex.isodatetime = msgspex.field(converter=msgspex.From[str | datetime], name="createdAt")', dto_py)
        self.assertIn('display_name: str = msgspex.field(name="displayName")', dto_py)
        self.assertIn('trace_id: saronia.Header[str] | None = msgspex.field(default=None, name="traceId")', dto_py)
        self.assertIn('nickname: str | None = None', dto_py)
        self.assertNotIn('default=..., name="itemId"', dto_py)
        self.assertNotIn('default=..., name="clientType"', dto_py)
        self.assertNotIn('default=..., name="createdAt"', dto_py)
        self.assertNotIn('default=..., name="displayName"', dto_py)

    def test_dto_parameter_fields_use_msgspex_deprecated_annotation(self) -> None:
        spec = {
            "openapi": "3.1.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/items/{itemId}": {
                    "post": {
                        "operationId": "createItem",
                        "parameters": [
                            {
                                "name": "itemId",
                                "in": "path",
                                "required": True,
                                "deprecated": True,
                                "description": "Use item_id instead.",
                                "schema": {"type": "string"},
                            },
                            {
                                "name": "clientType",
                                "in": "query",
                                "required": True,
                                "deprecated": True,
                                "schema": {"type": "string"},
                            },
                            {
                                "name": "traceId",
                                "in": "header",
                                "required": False,
                                "schema": {"type": "string"},
                            },
                        ],
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "createdAt": {"type": "string", "format": "date-time"},
                                            "displayName": {"type": "string"},
                                        },
                                        "required": ["createdAt", "displayName"],
                                    }
                                }
                            },
                        },
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }

        result = run_generation_pipeline(
            json.dumps(spec).encode(),
            PythonGenerator(fmt=False, module_name="api"),
            document_type="json",
        )

        dto_py = result.files["signatures.py"]

        self.assertIn(
            'item_id: msgspex.Deprecated[saronia.Path[str], "Use item_id instead."] = msgspex.field(name="itemId")',
            dto_py,
        )
        self.assertIn(
            'client_type: msgspex.Deprecated[saronia.Query[str], ...] = msgspex.field(name="clientType")',
            dto_py,
        )

    def test_required_converted_fields_sort_before_defaulted_fields(self) -> None:
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {},
            "components": {
                "schemas": {
                    "SortedModel": {
                        "type": "object",
                        "properties": {
                            "plainName": {"type": "string"},
                            "createdAt": {"type": "string", "format": "date-time"},
                            "userId": {"type": "string", "format": "uuid"},
                            "nickname": {"type": "string"},
                            "comment": {"type": "string", "nullable": True},
                        },
                        "required": ["plainName", "createdAt", "userId"],
                    }
                }
            },
        }

        result = run_generation_pipeline(
            json.dumps(spec).encode(),
            PythonGenerator(fmt=False, module_name="api"),
            document_type="json",
        )

        objects_py = result.files["objects.py"]
        plain_idx = objects_py.index("plain_name: str = msgspex.field(name=\"plainName\")")
        created_idx = objects_py.index("created_at: msgspex.isodatetime = msgspex.field(name=\"createdAt\", converter=msgspex.From[str | datetime])")
        user_idx = objects_py.index("user_id: UUID = msgspex.field(name=\"userId\", converter=msgspex.From[str | UUID])")
        nickname_idx = objects_py.index("nickname: msgspex.Option[str] = msgspex.field(default=..., converter=msgspex.From[str | None])")
        comment_idx = objects_py.index("comment: msgspex.NullableOption[str] = msgspex.field(default=NOTHING, converter=msgspex.From[str | None])")

        self.assertLess(plain_idx, nickname_idx)
        self.assertLess(created_idx, nickname_idx)
        self.assertLess(user_idx, nickname_idx)
        self.assertLess(plain_idx, comment_idx)
        self.assertLess(created_idx, comment_idx)
        self.assertLess(user_idx, comment_idx)

    def test_required_converted_fields_without_name_or_default_use_msgspex_field(self) -> None:
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {},
            "components": {
                "schemas": {
                    "ConverterModel": {
                        "type": "object",
                        "properties": {
                            "uuid": {"type": "string", "format": "uuid"},
                            "timestamp": {"type": "string", "format": "date-time"},
                            "score": {"type": "number"},
                        },
                        "required": ["uuid", "timestamp", "score"],
                    }
                }
            },
        }

        result = run_generation_pipeline(
            json.dumps(spec).encode(),
            PythonGenerator(fmt=False, module_name="api"),
            document_type="json",
        )

        objects_py = result.files["objects.py"]

        self.assertIn('uuid: UUID = msgspex.field(converter=msgspex.From[str | UUID])', objects_py)
        self.assertIn('timestamp: msgspex.isodatetime = msgspex.field(converter=msgspex.From[str | datetime])', objects_py)
        self.assertIn("score: int", objects_py)

    def test_integer_type_is_not_changed_by_float_examples(self) -> None:
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "components": {
                "schemas": {
                    "CounterModel": {
                        "type": "object",
                        "properties": {
                            "count": {
                                "type": "integer",
                                "examples": [1.5, 2.5],
                            }
                        },
                        "required": ["count"],
                    }
                }
            },
            "paths": {},
        }

        result = run_generation_pipeline(
            json.dumps(spec).encode(),
            PythonGenerator(fmt=False, module_name="api"),
            document_type="json",
        )

        objects_py = result.files["objects.py"]

        self.assertIn("count: int", objects_py)
        self.assertNotIn("count: float", objects_py)

    def test_number_without_format_uses_int_and_float_formats_use_float(self) -> None:
        spec = {
            "openapi": "3.1.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "components": {
                "schemas": {
                    "NumericModel": {
                        "type": "object",
                        "properties": {
                            "plain_number": {"type": "number"},
                            "example_float_number": {"type": "number", "examples": [1.5, 2.5]},
                            "bounded_float_number": {"type": "number", "minimum": 1.5},
                            "example_priority_number": {"type": "number", "examples": [1], "minimum": 1.5},
                            "float_number": {"type": "number", "format": "float"},
                            "double_number": {"type": "number", "format": "double"},
                        },
                        "required": [
                            "plain_number",
                            "example_float_number",
                            "bounded_float_number",
                            "example_priority_number",
                            "float_number",
                            "double_number",
                        ],
                    }
                }
            },
            "paths": {},
        }

        result = run_generation_pipeline(
            json.dumps(spec).encode(),
            PythonGenerator(fmt=False, module_name="api"),
            document_type="json",
        )

        objects_py = result.files["objects.py"]

        self.assertIn("plain_number: int", objects_py)
        self.assertIn("example_float_number: float", objects_py)
        self.assertIn("bounded_float_number: typing.Annotated[float, msgspec.Meta(ge=1.5)]", objects_py)
        self.assertIn("example_priority_number: typing.Annotated[int, msgspec.Meta(ge=1.5)]", objects_py)
        self.assertIn("float_number: msgspex.Float32", objects_py)
        self.assertIn("double_number: msgspex.Float64", objects_py)

    def test_identical_enums_are_deduplicated_with_generalized_name(self) -> None:
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "components": {
                "schemas": {
                    "CreateConfigProfileStatus": {
                        "type": "string",
                        "enum": ["active", "disabled"],
                    },
                    "UpdateConfigProfileStatus": {
                        "type": "string",
                        "enum": ["active", "disabled"],
                    },
                    "ConfigProfileModel": {
                        "type": "object",
                        "properties": {
                            "createStatus": {"$ref": "#/components/schemas/CreateConfigProfileStatus"},
                            "updateStatus": {"$ref": "#/components/schemas/UpdateConfigProfileStatus"},
                        },
                        "required": ["createStatus", "updateStatus"],
                    },
                }
            },
            "paths": {},
        }

        result = run_generation_pipeline(
            json.dumps(spec).encode(),
            PythonGenerator(fmt=False, module_name="api"),
            document_type="json",
        )

        enums_py = result.files["enums.py"]
        objects_py = result.files["objects.py"]

        self.assertIn("class ConfigProfileStatus(", enums_py)
        self.assertNotIn("class CreateConfigProfileStatus(", enums_py)
        self.assertNotIn("class UpdateConfigProfileStatus(", enums_py)
        self.assertIn("create_status: ConfigProfileStatus", objects_py)
        self.assertIn("update_status: ConfigProfileStatus", objects_py)

    def test_shared_prefix_fields_are_extracted_into_object_base_model(self) -> None:
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "components": {
                "schemas": {
                    "CreateConfigProfileDto": {
                        "type": "object",
                        "properties": {
                            "uuid": {"type": "string", "format": "uuid"},
                            "name": {"type": "string"},
                            "createdAt": {"type": "string", "format": "date-time"},
                            "createOnly": {"type": "string"},
                        },
                        "required": ["uuid", "name", "createdAt", "createOnly"],
                    },
                    "UpdateConfigProfileDto": {
                        "type": "object",
                        "properties": {
                            "uuid": {"type": "string", "format": "uuid"},
                            "name": {"type": "string"},
                            "createdAt": {"type": "string", "format": "date-time"},
                            "updateOnly": {"type": "string"},
                        },
                        "required": ["uuid", "name", "createdAt", "updateOnly"],
                    },
                }
            },
            "paths": {},
        }

        result = run_generation_pipeline(
            json.dumps(spec).encode(),
            PythonGenerator(fmt=False, module_name="api"),
            document_type="json",
        )

        objects_py = result.files["objects.py"]

        self.assertIn("class ConfigProfileBase(msgspex.Model, kw_only=True):", objects_py)
        self.assertIn("class CreateConfigProfileDto(ConfigProfileBase, kw_only=True):", objects_py)
        self.assertIn("class UpdateConfigProfileDto(ConfigProfileBase, kw_only=True):", objects_py)

    def test_required_dto_converted_fields_without_name_or_default_use_msgspex_field(self) -> None:
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/events": {
                    "get": {
                        "operationId": "getEvents",
                        "parameters": [
                            {
                                "name": "timestamp",
                                "in": "query",
                                "required": True,
                                "schema": {"type": "string", "format": "date-time"},
                            },
                            {
                                "name": "uuid",
                                "in": "header",
                                "required": True,
                                "schema": {"type": "string", "format": "uuid"},
                            },
                            {
                                "name": "limit",
                                "in": "query",
                                "required": False,
                                "schema": {"type": "integer"},
                            },
                            {
                                "name": "offset",
                                "in": "query",
                                "required": False,
                                "schema": {"type": "integer"},
                            },
                            {
                                "name": "page",
                                "in": "query",
                                "required": False,
                                "schema": {"type": "integer"},
                            },
                        ],
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }

        result = run_generation_pipeline(
            json.dumps(spec).encode(),
            PythonGenerator(fmt=False, module_name="api"),
            document_type="json",
        )

        dto_py = result.files["signatures.py"]

        self.assertIn('timestamp: msgspex.isodatetime = msgspex.field(converter=msgspex.From[str | datetime])', dto_py)
        self.assertIn('uuid: saronia.Header[UUID] = msgspex.field(converter=msgspex.From[str | UUID])', dto_py)

    def test_special_date_name_uses_date_converter_in_model(self) -> None:
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {},
            "components": {
                "schemas": {
                    "DateModel": {
                        "type": "object",
                        "properties": {
                            "date": {"type": "string"},
                        },
                        "required": ["date"],
                    }
                }
            },
        }

        result = run_generation_pipeline(
            json.dumps(spec).encode(),
            PythonGenerator(fmt=False, module_name="api"),
            document_type="json",
        )

        objects_py = result.files["objects.py"]
        self.assertIn('date: date = msgspex.field(converter=msgspex.From[str | date])', objects_py)

    def test_special_uuid_name_uses_uuid_converter_in_model(self) -> None:
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {},
            "components": {
                "schemas": {
                    "UuidModel": {
                        "type": "object",
                        "properties": {
                            "uuid": {"type": "string"},
                        },
                        "required": ["uuid"],
                    }
                }
            },
        }

        result = run_generation_pipeline(
            json.dumps(spec).encode(),
            PythonGenerator(fmt=False, module_name="api"),
            document_type="json",
        )

        objects_py = result.files["objects.py"]
        self.assertIn('uuid: UUID = msgspex.field(converter=msgspex.From[str | UUID])', objects_py)

    def test_special_date_name_uses_date_converter_in_dto(self) -> None:
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/reports": {
                    "get": {
                        "operationId": "getReports",
                        "parameters": [
                            {
                                "name": "date",
                                "in": "query",
                                "required": True,
                                "schema": {"type": "string"},
                            },
                            {
                                "name": "limit",
                                "in": "query",
                                "required": False,
                                "schema": {"type": "integer"},
                            },
                            {
                                "name": "offset",
                                "in": "query",
                                "required": False,
                                "schema": {"type": "integer"},
                            },
                            {
                                "name": "page",
                                "in": "query",
                                "required": False,
                                "schema": {"type": "integer"},
                            },
                        ],
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }

        result = run_generation_pipeline(
            json.dumps(spec).encode(),
            PythonGenerator(fmt=False, module_name="api"),
            document_type="json",
        )

        dto_py = result.files["signatures.py"]
        self.assertIn('date: date = msgspex.field(converter=msgspex.From[str | date])', dto_py)

    def test_special_uuid_name_uses_uuid_converter_in_dto(self) -> None:
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/reports": {
                    "get": {
                        "operationId": "getReports",
                        "parameters": [
                            {
                                "name": "uuid",
                                "in": "query",
                                "required": True,
                                "schema": {"type": "string"},
                            },
                            {
                                "name": "limit",
                                "in": "query",
                                "required": False,
                                "schema": {"type": "integer"},
                            },
                            {
                                "name": "offset",
                                "in": "query",
                                "required": False,
                                "schema": {"type": "integer"},
                            },
                            {
                                "name": "page",
                                "in": "query",
                                "required": False,
                                "schema": {"type": "integer"},
                            },
                        ],
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }

        result = run_generation_pipeline(
            json.dumps(spec).encode(),
            PythonGenerator(fmt=False, module_name="api"),
            document_type="json",
        )

        dto_py = result.files["signatures.py"]
        self.assertIn('uuid: UUID = msgspex.field(converter=msgspex.From[str | UUID])', dto_py)

    def test_shared_prefix_fields_are_extracted_into_signature_base_model(self) -> None:
        spec = {
            "openapi": "3.1.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/bandwidth-stats/user-usage-by-range": {
                    "get": {
                        "tags": ["BandwidthStatsController"],
                        "operationId": "getUserUsageByRange",
                        "parameters": [
                            {"name": "startAt", "in": "query", "required": True, "schema": {"type": "string", "format": "date-time"}},
                            {"name": "endAt", "in": "query", "required": True, "schema": {"type": "string", "format": "date-time"}},
                            {"name": "nodeId", "in": "query", "required": False, "schema": {"type": "string", "format": "uuid"}},
                            {"name": "userId", "in": "query", "required": False, "schema": {"type": "string", "format": "uuid"}},
                        ],
                        "responses": {"200": {"description": "ok"}},
                    }
                },
                "/bandwidth-stats/users-get-stats-nodes-usage": {
                    "get": {
                        "tags": ["BandwidthStatsController"],
                        "operationId": "getUsersGetStatsNodesUsage",
                        "parameters": [
                            {"name": "startAt", "in": "query", "required": True, "schema": {"type": "string", "format": "date-time"}},
                            {"name": "endAt", "in": "query", "required": True, "schema": {"type": "string", "format": "date-time"}},
                            {"name": "nodeId", "in": "query", "required": False, "schema": {"type": "string", "format": "uuid"}},
                            {"name": "hostId", "in": "query", "required": False, "schema": {"type": "string", "format": "uuid"}},
                        ],
                        "responses": {"200": {"description": "ok"}},
                    }
                },
            },
        }

        result = run_generation_pipeline(
            json.dumps(spec).encode(),
            PythonGenerator(fmt=False, module_name="api"),
            document_type="json",
        )

        dto_py = result.files["signatures.py"]

        self.assertIn("class BandwidthStatsBase(msgspex.Model, kw_only=True):", dto_py)
        self.assertIn("class GetBandwidthStatsControllerUserUsageByRangeSignature(BandwidthStatsBase, kw_only=True):", dto_py)
        self.assertIn("class GetBandwidthStatsControllerUsersGetStatsNodesUsageSignature(BandwidthStatsBase, kw_only=True):", dto_py)

    def test_shared_signature_fields_are_extracted_even_when_not_contiguous(self) -> None:
        spec = {
            "openapi": "3.1.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/bandwidth-stats/users/{uuid}/legacy": {
                    "get": {
                        "tags": ["BandwidthStatsController"],
                        "operationId": "getUserUsageByRange",
                        "parameters": [
                            {"name": "uuid", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}},
                            {"name": "start", "in": "query", "required": True, "schema": {"type": "string", "format": "date-time"}},
                            {"name": "end", "in": "query", "required": True, "schema": {"type": "string", "format": "date-time"}},
                            {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer"}},
                        ],
                        "responses": {"200": {"description": "ok"}},
                    }
                },
                "/bandwidth-stats/users/{uuid}": {
                    "get": {
                        "tags": ["BandwidthStatsController"],
                        "operationId": "getUsersGetStatsNodesUsage",
                        "parameters": [
                            {"name": "uuid", "in": "path", "required": True, "schema": {"type": "string", "format": "uuid"}},
                            {"name": "topNodesLimit", "in": "query", "required": True, "schema": {"type": "integer"}},
                            {"name": "start", "in": "query", "required": True, "schema": {"type": "string", "format": "date-time"}},
                            {"name": "end", "in": "query", "required": True, "schema": {"type": "string", "format": "date-time"}},
                        ],
                        "responses": {"200": {"description": "ok"}},
                    }
                },
            },
        }

        result = run_generation_pipeline(
            json.dumps(spec).encode(),
            PythonGenerator(fmt=False, module_name="api"),
            document_type="json",
        )

        dto_py = result.files["signatures.py"]

        self.assertIn("class BandwidthStatsBase(msgspex.Model, kw_only=True):", dto_py)
        self.assertIn("uuid: saronia.Path[UUID]", dto_py)
        self.assertIn("start: msgspex.isodatetime", dto_py)
        self.assertIn("end: msgspex.isodatetime", dto_py)
        self.assertIn("class GetBandwidthStatsControllerUserUsageByRangeSignature(BandwidthStatsBase, kw_only=True):", dto_py)
        self.assertIn("class GetBandwidthStatsControllerUsersGetStatsNodesUsageSignature(BandwidthStatsBase, kw_only=True):", dto_py)

    def test_list_converter_uses_inner_uuid_input_type(self) -> None:
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {},
            "components": {
                "schemas": {
                    "ListModel": {
                        "type": "object",
                        "properties": {
                            "uuids": {
                                "type": "array",
                                "items": {"type": "string", "format": "uuid"},
                            },
                            "optionalUuids": {
                                "type": "array",
                                "items": {"type": "string", "format": "uuid"},
                            },
                            "dates": {
                                "type": "array",
                                "items": {"type": "string", "format": "date"},
                            },
                        },
                        "required": ["uuids", "dates"],
                    }
                }
            },
        }

        result = run_generation_pipeline(
            json.dumps(spec).encode(),
            PythonGenerator(fmt=False, module_name="api"),
            document_type="json",
        )

        objects_py = result.files["objects.py"]
        self.assertIn('uuids: list[UUID] = msgspex.field(converter=msgspex.From[list[str | UUID]])', objects_py)
        self.assertIn('optional_uuids: msgspex.Option[list[UUID]] = msgspex.field(default=..., name="optionalUuids", converter=msgspex.From[list[str | UUID] | None])', objects_py)
        self.assertIn('dates: list[date] = msgspex.field(converter=msgspex.From[list[str | date]])', objects_py)

    def test_list_converter_uses_inner_uuid_input_type_in_dto(self) -> None:
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/bulk": {
                    "post": {
                        "operationId": "postBulk",
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "uuids": {
                                                "type": "array",
                                                "items": {"type": "string", "format": "uuid"},
                                            },
                                            "dates": {
                                                "type": "array",
                                                "items": {"type": "string", "format": "date"},
                                            },
                                        },
                                        "required": ["uuids", "dates"],
                                    }
                                }
                            },
                        },
                        "parameters": [
                            {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer"}},
                            {"name": "offset", "in": "query", "required": False, "schema": {"type": "integer"}},
                            {"name": "page", "in": "query", "required": False, "schema": {"type": "integer"}},
                            {"name": "sort", "in": "query", "required": False, "schema": {"type": "string"}},
                        ],
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }

        result = run_generation_pipeline(
            json.dumps(spec).encode(),
            PythonGenerator(fmt=False, module_name="api"),
            document_type="json",
        )

        dto_py = result.files["signatures.py"]
        self.assertIn('uuids: list[UUID] = msgspex.field(converter=msgspex.From[list[str | UUID]])', dto_py)
        self.assertIn('dates: list[date] = msgspex.field(converter=msgspex.From[list[str | date]])', dto_py)

    def test_controller_signatures_use_param_for_non_snake_case_names(self) -> None:
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/items/{itemId}": {
                    "get": {
                        "operationId": "getItem",
                        "parameters": [
                            {
                                "name": "itemId",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string", "format": "uuid"},
                            },
                            {
                                "name": "maxValue",
                                "in": "query",
                                "required": False,
                                "schema": {"type": "integer"},
                            },
                            {
                                "name": "trace_id",
                                "in": "header",
                                "required": True,
                                "schema": {"type": "string"},
                            },
                        ],
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }

        result = run_generation_pipeline(
            json.dumps(spec).encode(),
            PythonGenerator(fmt=False, module_name="api"),
            document_type="json",
        )

        controller_py = result.files["controllers/items_controller.py"]

        self.assertIn("@saronia.get('/{itemId}')", controller_py)
        self.assertIn('item_id: saronia.Param[UUID, saronia.Path, "itemId"]', controller_py)
        self.assertIn('max_value: saronia.Param[int | None, saronia.Query, "maxValue"] = None', controller_py)
        self.assertIn("trace_id: saronia.Header[str]", controller_py)
        self.assertIn('async def get_item(self, *, item_id: saronia.Param[UUID, saronia.Path, "itemId"], max_value: saronia.Param[int | None, saronia.Query, "maxValue"] = None, trace_id: saronia.Header[str],)', controller_py)

    def test_controller_signatures_use_plain_types_for_dominant_query_params_without_alias(self) -> None:
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/items": {
                    "get": {
                        "operationId": "listItems",
                        "parameters": [
                            {
                                "name": "limit",
                                "in": "query",
                                "required": False,
                                "schema": {"type": "integer"},
                            },
                            {
                                "name": "offset",
                                "in": "query",
                                "required": False,
                                "schema": {"type": "integer"},
                            },
                            {
                                "name": "traceId",
                                "in": "header",
                                "required": False,
                                "schema": {"type": "string"},
                            },
                        ],
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }

        result = run_generation_pipeline(
            json.dumps(spec).encode(),
            PythonGenerator(fmt=False, module_name="api"),
            document_type="json",
        )

        controller_py = result.files["controllers/items_controller.py"]

        self.assertIn("@saronia.get('/', query=True)", controller_py)
        self.assertIn("async def list_items(self, *, limit: int | None = None, offset: int | None = None, trace_id: saronia.Param[str | None, saronia.Header, \"traceId\"] = None,)", controller_py)
        self.assertIn("limit: int | None = None", controller_py)
        self.assertIn("offset: int | None = None", controller_py)
        self.assertNotIn("limit: saronia.Query[int]", controller_py)
        self.assertNotIn("offset: saronia.Query[int]", controller_py)
        self.assertIn('trace_id: saronia.Param[str | None, saronia.Header, "traceId"] = None', controller_py)

    def test_controller_signature_uses_uuid_type_from_name_hint_without_format(self) -> None:
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/items/{uuid}": {
                    "get": {
                        "operationId": "getItemByUuid",
                        "parameters": [
                            {
                                "name": "uuid",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"},
                            }
                        ],
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }

        result = run_generation_pipeline(
            json.dumps(spec).encode(),
            PythonGenerator(fmt=False, module_name="api"),
            document_type="json",
        )

        controller_py = result.files["controllers/items_controller.py"]

        self.assertIn("from uuid import UUID", controller_py)
        self.assertIn("@saronia.get('/{uuid}')", controller_py)
        self.assertIn("uuid: UUID", controller_py)

    def test_controller_signature_uses_deprecated_metadata_with_and_without_alias(self) -> None:
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/items/{itemId}": {
                    "get": {
                        "operationId": "getItem",
                        "parameters": [
                            {
                                "name": "itemId",
                                "in": "path",
                                "required": True,
                                "deprecated": True,
                                "description": "Use item_id instead.",
                                "schema": {"type": "string"},
                            },
                            {
                                "name": "limit",
                                "in": "query",
                                "required": False,
                                "deprecated": True,
                                "schema": {"type": "integer"},
                            },
                        ],
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }

        result = run_generation_pipeline(
            json.dumps(spec).encode(),
            PythonGenerator(fmt=False, module_name="api"),
            document_type="json",
        )

        controller_py = result.files["controllers/items_controller.py"]

        self.assertIn(
            'item_id: saronia.Param[str, saronia.Path, "itemId", saronia.Deprecated("Use item_id instead.")]',
            controller_py,
        )
        self.assertIn(
            "limit: saronia.Param[int | None, saronia.Query, saronia.Deprecated()] = None",
            controller_py,
        )

    def test_route_deprecated_decorator_is_used_and_param_deprecation_is_ignored(self) -> None:
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/items/{itemId}": {
                    "get": {
                        "operationId": "getItem",
                        "deprecated": True,
                        "description": "Use /v2/items/{itemId}.",
                        "parameters": [
                            {
                                "name": "itemId",
                                "in": "path",
                                "required": True,
                                "deprecated": True,
                                "description": "Legacy id.",
                                "schema": {"type": "string"},
                            },
                            {
                                "name": "limit",
                                "in": "query",
                                "required": False,
                                "deprecated": True,
                                "description": "Legacy limit.",
                                "schema": {"type": "integer"},
                            },
                        ],
                        "responses": {"200": {"description": "ok"}},
                    }
                }
            },
        }

        result = run_generation_pipeline(
            json.dumps(spec).encode(),
            PythonGenerator(fmt=False, module_name="api"),
            document_type="json",
        )

        controller_py = result.files["controllers/items_controller.py"]

        self.assertIn('@saronia.route_deprecated("Use /v2/items/{itemId}.")', controller_py)
        self.assertIn('item_id: saronia.Param[str, saronia.Path, "itemId"]', controller_py)
        self.assertIn("limit: saronia.Query[int] | None = None", controller_py)
        self.assertNotIn("saronia.Deprecated(", controller_py)


if __name__ == "__main__":
    unittest.main()
