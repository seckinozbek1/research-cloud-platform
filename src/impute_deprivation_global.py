from pathlib import Path
from collections import defaultdict
from statistics import median
import csv
import time

INPUT_PATH = Path(
    "data/education_attendance/global_resolution/"
    "national_attendance_resolved.csv"
)

OUTPUT_DIR = Path(
    "data/education_attendance/curated_national"
)

OUTPUT_PATH = OUTPUT_DIR / "national_attendance_imputed.csv"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

start = time.perf_counter()

# --------------------------------------------------
# PASS 1: compute district-year deprivation medians
# --------------------------------------------------

values_by_group = defaultdict(list)

with INPUT_PATH.open("r", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)

    for row in reader:
        value = row["deprivation_score"]

        if value != "":
            key = (
                row["district_id"],
                row["academic_year"],
            )

            values_by_group[key].append(float(value))


medians = {
    key: median(values)
    for key, values in values_by_group.items()
    if values
}

print(f"District-year medians computed: {len(medians):,}")


# --------------------------------------------------
# PASS 2: fill unresolved deprivation values
# --------------------------------------------------

rows_written = 0
imputed_count = 0
still_missing = 0

with INPUT_PATH.open(
    "r",
    newline="",
    encoding="utf-8"
) as source, OUTPUT_PATH.open(
    "w",
    newline="",
    encoding="utf-8"
) as target:

    reader = csv.DictReader(source)

    output_fields = reader.fieldnames + [
        "deprivation_imputed",
        "imputation_method",
    ]

    writer = csv.DictWriter(
        target,
        fieldnames=output_fields
    )

    writer.writeheader()

    for row in reader:
        value = row["deprivation_score"]

        if value == "":
            key = (
                row["district_id"],
                row["academic_year"],
            )

            group_median = medians.get(key)

            if group_median is not None:
                row["deprivation_score"] = group_median
                row["deprivation_imputed"] = 1
                row["imputation_method"] = (
                    "district_year_median"
                )

                imputed_count += 1

            else:
                row["deprivation_imputed"] = 0
                row["imputation_method"] = (
                    "unresolved_no_group_median"
                )

                still_missing += 1

        else:
            row["deprivation_imputed"] = 0
            row["imputation_method"] = "observed_or_repaired"

        writer.writerow(row)
        rows_written += 1


elapsed = time.perf_counter() - start

print()
print(f"Rows written:       {rows_written:,}")
print(f"Values imputed:     {imputed_count:,}")
print(f"Still unresolved:   {still_missing:,}")
print(f"Output:             {OUTPUT_PATH}")
print(f"Elapsed:            {elapsed:.3f} seconds")
