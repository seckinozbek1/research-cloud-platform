from pathlib import Path
from collections import defaultdict
import csv
import time

INPUT_DIR = Path(
    "data/education_attendance/partial_aggregates"
)

OUTPUT_DIR = Path(
    "data/education_attendance/analytics"
)

OUTPUT_PATH = OUTPUT_DIR / "district_year_attendance_metrics.csv"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

start = time.perf_counter()

combined = defaultdict(
    lambda: {
        "student_days": 0,
        "absent_days": 0,
        "deprivation_sum": 0.0,
        "rural_known": 0,
        "rural_count": 0,
        "rural_missing": 0,
    }
)

for path in sorted(INPUT_DIR.glob("*_partial.csv")):
    print(f"Reducing {path.name}")

    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            key = (
                row["district_id"],
                row["academic_year"],
            )

            group = combined[key]

            group["student_days"] += int(
                row["student_days_partial"]
            )

            group["absent_days"] += int(
                row["absent_days_partial"]
            )

            group["deprivation_sum"] += float(
                row["deprivation_sum_partial"]
            )

            group["rural_known"] += int(
                row["rural_known_partial"]
            )

            group["rural_count"] += int(
                row["rural_count_partial"]
            )

            group["rural_missing"] += int(
                row["rural_missing_partial"]
            )


with OUTPUT_PATH.open(
    "w",
    newline="",
    encoding="utf-8"
) as out:

    writer = csv.writer(out)

    writer.writerow([
        "district_id",
        "academic_year",
        "student_days",
        "absent_days",
        "absence_rate",
        "mean_deprivation",
        "rural_share_among_observed",
        "rural_unknown_rate",
    ])

    for (district, year), values in sorted(
        combined.items()
    ):
        student_days = values["student_days"]
        rural_known = values["rural_known"]

        writer.writerow([
            district,
            year,
            student_days,
            values["absent_days"],
            values["absent_days"] / student_days,
            values["deprivation_sum"] / student_days,
            (
                values["rural_count"] / rural_known
                if rural_known > 0
                else ""
            ),
            values["rural_missing"] / student_days,
        ])

elapsed = time.perf_counter() - start

print()
print(f"Final groups: {len(combined):,}")
print(f"Output: {OUTPUT_PATH}")
print(f"Elapsed: {elapsed:.3f} seconds")
