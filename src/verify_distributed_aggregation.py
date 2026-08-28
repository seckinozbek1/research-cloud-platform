from pathlib import Path
from collections import defaultdict
import csv
import math
import time

SOURCE_PATH = Path(
    "data/education_attendance/curated_national/"
    "national_attendance_curated.csv"
)

DISTRIBUTED_PATH = Path(
    "data/education_attendance/analytics/"
    "district_year_attendance_metrics.csv"
)

start = time.perf_counter()

direct = defaultdict(
    lambda: {
        "student_days": 0,
        "absent_days": 0,
        "deprivation_sum": 0.0,
        "rural_known": 0,
        "rural_count": 0,
        "rural_missing": 0,
    }
)

with SOURCE_PATH.open("r", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)

    for row in reader:
        key = (
            row["district_id"],
            row["academic_year"],
        )

        group = direct[key]

        group["student_days"] += 1
        group["absent_days"] += int(row["absent"])
        group["deprivation_sum"] += float(
            row["deprivation_score"]
        )

        if row["rural"] == "":
            group["rural_missing"] += 1
        else:
            group["rural_known"] += 1
            group["rural_count"] += int(row["rural"])


distributed = {}

with DISTRIBUTED_PATH.open(
    "r",
    newline="",
    encoding="utf-8"
) as f:
    reader = csv.DictReader(f)

    for row in reader:
        key = (
            row["district_id"],
            row["academic_year"],
        )
        distributed[key] = row


problems = []

for key, values in direct.items():
    student_days = values["student_days"]
    rural_known = values["rural_known"]

    expected = {
        "student_days": student_days,
        "absent_days": values["absent_days"],
        "absence_rate": (
            values["absent_days"] / student_days
        ),
        "mean_deprivation": (
            values["deprivation_sum"] / student_days
        ),
        "rural_share_among_observed": (
            values["rural_count"] / rural_known
            if rural_known
            else None
        ),
        "rural_unknown_rate": (
            values["rural_missing"] / student_days
        ),
    }

    actual = distributed.get(key)

    if actual is None:
        problems.append((key, "missing distributed key"))
        continue

    if int(actual["student_days"]) != expected["student_days"]:
        problems.append((key, "student_days"))

    if int(actual["absent_days"]) != expected["absent_days"]:
        problems.append((key, "absent_days"))

    for field in [
        "absence_rate",
        "mean_deprivation",
        "rural_share_among_observed",
        "rural_unknown_rate",
    ]:
        expected_value = expected[field]

        if expected_value is None:
            continue

        actual_value = float(actual[field])

        if not math.isclose(
            actual_value,
            expected_value,
            rel_tol=1e-12,
            abs_tol=1e-12,
        ):
            problems.append((key, field))


elapsed = time.perf_counter() - start

print(f"Direct groups:       {len(direct):,}")
print(f"Distributed groups:  {len(distributed):,}")
print(f"Mismatches:          {len(problems):,}")

if problems:
    print("\nFirst mismatches:")
    for problem in problems[:10]:
        print(problem)
else:
    print("\nDistributed result matches direct aggregation.")

print()
print(f"Elapsed: {elapsed:.3f} seconds")
