import unittest

from retcon.generators.python import _resolve_method_name_conflicts
from retcon.schema.paths import Operation


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


if __name__ == "__main__":
    unittest.main()
