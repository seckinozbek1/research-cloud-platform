from pathlib import Path
from collections import defaultdict
import csv
import time

INPUT_DIR = Path("data/education_attendance/raw")
OUTPUT_DIR = Path("data/education_attendance/curated")
OUTPUT_PATH = OUTPUT_DIR / "district_year_attendance_metrics_single.csv"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

input_files = sorted(INPUT_DIR.glob("attendance_*.csv"))

aggregates = defaultdict(
    lambda: {
        "student_days": 0,
        "absent_days": 0,
        "deprivation_sum": 0.0,
        "rural_count": 0,
    }
)

start = time.perf_counter()

for input_path in input_files:
    print(f"Processing {input_path}")

    with input_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for row in reader:
            key = (
                int(row["district_id"]),
                int(row["academic_year"]),
            )

            group = aggregates[key]

            group["student_days"] += 1
            group["absent_days"] += int(row["absent"])
            group["deprivation_sum"] += float(row["deprivation_score"])
            group["rural_count"] += int(row["rural"])

with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)

    writer.writerow([
        "district_id",
        "academic_year",
        "student_days",
        "absent_days",
        "absence_rate",
        "average_deprivation_score",
        "rural_share",
    ])

    for (district_id, academic_year), values in sorted(aggregates.items()):
        student_days = values["student_days"]

        writer.writerow([
            district_id,
            academic_year,
            student_days,
            values["absent_days"],
            values["absent_days"] / student_days,
            values["deprivation_sum"] / student_days,
            values["rural_count"] / student_days,
        ])

elapsed = time.perf_counter() - start

print()
print(f"Groups produced: {len(aggregates):,}")
print(f"Output: {OUTPUT_PATH}")
print(f"Elapsed: {elapsed:.3f} seconds")
