from pathlib import Path
from collections import defaultdict
import csv
import time

INPUT_PATH = Path(
    "data/education_attendance/national_staging/"
    "national_attendance_staging.csv"
)

OUTPUT_DIR = Path(
    "data/education_attendance/global_resolution"
)

RESOLVED_PATH = OUTPUT_DIR / "national_attendance_resolved.csv"
QUARANTINE_PATH = OUTPUT_DIR / "national_attendance_conflicts.csv"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

start = time.perf_counter()

records_by_key = defaultdict(list)

with INPUT_PATH.open("r", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames

    for row in reader:
        key = (
            row["student_id"],
            row["academic_year"],
        )
        records_by_key[key].append(row)

resolved_fields = fieldnames + [
    "duplicate_count",
    "duplicate_resolution",
    "school_code_conflict",
    "absence_conflict",
]

quarantine_fields = resolved_fields + [
    "conflict_reason",
]

resolved_count = 0
quarantine_count = 0
exact_collapsed = 0
school_conflict_resolved = 0
absence_conflicts = 0
other_conflicts = 0

with RESOLVED_PATH.open(
    "w",
    newline="",
    encoding="utf-8"
) as resolved_file, QUARANTINE_PATH.open(
    "w",
    newline="",
    encoding="utf-8"
) as quarantine_file:

    resolved_writer = csv.DictWriter(
        resolved_file,
        fieldnames=resolved_fields
    )

    quarantine_writer = csv.DictWriter(
        quarantine_file,
        fieldnames=quarantine_fields
    )

    resolved_writer.writeheader()
    quarantine_writer.writeheader()

    for key, rows in records_by_key.items():
        duplicate_count = len(rows)

        if duplicate_count == 1:
            row = rows[0].copy()

            row["duplicate_count"] = 1
            row["duplicate_resolution"] = "unique"
            row["school_code_conflict"] = 0
            row["absence_conflict"] = 0

            resolved_writer.writerow(row)
            resolved_count += 1
            continue

        signatures = {
            (
                row["district_id"],
                row["absent"],
                row["deprivation_score"],
                row["rural"],
                row["school_code"],
            )
            for row in rows
        }

        if len(signatures) == 1:
            row = rows[0].copy()

            row["duplicate_count"] = duplicate_count
            row["duplicate_resolution"] = "exact_duplicate_collapsed"
            row["school_code_conflict"] = 0
            row["absence_conflict"] = 0

            resolved_writer.writerow(row)

            resolved_count += 1
            exact_collapsed += 1
            continue

        values_by_field = {
            field: {
                row[field]
                for row in rows
            }
            for field in [
                "district_id",
                "absent",
                "deprivation_score",
                "rural",
                "school_code",
            ]
        }

        conflicting_fields = {
            field
            for field, values in values_by_field.items()
            if len(values) > 1
        }

        if conflicting_fields == {"school_code"}:
            row = rows[0].copy()

            valid_school_codes = sorted(
                {
                    r["school_code"]
                    for r in rows
                    if r["school_code"].startswith("SCH-")
                }
            )

            if len(valid_school_codes) == 1:
                row["school_code"] = valid_school_codes[0]
            else:
                row["school_code"] = ""

            row["duplicate_count"] = duplicate_count
            row["duplicate_resolution"] = "school_conflict_preserved"
            row["school_code_conflict"] = 1
            row["absence_conflict"] = 0

            resolved_writer.writerow(row)

            resolved_count += 1
            school_conflict_resolved += 1
            continue

        if "absent" in conflicting_fields:
            absence_conflicts += 1
            reason = "CONFLICTING_ABSENCE"

        else:
            other_conflicts += 1
            reason = (
                "CONFLICTING_"
                + "_".join(
                    sorted(field.upper() for field in conflicting_fields)
                )
            )

        for row in rows:
            output = row.copy()

            output["duplicate_count"] = duplicate_count
            output["duplicate_resolution"] = "quarantined_conflict"
            output["school_code_conflict"] = (
                1 if "school_code" in conflicting_fields else 0
            )
            output["absence_conflict"] = (
                1 if "absent" in conflicting_fields else 0
            )
            output["conflict_reason"] = reason

            quarantine_writer.writerow(output)
            quarantine_count += 1


elapsed = time.perf_counter() - start

print(f"Unique keys inspected:       {len(records_by_key):,}")
print(f"Resolved output rows:        {resolved_count:,}")
print(f"Conflict quarantine rows:    {quarantine_count:,}")

print()
print(f"Exact duplicates collapsed:  {exact_collapsed:,}")
print(f"School conflicts resolved:   {school_conflict_resolved:,}")
print(f"Absence conflict keys:       {absence_conflicts:,}")
print(f"Other conflict keys:         {other_conflicts:,}")

print()
print(f"Resolved:    {RESOLVED_PATH}")
print(f"Quarantine:  {QUARANTINE_PATH}")
print(f"Elapsed:     {elapsed:.3f} seconds")
