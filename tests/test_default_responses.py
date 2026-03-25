import json
import unittest

from retcon.generators.python import PythonGenerator
from retcon.schema.pipeline import run_generation_pipeline


class DefaultResponsesTests(unittest.TestCase):
    def test_default_response_models_are_generated_in_responses_and_used_by_controllers(self) -> None:
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/auth/options": {
                    "get": {
                        "operationId": "getAuthenticationOptions",
                        "responses": {
                            "500": {
                                "description": "Server error",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "message": {"type": "string"},
                                            },
                                        }
                                    }
                                },
                            },
                            "default": {
                                "description": "Authentication options",
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/GetAuthenticationOptionsResponseDto"}
                                    }
                                },
                            },
                        },
                    }
                },
                "/auth/inline-options": {
                    "get": {
                        "operationId": "getInlineAuthenticationOptions",
                        "responses": {
                            "default": {
                                "description": "Inline authentication options",
                                "content": {
                                    "application/json": {
                                        "schema": {
                                            "type": "object",
                                            "properties": {
                                                "token": {"type": "string"},
                                            },
                                            "required": ["token"],
                                        }
                                    }
                                },
                            }
                        },
                    }
                },
            },
            "components": {
                "schemas": {
                    "GetAuthenticationOptionsResponseDto": {
                        "type": "object",
                        "properties": {
                            "challenge": {"type": "string"},
                        },
                        "required": ["challenge"],
                    }
                }
            },
        }

        result = run_generation_pipeline(
            json.dumps(spec).encode(),
            PythonGenerator(fmt=False, module_name="api"),
            document_type="json",
        )

        responses_py = result.files["responses.py"]
        controller_options_py = result.files["controllers/options_controller.py"]
        controller_inline_options_py = result.files["controllers/inline_options_controller.py"]

        self.assertIn("class GetAuthenticationOptionsResponseDto(msgspex.Model, kw_only=True):", responses_py)
        self.assertIn("class InlineAuthenticationOptionsResponse(msgspex.Model, kw_only=True):", responses_py)
        self.assertNotIn("objects.py", result.files)
        self.assertIn("from ..responses import GetAuthenticationOptionsResponseDto", controller_options_py)
        self.assertIn("saronia.APIResult[GetAuthenticationOptionsResponseDto", controller_options_py)
        self.assertIn("from ..responses import InlineAuthenticationOptionsResponse", controller_inline_options_py)
        self.assertIn("saronia.APIResult[InlineAuthenticationOptionsResponse]", controller_inline_options_py)

    def test_description_only_error_responses_render_as_status_error_in_controller(self) -> None:
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/items/{uuid}": {
                    "get": {
                        "operationId": "getItem",
                        "parameters": [
                            {
                                "name": "uuid",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"},
                            }
                        ],
                        "responses": {
                            "200": {"description": "ok"},
                            "404": {
                                "description": "Missing item",
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/GetItemError"}
                                    }
                                },
                            },
                            "405": {"description": ""},
                            "407": {"description": "Proxy authentication required"},
                            "408": {"description": "Request timeout"},
                        },
                    }
                }
            },
            "components": {
                "schemas": {
                    "GetItemError": {
                        "type": "object",
                        "properties": {"message": {"type": "string"}},
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
        errors_py = result.files["errors.py"]

        self.assertIn("from ..errors import GetItemError", controller_py)
        self.assertIn("class GetItemError(msgspex.Model, saronia.ModelStatusError[HTTPStatus.NOT_FOUND], kw_only=True):", errors_py)
        self.assertIn("class GetItemMethodNotAllowedError(saronia.StatusError[405]):", controller_py)
        self.assertIn('class GetItemProxyAuthenticationRequiredError(saronia.StatusError[407]):\n    """Proxy authentication required"""', controller_py)
        self.assertIn('class GetItemRequestTimeoutError(saronia.StatusError[408]):\n    """Request timeout"""', controller_py)
        self.assertIn(
            "saronia.APIResult[None, GetItemError | GetItemMethodNotAllowedError | GetItemProxyAuthenticationRequiredError | GetItemRequestTimeoutError,]",
            controller_py,
        )

    def test_identical_status_only_errors_are_deduplicated_per_controller(self) -> None:
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/config-profiles": {
                    "post": {
                        "operationId": "createConfigProfile",
                        "responses": {
                            "200": {"description": "ok"},
                            "404": {"description": "Profile not found"},
                        },
                    }
                },
                "/config-profiles/{id}": {
                    "patch": {
                        "operationId": "updateConfigProfile",
                        "parameters": [
                            {
                                "name": "id",
                                "in": "path",
                                "required": True,
                                "schema": {"type": "string"},
                            }
                        ],
                        "responses": {
                            "200": {"description": "ok"},
                            "404": {"description": "Profile not found"},
                        },
                    }
                },
            },
        }

        result = run_generation_pipeline(
            json.dumps(spec).encode(),
            PythonGenerator(fmt=False, module_name="api"),
            document_type="json",
        )

        controller_py = result.files["controllers/config_profiles_controller.py"]
        controllers_init_py = result.files["controllers/__init__.py"]

        self.assertIn('class ConfigProfileNotFoundError(saronia.StatusError[404]):\n    """Profile not found"""', controller_py)
        self.assertEqual(controller_py.count("class ConfigProfileNotFoundError("), 1)
        self.assertIn("saronia.APIResult[None, ConfigProfileNotFoundError]", controller_py)
        self.assertIn('"ConfigProfileNotFoundError"', controller_py)
        self.assertIn("from .config_profiles_controller import ConfigProfilesController", controllers_init_py)
        self.assertNotIn("import *", controllers_init_py)

    def test_shared_prefix_fields_are_extracted_into_response_and_error_base_models(self) -> None:
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/profiles/create": {
                    "get": {
                        "operationId": "createConfigProfile",
                        "responses": {
                            "200": {
                                "description": "ok",
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/CreateConfigProfileResponseDto"}
                                    }
                                },
                            },
                            "400": {
                                "description": "bad",
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/CreateConfigProfileError"}
                                    }
                                },
                            },
                        },
                    }
                },
                "/profiles/update": {
                    "get": {
                        "operationId": "updateConfigProfile",
                        "responses": {
                            "200": {
                                "description": "ok",
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/UpdateConfigProfileResponseDto"}
                                    }
                                },
                            },
                            "404": {
                                "description": "missing",
                                "content": {
                                    "application/json": {
                                        "schema": {"$ref": "#/components/schemas/UpdateConfigProfileError"}
                                    }
                                },
                            },
                        },
                    }
                },
            },
            "components": {
                "schemas": {
                    "CreateConfigProfileResponseDto": {
                        "type": "object",
                        "properties": {
                            "uuid": {"type": "string", "format": "uuid"},
                            "name": {"type": "string"},
                            "createdAt": {"type": "string", "format": "date-time"},
                            "createOnly": {"type": "string"},
                        },
                        "required": ["uuid", "name", "createdAt", "createOnly"],
                    },
                    "UpdateConfigProfileResponseDto": {
                        "type": "object",
                        "properties": {
                            "uuid": {"type": "string", "format": "uuid"},
                            "name": {"type": "string"},
                            "createdAt": {"type": "string", "format": "date-time"},
                            "updateOnly": {"type": "string"},
                        },
                        "required": ["uuid", "name", "createdAt", "updateOnly"],
                    },
                    "CreateConfigProfileError": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string"},
                            "message": {"type": "string"},
                            "detailsA": {"type": "string"},
                        },
                        "required": ["code", "message", "detailsA"],
                    },
                    "UpdateConfigProfileError": {
                        "type": "object",
                        "properties": {
                            "code": {"type": "string"},
                            "message": {"type": "string"},
                            "detailsB": {"type": "string"},
                        },
                        "required": ["code", "message", "detailsB"],
                    },
                }
            },
        }

        result = run_generation_pipeline(
            json.dumps(spec).encode(),
            PythonGenerator(fmt=False, module_name="api"),
            document_type="json",
        )

        responses_py = result.files["responses.py"]
        errors_py = result.files["errors.py"]

        self.assertIn("class ConfigProfileBase(msgspex.Model, kw_only=True):", responses_py)
        self.assertIn("class CreateConfigProfileResponseDto(ConfigProfileBase, kw_only=True):", responses_py)
        self.assertIn("class UpdateConfigProfileResponseDto(ConfigProfileBase, kw_only=True):", responses_py)
        self.assertIn("class ConfigProfileBase(msgspex.Model, kw_only=True):", errors_py)
        self.assertIn("class CreateConfigProfileError(ConfigProfileBase, saronia.ModelStatusError[HTTPStatus.BAD_REQUEST], kw_only=True):", errors_py)
        self.assertIn("class UpdateConfigProfileError(ConfigProfileBase, saronia.ModelStatusError[HTTPStatus.NOT_FOUND], kw_only=True):", errors_py)


if __name__ == "__main__":
    unittest.main()
