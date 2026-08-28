from pathlib import Path
import csv
import time

INPUT_PATH = Path(
    "data/education_attendance/curated_national/"
    "national_attendance_imputed.csv"
)

OUTPUT_PATH = Path(
    "data/education_attendance/curated_national/"
    "national_attendance_curated.csv"
)

start = time.perf_counter()

rows = 0
rural_missing = 0

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

    output_fields = reader.fieldnames + [
        "rural_missing"
    ]

    writer = csv.DictWriter(
        target,
        fieldnames=output_fields
    )

    writer.writeheader()

    for row in reader:
        missing = 1 if row["rural"] == "" else 0

        row["rural_missing"] = missing

        if missing:
            rural_missing += 1

        writer.writerow(row)
        rows += 1

elapsed = time.perf_counter() - start

print(f"Rows written:         {rows:,}")
print(f"Rural missing rows:   {rural_missing:,}")
print(f"Rural missing rate:   {rural_missing / rows:.2%}")
print(f"Output:               {OUTPUT_PATH}")
print(f"Elapsed:              {elapsed:.3f} seconds")
