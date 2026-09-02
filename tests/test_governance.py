from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class GovernanceIntegrationTest(unittest.TestCase):

    def test_waste_gis_governance_gate_passes(self):
        script = (
            ROOT
            / "governance"
            / "waste_gis_gate.py"
        )

        self.assertTrue(
            script.exists(),
            f"Missing governance gate: {script}",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(script),
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

        self.assertIn(
            "GATE RESULT: PASS",
            combined,
        )


if __name__ == "__main__":
    unittest.main()
