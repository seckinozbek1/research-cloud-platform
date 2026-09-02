from pathlib import Path
import json
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]

REQUEST = (
    ROOT
    / "hybrid"
    / "workload_profiles"
    / "waste_gis_ddp_resolved.json"
)

REPORT = (
    ROOT
    / "hybrid"
    / "adaptive_placement_decision.json"
)


class HybridRoutingIntegrationTest(unittest.TestCase):

    def test_measured_ddp_workload_routes_local(self):
        self.assertTrue(
            REQUEST.exists(),
            f"Missing workload request: {REQUEST}",
        )

        script = (
            ROOT
            / "hybrid"
            / "adaptive_placement.py"
        )

        self.assertTrue(
            script.exists(),
            f"Missing placement engine: {script}",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--request",
                str(REQUEST),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=120,
        )

        combined = (
            result.stdout
            + "\n"
            + result.stderr
        )

        self.assertEqual(
            result.returncode,
            0,
            combined,
        )

        self.assertTrue(
            REPORT.exists(),
            "Placement report was not generated.",
        )

        report = json.loads(
            REPORT.read_text()
        )

        self.assertEqual(
            report.get("routing_decision"),
            "LOCAL_PC",
            report,
        )

        self.assertTrue(
            report.get("local_capacity_sufficient"),
            report,
        )


if __name__ == "__main__":
    unittest.main()
