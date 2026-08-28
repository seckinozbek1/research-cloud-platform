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

VALID_ABSENCE = {"0", "1"}
VALID_RURAL = {"0", "1"}
VALID_YEARS = {"2022", "2023", "2024", "2025"}

counts = Counter()
total_rows = 0

for path in sorted(INPUT_DIR.glob("*.csv")):
    print(f"Diagnosing {path.name}")

    with path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        for raw in reader:
            total_rows += 1

            row = {
                SCHEMA_MAP[key]: value.strip()
                for key, value in raw.items()
            }

            # Student ID
            sid = row["student_id"]

            if not sid:
                counts["student_missing"] += 1
            elif re.fullmatch(r"\d{4}_\d+", sid):
                counts["student_direct"] += 1
            else:
                counts["student_needs_review"] += 1

            # District
            district = row["district_id"]

            if not district:
                counts["district_missing"] += 1
            elif district.isdigit() and 1 <= int(district) <= 250:
                counts["district_direct"] += 1
            else:
                counts["district_needs_review"] += 1

            # Academic year
            year = row["academic_year"]

            if not year:
                counts["year_missing"] += 1
            elif year in VALID_YEARS:
                counts["year_direct"] += 1
            else:
                counts["year_needs_review"] += 1

            # Absence
            absent = row["absent"]

            if not absent:
                counts["absence_missing"] += 1
            elif absent in VALID_ABSENCE:
                counts["absence_direct"] += 1
            else:
                counts["absence_needs_review"] += 1

            # Rural
            rural = row["rural"]

            if not rural:
                counts["rural_missing"] += 1
            elif rural in VALID_RURAL:
                counts["rural_direct"] += 1
            else:
                counts["rural_needs_review"] += 1

            # Deprivation
            dep = row["deprivation_score"]

            if not dep:
                counts["deprivation_missing"] += 1
            else:
                try:
                    value = float(dep)

                    if 0 <= value <= 1:
                        counts["deprivation_direct"] += 1
                    else:
                        counts["deprivation_needs_review"] += 1

                except ValueError:
                    counts["deprivation_needs_review"] += 1

            # School code
            school = row["school_code"]

            if not school:
                counts["school_missing"] += 1
            elif re.fullmatch(r"SCH-\d{3}-\d{2}", school):
                counts["school_direct"] += 1
            else:
                counts["school_needs_review"] += 1


print()
print(f"TOTAL ROWS: {total_rows:,}")

fields = [
    "student",
    "district",
    "year",
    "absence",
    "deprivation",
    "rural",
    "school",
]

for field in fields:
    print(f"\n{field.upper()}")

    direct = counts[f"{field}_direct"]
    missing = counts[f"{field}_missing"]
    review = counts[f"{field}_needs_review"]

    print(f"  directly usable : {direct:>10,}  ({direct / total_rows:6.2%})")
    print(f"  needs review    : {review:>10,}  ({review / total_rows:6.2%})")
    print(f"  missing         : {missing:>10,}  ({missing / total_rows:6.2%})")
