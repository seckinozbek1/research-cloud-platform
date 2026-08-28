from pathlib import Path
import csv
import random
import re

SOURCE_DIR = Path("data/education_attendance/raw")
OUTPUT_DIR = Path("data/education_attendance/ministry_exports")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

random.seed(20260829)

DISTRICT_NAMES = {
    i: f"District {i:03d}"
    for i in range(1, 251)
}

RURAL_VARIANTS = {
    0: ["0", "N", "no", "NO", "Urban", "urban", "U"],
    1: ["1", "Y", "yes", "YES", "Rural", "rural", "R"],
}

ABSENCE_VARIANTS = {
    0: ["0", "N", "present", "P", "no", "Present"],
    1: ["1", "Y", "absent", "A", "yes", "Absent"],
}


def maybe_blank(value, probability):
    return "" if random.random() < probability else value


def messy_student_id(value):
    r = random.random()

    if r < 0.08:
        return f" {value} "
    if r < 0.13:
        return value.replace("_", "-")
    if r < 0.16:
        return value.lower()
    if r < 0.19:
        return ""
    if r < 0.22:
        return f"STU-{value}"

    return value


def messy_district(value):
    district = int(value)
    r = random.random()

    if r < 0.08:
        return ""
    if r < 0.14:
        return DISTRICT_NAMES[district]
    if r < 0.18:
        return f"D{district:03d}"
    if r < 0.21:
        return f" {district} "
    if r < 0.24:
        return str(district + 1000)
    if r < 0.27:
        name = DISTRICT_NAMES[district]
        return re.sub(
            r"District",
            random.choice(["Dist.", "district", "DIST"]),
            name
        )

    return str(district)


def messy_year(value):
    year = int(value)
    r = random.random()

    if r < 0.05:
        return ""
    if r < 0.08:
        return str(year)[2:]
    if r < 0.10:
        return f"{year}/{year + 1}"
    if r < 0.12:
        return str(random.choice([1999, 2037, 2205]))
    if r < 0.14:
        return f" {year} "

    return str(year)


def messy_binary(value, variants):
    numeric = int(value)
    r = random.random()

    if r < 0.07:
        return ""
    if r < 0.25:
        return random.choice(variants[numeric])
    if r < 0.28:
        return random.choice(["?", "unknown", "-", "n/a"])
    if r < 0.30:
        return random.choice(["2", "-1", "9"])

    return str(numeric)


def messy_deprivation(value):
    score = float(value)
    r = random.random()

    if r < 0.08:
        return ""
    if r < 0.14:
        return f"{score * 100:.1f}%"
    if r < 0.19:
        return f"{score:.4f}".replace(".", ",")
    if r < 0.23:
        return f"{score * 100:.2f}"
    if r < 0.26:
        return random.choice(["low", "medium", "high"])
    if r < 0.28:
        return str(round(random.uniform(1.2, 9.0), 3))
    if r < 0.30:
        return random.choice(["NA", "?", "missing"])

    return str(value)


def school_code(district_id):
    district = int(district_id)

    # Gives us an independent field from which district
    # can sometimes be reconstructed later.
    return f"SCH-{district:03d}-{random.randint(1, 80):02d}"


schemas = [
    [
        "student_id",
        "district_id",
        "academic_year",
        "absent",
        "deprivation_score",
        "rural",
        "school_code",
    ],
    [
        "student",
        "district",
        "year",
        "attendance_status",
        "deprivation",
        "location_type",
        "school",
    ],
    [
        "StudentID",
        "DistrictCode",
        "AcademicYear",
        "AbsentFlag",
        "DeprivationIndex",
        "RuralUrban",
        "SchoolCode",
    ],
    [
        "student_id",
        "school_code",
        "district_id",
        "rural",
        "academic_year",
        "deprivation_score",
        "absent",
    ],
]


source_files = sorted(SOURCE_DIR.glob("attendance_*.csv"))

writers = []
handles = []

try:
    for i, schema in enumerate(schemas):
        path = OUTPUT_DIR / f"regional_attendance_export_{i + 1}.csv"
        handle = path.open("w", newline="", encoding="utf-8")
        writer = csv.writer(handle)
        writer.writerow(schema)

        handles.append(handle)
        writers.append(writer)

    row_counter = 0

    for source_path in source_files:
        print(f"Reading source fixture: {source_path}")

        with source_path.open("r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            for row in reader:
                export_id = row_counter % 4
                row_counter += 1

                sid = messy_student_id(row["student_id"])
                district = messy_district(row["district_id"])
                year = messy_year(row["academic_year"])
                absent = messy_binary(
                    row["absent"],
                    ABSENCE_VARIANTS
                )
                deprivation = messy_deprivation(
                    row["deprivation_score"]
                )
                rural = messy_binary(
                    row["rural"],
                    RURAL_VARIANTS
                )
                school = school_code(row["district_id"])

                if random.random() < 0.06:
                    school = ""

                values = [
                    sid,
                    district,
                    year,
                    absent,
                    deprivation,
                    rural,
                    school,
                ]

                # Rearrange to match the fourth export's different order.
                if export_id == 3:
                    values = [
                        sid,
                        school,
                        district,
                        rural,
                        year,
                        deprivation,
                        absent,
                    ]

                writers[export_id].writerow(values)

                # Exact or near duplicate.
                if random.random() < 0.035:
                    writers[export_id].writerow(values)

                # Conflicting duplicate.
                if random.random() < 0.015:
                    conflict = list(values)

                    # Deliberately alter one field.
                    conflict[-1] = random.choice(
                        ["0", "1", "A", "P", "?", ""]
                    )

                    writers[export_id].writerow(conflict)

finally:
    for handle in handles:
        handle.close()

print()
print(f"Created ministry exports in: {OUTPUT_DIR}")
