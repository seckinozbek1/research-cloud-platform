from pathlib import Path
import csv
import random

OUTPUT_DIR = Path("data/education_attendance/raw")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

YEARS = [2022, 2023, 2024, 2025]
ROWS_PER_YEAR = 500_000
DISTRICTS = 250

random.seed(42)

for year in YEARS:
    output_path = OUTPUT_DIR / f"attendance_{year}.csv"

    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)

        writer.writerow([
            "student_id",
            "district_id",
            "academic_year",
            "absent",
            "deprivation_score",
            "rural"
        ])

        for i in range(ROWS_PER_YEAR):
            district_id = random.randint(1, DISTRICTS)
            deprivation = round(random.random(), 4)
            rural = 1 if random.random() < 0.30 else 0

            # Synthetic relationship:
            # higher deprivation slightly increases absence probability.
            absence_probability = 0.04 + 0.12 * deprivation
            absent = 1 if random.random() < absence_probability else 0

            writer.writerow([
                f"{year}_{i}",
                district_id,
                year,
                absent,
                deprivation,
                rural
            ])

    print(f"Wrote {output_path}")
