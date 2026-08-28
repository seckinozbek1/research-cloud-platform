from pathlib import Path
import csv
import time

INPUT_DIR = Path(
    "data/education_attendance/distributed_cleaning"
)

OUTPUT_DIR = Path(
    "data/education_attendance/national_staging"
)

OUTPUT_PATH = OUTPUT_DIR / "national_attendance_staging.csv"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

input_files = sorted(
    INPUT_DIR.glob("regional_attendance_export_*_cleaned.csv")
)

if not input_files:
    raise SystemExit("No cleaned regional outputs found.")

start = time.perf_counter()

total_rows = 0
writer = None

with OUTPUT_PATH.open("w", newline="", encoding="utf-8") as out:
    for path in input_files:
        print(f"Merging {path.name}")

        with path.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            if writer is None:
                writer = csv.DictWriter(
                    out,
                    fieldnames=reader.fieldnames
                )
                writer.writeheader()

            elif reader.fieldnames != writer.fieldnames:
                raise RuntimeError(
                    f"Schema mismatch in {path.name}"
                )

            for row in reader:
                writer.writerow(row)
                total_rows += 1

elapsed = time.perf_counter() - start

print()
print(f"Rows merged: {total_rows:,}")
print(f"Output: {OUTPUT_PATH}")
print(f"Elapsed: {elapsed:.3f} seconds")
