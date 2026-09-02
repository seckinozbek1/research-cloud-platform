from pathlib import Path
import json
import unittest


ROOT = Path(__file__).resolve().parents[1]

LINEAGE = (
    ROOT
    / "governance"
    / "lineage_events.jsonl"
)


class LineageIntegrityTest(unittest.TestCase):

    def load_events(self):
        self.assertTrue(
            LINEAGE.exists(),
            f"Missing lineage log: {LINEAGE}",
        )

        events = []

        for line in LINEAGE.read_text().splitlines():
            line = line.strip()

            if not line:
                continue

            events.append(
                json.loads(line)
            )

        return events

    def test_lineage_log_contains_events(self):
        events = self.load_events()

        self.assertGreater(
            len(events),
            0,
            "Lineage log is empty.",
        )

    def test_events_have_provenance_structure(self):
        events = self.load_events()

        valid = [
            event
            for event in events
            if (
                event.get("run_id")
                and event.get("transformation")
                and isinstance(
                    event.get("inputs"),
                    list,
                )
                and isinstance(
                    event.get("outputs"),
                    list,
                )
            )
        ]

        self.assertGreater(
            len(valid),
            0,
            "No structured provenance events found.",
        )

    def test_ddp_training_lineage_exists(self):
        events = self.load_events()

        input_suffix = (
            "data/curated/waste_gis/"
            "waste_operations.csv"
        )

        output_suffix = (
            "artifacts/distributed_ml/"
            "ddp-2-cpu_metrics.json"
        )

        matches = []

        for event in events:
            inputs = [
                item.get("path", "")
                for item
                in event.get("inputs", [])
            ]

            outputs = [
                item.get("path", "")
                for item
                in event.get("outputs", [])
            ]

            has_input = any(
                path.endswith(input_suffix)
                for path in inputs
            )

            has_output = any(
                path.endswith(output_suffix)
                for path in outputs
            )

            if has_input and has_output:
                matches.append(event)

        self.assertGreater(
            len(matches),
            0,
            (
                "No DDP lineage event links "
                "waste_operations.csv to "
                "ddp-2-cpu_metrics.json"
            ),
        )


if __name__ == "__main__":
    unittest.main()
