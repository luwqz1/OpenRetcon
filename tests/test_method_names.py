import json
import unittest

from retcon.generators.python import PythonGenerator, _resolve_method_name_conflicts
from retcon.schema.paths import Operation
from retcon.schema.pipeline import run_generation_pipeline


class MethodNameConflictTests(unittest.TestCase):
    def test_operation_id_conflicts_use_route_prefixes(self) -> None:
        operations = [
            Operation(
                method="get",
                path="/api/bandwidth-stats/users/{uuid}",
                operation_id="BandwidthStatsUsersController_getStatsNodesUsage",
                summary=None,
                description=None,
                tags=[],
                parameters=[],
                request_body=None,
                responses=[],
                deprecated=False,
                security_requirements=[],
            ),
            Operation(
                method="get",
                path="/api/bandwidth-stats/nodes",
                operation_id="NodesUsageHistoryController_getStatsNodesUsage",
                summary=None,
                description=None,
                tags=[],
                parameters=[],
                request_body=None,
                responses=[],
                deprecated=False,
                security_requirements=[],
            ),
        ]

        names = _resolve_method_name_conflicts(operations, "/api/bandwidth-stats")

        self.assertEqual(names[id(operations[0])], "users_get_stats_nodes_usage")
        self.assertEqual(names[id(operations[1])], "nodes_get_stats_nodes_usage")

    def test_controller_method_without_params_does_not_generate_star_self(self) -> None:
        spec = {
            "openapi": "3.1.0",
            "info": {"title": "Test API", "version": "1.0.0"},
            "paths": {
                "/health": {
                    "get": {
                        "operationId": "getHealth",
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

        controller_py = result.files["controllers/health_controller.py"]

        self.assertIn("async def get_health(self) -> saronia.APIResult[None]:", controller_py)
        self.assertNotIn("*self", controller_py)


if __name__ == "__main__":
    unittest.main()
