import unittest

from agent.policy import inspect_policy_request
from agent.workload import inspect_workload_request
from agent.placement import resolve_agent_placement


ENVIRONMENT = {
    "compute": {
        "logical_cpu_count": 20,
        "memory_total_gib": 11.68,
        "gpu": {
            "name": "Test GPU",
            "memory_total_mib": 8192,
            "memory_free_mib": 4096,
        },
    }
}


def evidence(request):
    return {
        "inspect_environment": ENVIRONMENT,
        "inspect_workload": inspect_workload_request(request),
        "inspect_policy": inspect_policy_request(request),
    }


class OperationsMetaAgentRoutingTest(unittest.TestCase):

    def test_policy_unknown_requires_cloud_policy(self):
        result = resolve_agent_placement(
            evidence(
                "This workload requires 4 CPU cores, "
                "requires 4 GB RAM, and is CPU-only."
            )
        )

        self.assertEqual(
            result["decision"],
            "POLICY_INPUT_REQUIRED:CLOUD_REQUIRED",
        )

    def test_small_explicit_local_workload_routes_local(self):
        result = resolve_agent_placement(
            evidence(
                "Cloud is not required. "
                "This workload requires 4 CPU cores, "
                "requires 4 GB RAM, and is CPU-only."
            )
        )

        self.assertEqual(
            result["decision"],
            "LOCAL_PC",
        )

    def test_temporary_capacity_excess_routes_cloud_burst(self):
        result = resolve_agent_placement(
            evidence(
                "Cloud is not required. "
                "This is a one-off capacity spike. "
                "This workload requires 40 CPU cores, "
                "requires 32 GB RAM, and is CPU-only."
            )
        )

        self.assertEqual(
            result["decision"],
            "CLOUD_BURST",
        )

    def test_sustained_cloud_requirement_routes_committed_cloud(self):
        result = resolve_agent_placement(
            evidence(
                "This must run in the cloud "
                "and has sustained high load."
            )
        )

        self.assertEqual(
            result["decision"],
            "FULL_OR_COMMITTED_CLOUD",
        )

    def test_unknown_workload_resources_do_not_imply_local_sufficiency(self):
        result = resolve_agent_placement(
            evidence(
                "Cloud is not required."
            )
        )

        self.assertEqual(
            result["decision"],
            "UNKNOWN",
        )

        self.assertEqual(
            result["status"],
            "INPUT_REQUIRED",
        )


if __name__ == "__main__":
    unittest.main()
