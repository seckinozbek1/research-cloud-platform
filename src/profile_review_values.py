from pathlib import Path
from collections import Counter
import csv
import re

INPUT_DIR = Path("data/education_attendance/ministry_exports")
OUTPUT_PATH = Path(
    "data/education_attendance/profiling/review_value_profile.txt"
)

SCHEMA_MAP = {
    "student_id": "student_id",
    "student": "student_id",
    "StudentID": "student_id",

    "district_id": "district_id",
    "district": "district_id",
    "DistrictCode": "district_id",

    "academic_year": "academic_year",
    "year": "academic_year",
    "AcademicYear": "academic_year",

    "absent": "absent",
    "attendance_status": "absent",
    "AbsentFlag": "absent",

    "deprivation_score": "deprivation_score",
    "deprivation": "deprivation_score",
    "DeprivationIndex": "deprivation_score",

    "rural": "rural",
    "location_type": "rural",
    "RuralUrban": "rural",

    "school_code": "school_code",
    "school": "school_code",
    "SchoolCode": "school_code",
}

VALID_YEARS = {"2022", "2023", "2024", "2025"}


def direct_student(value):
    return bool(re.fullmatch(r"\d{4}_\d+", value))


def direct_district(value):
    return value.isdigit() and 1 <= int(value) <= 250


def direct_year(value):
    return value in VALID_YEARS


def direct_binary(value):
    return value in {"0", "1"}


def direct_deprivation(value):
    try:
        x = float(value)
        return 0 <= x <= 1
    except ValueError:
        return False


def direct_school(value):
    return bool(re.fullmatch(r"SCH-\d{3}-\d{2}", value))


validators = {
    "student_id": direct_student,
    "district_id": direct_district,
    "academic_year": direct_year,
    "absent": direct_binary,
    "deprivation_score": direct_deprivation,
    "rural": direct_binary,
    "school_code": direct_school,
}

review_values = {
    field: Counter()
    for field in validators
}

missing_counts = Counter()

for path in sorted(INPUT_DIR.glob("*.csv")):
    print(f"Inspecting {path.name}")

    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for raw in reader:
            row = {
                SCHEMA_MAP[key]: value.strip()
                for key, value in raw.items()
            }

            for field, validator in validators.items():
                value = row[field]

                if value == "":
                    missing_counts[field] += 1

                elif not validator(value):
                    review_values[field][value] += 1


lines = []

for field in validators:
    lines.append("=" * 70)
    lines.append(field.upper())
    lines.append("=" * 70)

    lines.append(
        f"Missing values: {missing_counts[field]:,}"
    )

    lines.append("Most common non-direct values:")

    for value, count in review_values[field].most_common(30):
        lines.append(
            f"{value!r:<30} {count:>10,}"
        )

    lines.append("")


OUTPUT_PATH.write_text(
    "\n".join(lines),
    encoding="utf-8"
)

print()
print(f"Report written to: {OUTPUT_PATH}")
