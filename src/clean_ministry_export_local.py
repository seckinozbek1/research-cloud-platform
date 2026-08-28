from pathlib import Path
import csv
import re

INPUT_PATH = Path(
    "data/education_attendance/ministry_exports/"
    "regional_attendance_export_1.csv"
)

OUTPUT_DIR = Path(
    "data/education_attendance/local_cleaning_test"
)

CLEAN_PATH = OUTPUT_DIR / "regional_export_1_cleaned.csv"
QUARANTINE_PATH = OUTPUT_DIR / "regional_export_1_quarantine.csv"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

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

ABSENCE_ZERO = {
    "0", "n", "no", "p", "present"
}

ABSENCE_ONE = {
    "1", "y", "yes", "a", "absent"
}

RURAL_ZERO = {
    "0", "n", "no", "u", "urban"
}

RURAL_ONE = {
    "1", "y", "yes", "r", "rural"
}

MISSING_MARKERS = {
    "", "?", "-", "unknown", "n/a", "na", "missing"
}


def normalize_student(value):
    original = value
    value = value.strip()

    if value.lower() in MISSING_MARKERS:
        return "", "unresolved"

    if re.fullmatch(r"\d{4}_\d+", value):
        return value, "direct"

    if value.startswith("STU-"):
        candidate = value[4:]

        if re.fullmatch(r"\d{4}_\d+", candidate):
            return candidate, "normalized"

    if re.fullmatch(r"\d{4}-\d+", value):
        return value.replace("-", "_"), "normalized"

    return original.strip(), "unresolved"


def normalize_school(value):
    value = value.strip()

    if value.lower() in MISSING_MARKERS:
        return "", "unresolved"

    if re.fullmatch(r"SCH-\d{3}-\d{2}", value):
        return value, "direct"

    return value, "unresolved"


def district_from_school(school):
    match = re.fullmatch(
        r"SCH-(\d{3})-\d{2}",
        school
    )

    if not match:
        return None

    district = int(match.group(1))

    if 1 <= district <= 250:
        return district

    return None


def normalize_district(value, school):
    value = value.strip()

    if value.isdigit():
        district = int(value)

        if 1 <= district <= 250:
            return district, "direct"

    patterns = [
        r"District\s+(\d{1,3})",
        r"district\s+(\d{1,3})",
        r"DIST\s+(\d{1,3})",
        r"Dist\.\s*(\d{1,3})",
        r"D(\d{3})",
    ]

    for pattern in patterns:
        match = re.fullmatch(
            pattern,
            value,
            flags=re.IGNORECASE
        )

        if match:
            district = int(match.group(1))

            if 1 <= district <= 250:
                return district, "normalized"

    recovered = district_from_school(school)

    if recovered is not None:
        return recovered, "recovered_from_school"

    return "", "unresolved"


def normalize_year(value, student_id):
    value = value.strip()

    if value in {"2022", "2023", "2024", "2025"}:
        return int(value), "direct"

    if value in {"22", "23", "24", "25"}:
        return 2000 + int(value), "normalized"

    match = re.fullmatch(
        r"(2022|2023|2024|2025)/\d{4}",
        value
    )

    if match:
        return int(match.group(1)), "normalized"

    # If the year itself is unusable, try the normalized student ID.
    match = re.fullmatch(
        r"(2022|2023|2024|2025)_\d+",
        student_id
    )

    if match:
        return int(match.group(1)), "recovered_from_student_id"

    return "", "unresolved"


def normalize_binary(value, zero_values, one_values):
    value = value.strip()
    lowered = value.lower()

    if lowered in MISSING_MARKERS:
        return "", "unresolved"

    if lowered == "0":
        return 0, "direct"

    if lowered == "1":
        return 1, "direct"

    if lowered in zero_values:
        return 0, "normalized"

    if lowered in one_values:
        return 1, "normalized"

    return "", "unresolved"


def normalize_deprivation(value):
    value = value.strip()

    if value.lower() in MISSING_MARKERS:
        return "", "unresolved"

    # Decimal comma.
    candidate = value.replace(",", ".")

    # Percentage notation.
    if candidate.endswith("%"):
        try:
            number = float(candidate[:-1]) / 100

            if 0 <= number <= 1:
                return number, "normalized"

        except ValueError:
            pass

    try:
        number = float(candidate)

        if 0 <= number <= 1:
            return number, "direct"

        # Values such as 72.5 interpreted as percentage scale.
        if 1 < number <= 100:
            return number / 100, "normalized"

    except ValueError:
        pass

    # low / medium / high deliberately remain unresolved.
    return "", "unresolved"


OUTPUT_FIELDS = [
    "student_id",
    "district_id",
    "academic_year",
    "absent",
    "deprivation_score",
    "rural",
    "school_code",

    "student_status",
    "district_status",
    "year_status",
    "absence_status",
    "deprivation_status",
    "rural_status",
    "school_status",

    "source_file",
    "source_row",
]


clean_count = 0
quarantine_count = 0

status_counts = {
    field: {}
    for field in [
        "student",
        "district",
        "year",
        "absence",
        "deprivation",
        "rural",
        "school",
    ]
}


def count_status(field, status):
    status_counts[field][status] = (
        status_counts[field].get(status, 0) + 1
    )


with INPUT_PATH.open(
    "r",
    newline="",
    encoding="utf-8"
) as source, CLEAN_PATH.open(
    "w",
    newline="",
    encoding="utf-8"
) as clean_file, QUARANTINE_PATH.open(
    "w",
    newline="",
    encoding="utf-8"
) as quarantine_file:

    reader = csv.DictReader(source)

    clean_writer = csv.DictWriter(
        clean_file,
        fieldnames=OUTPUT_FIELDS
    )

    quarantine_writer = csv.DictWriter(
        quarantine_file,
        fieldnames=OUTPUT_FIELDS + ["quarantine_reason"]
    )

    clean_writer.writeheader()
    quarantine_writer.writeheader()

    for source_row, raw in enumerate(reader, start=2):

        row = {
            SCHEMA_MAP[key]: value
            for key, value in raw.items()
        }

        student_id, student_status = normalize_student(
            row["student_id"]
        )

        school_code, school_status = normalize_school(
            row["school_code"]
        )

        district_id, district_status = normalize_district(
            row["district_id"],
            school_code
        )

        academic_year, year_status = normalize_year(
            row["academic_year"],
            student_id
        )

        absent, absence_status = normalize_binary(
            row["absent"],
            ABSENCE_ZERO,
            ABSENCE_ONE
        )

        rural, rural_status = normalize_binary(
            row["rural"],
            RURAL_ZERO,
            RURAL_ONE
        )

        deprivation_score, deprivation_status = (
            normalize_deprivation(
                row["deprivation_score"]
            )
        )

        statuses = {
            "student": student_status,
            "district": district_status,
            "year": year_status,
            "absence": absence_status,
            "deprivation": deprivation_status,
            "rural": rural_status,
            "school": school_status,
        }

        for field, status in statuses.items():
            count_status(field, status)

        output = {
            "student_id": student_id,
            "district_id": district_id,
            "academic_year": academic_year,
            "absent": absent,
            "deprivation_score": deprivation_score,
            "rural": rural,
            "school_code": school_code,

            "student_status": student_status,
            "district_status": district_status,
            "year_status": year_status,
            "absence_status": absence_status,
            "deprivation_status": deprivation_status,
            "rural_status": rural_status,
            "school_status": school_status,

            "source_file": INPUT_PATH.name,
            "source_row": source_row,
        }

        # At this stage we require identity, geography, year,
        # and attendance outcome to be known.
        critical_missing = []

        if student_id == "":
            critical_missing.append("student_id")

        if district_id == "":
            critical_missing.append("district_id")

        if academic_year == "":
            critical_missing.append("academic_year")

        if absent == "":
            critical_missing.append("absent")

        if critical_missing:
            quarantine_count += 1

            output["quarantine_reason"] = (
                "UNRESOLVED_" + "_".join(
                    field.upper()
                    for field in critical_missing
                )
            )

            quarantine_writer.writerow(output)

        else:
            clean_count += 1
            clean_writer.writerow(output)


print()
print(f"Input:       {INPUT_PATH}")
print(f"Cleaned:     {CLEAN_PATH}")
print(f"Quarantine:  {QUARANTINE_PATH}")

print()
print(f"Accepted rows:    {clean_count:,}")
print(f"Quarantined rows: {quarantine_count:,}")

print("\nSTATUS COUNTS")

for field, values in status_counts.items():
    print(f"\n{field.upper()}")

    for status, count in sorted(values.items()):
        print(f"  {status:<25} {count:>10,}")
