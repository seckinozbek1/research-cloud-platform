from pathlib import Path
from collections import defaultdict, Counter
import csv
import time

INPUT_PATH = Path(
    "data/education_attendance/curated_national/"
    "national_attendance_imputed.csv"
)

start = time.perf_counter()

school_counts = defaultdict(Counter)
district_counts = defaultdict(Counter)

total = 0
missing_rural = 0

with INPUT_PATH.open("r", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)

    for row in reader:
        total += 1

        rural = row["rural"]
        school = row["school_code"]
        district = row["district_id"]

        if rural == "":
            missing_rural += 1
            continue

        if school:
            school_counts[school][rural] += 1

        if district:
            district_counts[district][rural] += 1


def summarize_group(name, counts):
    stable = 0
    mixed = 0
    usable = 0

    for key, values in counts.items():
        total_obs = sum(values.values())

        if total_obs == 0:
            continue

        usable += 1

        top_count = max(values.values())
        consistency = top_count / total_obs

        if consistency >= 0.95:
            stable += 1
        else:
            mixed += 1

    print(f"\n{name}")
    print("-" * len(name))
    print(f"Groups observed:        {usable:,}")
    print(f">=95% consistent:       {stable:,}")
    print(f"Mixed/inconsistent:     {mixed:,}")


print(f"TOTAL ROWS:           {total:,}")
print(f"MISSING RURAL:        {missing_rural:,}")
print(f"MISSING RATE:         {missing_rural / total:.2%}")

summarize_group("SCHOOL-LEVEL CONSISTENCY", school_counts)
summarize_group("DISTRICT-LEVEL CONSISTENCY", district_counts)

print("\nMOST MIXED SCHOOLS")
print("------------------")

mixed_schools = []

for school, values in school_counts.items():
    total_obs = sum(values.values())

    if total_obs == 0:
        continue

    top_count = max(values.values())
    consistency = top_count / total_obs

    if consistency < 0.95:
        mixed_schools.append(
            (
                consistency,
                school,
                total_obs,
                dict(values),
            )
        )

mixed_schools.sort()

for consistency, school, n, values in mixed_schools[:20]:
    print(
        f"{school:<15} "
        f"rows={n:>5,} "
        f"consistency={consistency:6.2%} "
        f"values={values}"
    )

elapsed = time.perf_counter() - start

print()
print(f"Elapsed: {elapsed:.3f} seconds")
