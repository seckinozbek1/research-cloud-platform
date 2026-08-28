from pathlib import Path
import csv
import time

INPUT_PATH = Path(
    "data/education_attendance/curated_national/"
    "national_attendance_curated.csv"
)

OUTPUT_PATH = Path(
    "data/education_attendance/curated_national/"
    "national_attendance_skewed.csv"
)

SKEW_DISTRICT = "1"
EXTRA_COPIES = 20

start = time.perf_counter()

original_rows = 0
extra_rows = 0

with INPUT_PATH.open(
    "r",
    newline="",
    encoding="utf-8"
) as source, OUTPUT_PATH.open(
    "w",
    newline="",
    encoding="utf-8"
) as target:

    reader = csv.DictReader(source)

    writer = csv.DictWriter(
        target,
        fieldnames=reader.fieldnames
    )

    writer.writeheader()

    for row in reader:
        writer.writerow(row)
        original_rows += 1

        if row["district_id"] == SKEW_DISTRICT:
            for _ in range(EXTRA_COPIES):
                writer.writerow(row)
                extra_rows += 1

elapsed = time.perf_counter() - start

print(f"Original rows: {original_rows:,}")
print(f"Extra skew rows: {extra_rows:,}")
print(f"Total rows: {original_rows + extra_rows:,}")
print(f"Output: {OUTPUT_PATH}")
print(f"Elapsed: {elapsed:.3f} seconds")
