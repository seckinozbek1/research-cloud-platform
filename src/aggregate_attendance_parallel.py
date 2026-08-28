from pathlib import Path
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
import csv
import os
import time

INPUT_DIR = Path("data/education_attendance/raw")
OUTPUT_DIR = Path("data/education_attendance/curated")
OUTPUT_PATH = OUTPUT_DIR / "district_year_attendance_metrics_parallel.csv"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def process_file(input_path):
    """
    One worker processes one academic-year partition.
    """
    aggregates = defaultdict(
        lambda: {
            "student_days": 0,
            "absent_days": 0,
            "deprivation_sum": 0.0,
            "rural_count": 0,
        }
    )

    with Path(input_path).open("r", newline="", encoding="utf-8") as f:
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

    return dict(aggregates)


def main():
    input_files = sorted(INPUT_DIR.glob("attendance_*.csv"))

    start = time.perf_counter()

    workers = int(os.environ.get("WORKERS", "4"))

    with ProcessPoolExecutor(max_workers=workers) as executor:
        partial_results = list(
            executor.map(process_file, input_files)
        )

    combined = {}

    for result in partial_results:
        combined.update(result)

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

        for (district_id, academic_year), values in sorted(combined.items()):
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

    print(f"Logical CPUs available: {os.cpu_count()}")
    print(f"Workers used: {workers}")
    print(f"Groups produced: {len(combined):,}")
    print(f"Output: {OUTPUT_PATH}")
    print(f"Elapsed: {elapsed:.3f} seconds")


if __name__ == "__main__":
    main()
