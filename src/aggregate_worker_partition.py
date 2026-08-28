from pathlib import Path
from collections import defaultdict
import csv
import sys
import time

if len(sys.argv) != 2:
    raise SystemExit(
        "Usage: python aggregate_worker_partition.py <partition_csv>"
    )

INPUT_PATH = Path(sys.argv[1])

OUTPUT_DIR = Path(
    "data/education_attendance/partial_aggregates"
)

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_PATH = OUTPUT_DIR / (
    f"{INPUT_PATH.stem}_partial.csv"
)

start = time.perf_counter()

aggregates = defaultdict(
    lambda: {
        "student_days": 0,
        "absent_days": 0,
        "deprivation_sum": 0.0,
        "rural_known": 0,
        "rural_count": 0,
        "rural_missing": 0,
    }
)

with INPUT_PATH.open("r", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)

    for row in reader:
        key = (
            row["district_id"],
            row["academic_year"],
        )

        group = aggregates[key]

        group["student_days"] += 1
        group["absent_days"] += int(row["absent"])
        group["deprivation_sum"] += float(
            row["deprivation_score"]
        )

        if row["rural"] == "":
            group["rural_missing"] += 1

        else:
            group["rural_known"] += 1
            group["rural_count"] += int(row["rural"])

with OUTPUT_PATH.open(
    "w",
    newline="",
    encoding="utf-8"
) as out:

    writer = csv.writer(out)

    writer.writerow([
        "district_id",
        "academic_year",
        "student_days_partial",
        "absent_days_partial",
        "deprivation_sum_partial",
        "rural_known_partial",
        "rural_count_partial",
        "rural_missing_partial",
    ])

    for (district, year), values in sorted(
        aggregates.items()
    ):
        writer.writerow([
            district,
            year,
            values["student_days"],
            values["absent_days"],
            values["deprivation_sum"],
            values["rural_known"],
            values["rural_count"],
            values["rural_missing"],
        ])

elapsed = time.perf_counter() - start

print(f"Input:   {INPUT_PATH}")
print(f"Groups:  {len(aggregates):,}")
print(f"Output:  {OUTPUT_PATH}")
print(f"Elapsed: {elapsed:.3f} seconds")
