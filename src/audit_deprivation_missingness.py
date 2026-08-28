from pathlib import Path
from collections import defaultdict
import csv
import time

INPUT_PATH = Path(
    "data/education_attendance/global_resolution/"
    "national_attendance_resolved.csv"
)

start = time.perf_counter()

total = 0
missing = 0

by_year = defaultdict(lambda: [0, 0])
by_rural = defaultdict(lambda: [0, 0])
by_absence = defaultdict(lambda: [0, 0])
by_district_year = defaultdict(lambda: [0, 0])

with INPUT_PATH.open("r", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)

    for row in reader:
        total += 1

        dep_missing = row["deprivation_score"] == ""

        if dep_missing:
            missing += 1

        year = row["academic_year"]
        rural = row["rural"]
        absent = row["absent"]
        district = row["district_id"]

        groups = [
            (by_year, year),
            (by_rural, rural),
            (by_absence, absent),
            (by_district_year, (district, year)),
        ]

        for container, key in groups:
            container[key][0] += 1

            if dep_missing:
                container[key][1] += 1


def print_group(title, data):
    print(f"\n{title}")
    print("-" * len(title))

    for key, (n, m) in sorted(data.items()):
        print(
            f"{str(key):<20} "
            f"rows={n:>10,} "
            f"missing={m:>10,} "
            f"rate={m/n:7.2%}"
        )


print(f"TOTAL ROWS:            {total:,}")
print(f"MISSING DEPRIVATION:   {missing:,}")
print(f"MISSING RATE:          {missing / total:.2%}")

print_group("BY YEAR", by_year)
print_group("BY RURAL STATUS", by_rural)
print_group("BY ABSENCE STATUS", by_absence)

rates = []

for (district, year), (n, m) in by_district_year.items():
    rates.append(
        (
            m / n,
            district,
            year,
            n,
            m,
        )
    )

rates.sort(reverse=True)

print("\n20 HIGHEST-MISSING DISTRICT-YEARS")
print("---------------------------------")

for rate, district, year, n, m in rates[:20]:
    print(
        f"district={district:>3} "
        f"year={year} "
        f"rows={n:>6,} "
        f"missing={m:>6,} "
        f"rate={rate:7.2%}"
    )

elapsed = time.perf_counter() - start

print()
print(f"Elapsed: {elapsed:.3f} seconds")
