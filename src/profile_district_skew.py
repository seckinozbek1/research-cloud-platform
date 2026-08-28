from pathlib import Path
from collections import Counter
import csv
import time

INPUT_PATH = Path(
    "data/education_attendance/curated_national/"
    "national_attendance_skewed.csv"
)

start = time.perf_counter()

counts = Counter()

with INPUT_PATH.open("r", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)

    for row in reader:
        counts[
            (
                row["district_id"],
                row["academic_year"],
            )
        ] += 1

values = list(counts.values())

print(f"Groups: {len(values):,}")
print(f"Minimum group size: {min(values):,}")
print(f"Maximum group size: {max(values):,}")
print(f"Mean group size:    {sum(values) / len(values):,.1f}")

print("\n10 LARGEST GROUPS")

for (district, year), count in counts.most_common(10):
    print(
        f"district={district:>3} "
        f"year={year} "
        f"rows={count:>8,}"
    )

elapsed = time.perf_counter() - start

print()
print(f"Elapsed: {elapsed:.3f} seconds")
