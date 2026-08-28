from pathlib import Path
from collections import Counter
import csv
import json
import time

INPUT_DIR = Path("data/education_attendance/ministry_exports")
OUTPUT_DIR = Path("data/education_attendance/profiling")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

REPORT_PATH = OUTPUT_DIR / "ministry_export_profile.json"

files = sorted(INPUT_DIR.glob("*.csv"))

report = {
    "files": {},
    "schemas_seen": [],
}

start = time.perf_counter()

for path in files:
    print(f"Profiling {path}")

    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.reader(f)

        try:
            header = next(reader)
        except StopIteration:
            continue

        header = [col.strip() for col in header]
        report["schemas_seen"].append(header)

        row_count = 0
        malformed_row_count = 0

        blank_counts = Counter()
        value_samples = {
            col: Counter()
            for col in header
        }

        exact_row_counts = Counter()

        for row in reader:
            row_count += 1

            if len(row) != len(header):
                malformed_row_count += 1
                continue

            exact_row_counts[tuple(row)] += 1

            for col, value in zip(header, row):
                stripped = value.strip()

                if stripped == "":
                    blank_counts[col] += 1

                # Keep the most common raw values.
                if len(value_samples[col]) < 500 or stripped in value_samples[col]:
                    value_samples[col][stripped] += 1

        exact_duplicate_rows = sum(
            count - 1
            for count in exact_row_counts.values()
            if count > 1
        )

        report["files"][path.name] = {
            "header": header,
            "row_count": row_count,
            "malformed_row_count": malformed_row_count,
            "exact_duplicate_rows": exact_duplicate_rows,
            "blank_counts": dict(blank_counts),
            "common_values": {
                col: counter.most_common(15)
                for col, counter in value_samples.items()
            },
        }

elapsed = time.perf_counter() - start
report["elapsed_seconds"] = elapsed

REPORT_PATH.write_text(
    json.dumps(report, indent=2),
    encoding="utf-8"
)

print()
print(f"Profile written to: {REPORT_PATH}")
print(f"Elapsed: {elapsed:.3f} seconds")
