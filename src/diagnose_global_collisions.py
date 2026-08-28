from pathlib import Path
from collections import defaultdict, Counter
import csv
import time

INPUT_PATH = Path(
    "data/education_attendance/national_staging/"
    "national_attendance_staging.csv"
)

start = time.perf_counter()

records_by_key = defaultdict(list)

with INPUT_PATH.open("r", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)

    for row in reader:
        key = (
            row["student_id"],
            row["academic_year"],
        )

        records_by_key[key].append(row)

total_keys = len(records_by_key)

duplicate_keys = 0
duplicate_rows = 0
exact_duplicate_keys = 0
conflicting_keys = 0

conflict_types = Counter()

for key, rows in records_by_key.items():
    if len(rows) == 1:
        continue

    duplicate_keys += 1
    duplicate_rows += len(rows) - 1

    signatures = {
        (
            row["district_id"],
            row["academic_year"],
            row["absent"],
            row["deprivation_score"],
            row["rural"],
            row["school_code"],
        )
        for row in rows
    }

    if len(signatures) == 1:
        exact_duplicate_keys += 1
        continue

    conflicting_keys += 1

    fields = [
        "district_id",
        "absent",
        "deprivation_score",
        "rural",
        "school_code",
    ]

    for field in fields:
        values = {
            row[field]
            for row in rows
        }

        if len(values) > 1:
            conflict_types[field] += 1

elapsed = time.perf_counter() - start

print(f"Unique student-year keys: {total_keys:,}")
print(f"Keys appearing >1 time:  {duplicate_keys:,}")
print(f"Extra duplicate rows:    {duplicate_rows:,}")
print(f"Exact duplicate keys:    {exact_duplicate_keys:,}")
print(f"Conflicting keys:        {conflicting_keys:,}")

print("\nCONFLICT TYPES")

for field, count in conflict_types.most_common():
    print(f"  {field:<20} {count:>10,}")

print()
print(f"Elapsed: {elapsed:.3f} seconds")
