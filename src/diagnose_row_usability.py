from pathlib import Path
from collections import Counter
import csv
import re

INPUT_DIR = Path("data/education_attendance/ministry_exports")

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

problem_counts = Counter()
valid_field_distribution = Counter()

total_rows = 0
fully_direct = 0


def is_valid_student(value):
    return bool(re.fullmatch(r"\d{4}_\d+", value))


def is_valid_district(value):
    return (
        value.isdigit()
        and 1 <= int(value) <= 250
    )


def is_valid_year(value):
    return value in VALID_YEARS


def is_valid_binary(value):
    return value in {"0", "1"}


def is_valid_deprivation(value):
    try:
        number = float(value)
        return 0 <= number <= 1
    except ValueError:
        return False


def is_valid_school(value):
    return bool(
        re.fullmatch(r"SCH-\d{3}-\d{2}", value)
    )


validators = {
    "student_id": is_valid_student,
    "district_id": is_valid_district,
    "academic_year": is_valid_year,
    "absent": is_valid_binary,
    "deprivation_score": is_valid_deprivation,
    "rural": is_valid_binary,
    "school_code": is_valid_school,
}


for path in sorted(INPUT_DIR.glob("*.csv")):
    print(f"Scanning {path.name}")

    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for raw in reader:
            total_rows += 1

            row = {
                SCHEMA_MAP[key]: value.strip()
                for key, value in raw.items()
            }

            invalid_fields = []

            for field, validator in validators.items():
                value = row[field]

                if not value or not validator(value):
                    invalid_fields.append(field)

            valid_count = 7 - len(invalid_fields)
            valid_field_distribution[valid_count] += 1

            if not invalid_fields:
                fully_direct += 1
            else:
                signature = "+".join(sorted(invalid_fields))
                problem_counts[signature] += 1


print()
print(f"TOTAL ROWS: {total_rows:,}")
print(
    f"DIRECTLY USABLE ROWS: {fully_direct:,} "
    f"({fully_direct / total_rows:.2%})"
)

print("\nVALID FIELDS PER ROW")

for valid_count in range(7, -1, -1):
    count = valid_field_distribution[valid_count]

    print(
        f"  {valid_count}/7 valid: "
        f"{count:>10,} "
        f"({count / total_rows:6.2%})"
    )


print("\nMOST COMMON PROBLEM COMBINATIONS")

for signature, count in problem_counts.most_common(20):
    print(
        f"  {signature:<70} "
        f"{count:>10,} "
        f"({count / total_rows:6.2%})"
    )
