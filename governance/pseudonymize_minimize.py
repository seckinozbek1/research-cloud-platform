from pathlib import Path
import hashlib
import os

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

INPUT_ROOT = (
    PROJECT_ROOT
    / "data"
    / "education_attendance"
)

OUTPUT_ROOT = (
    PROJECT_ROOT
    / "data"
    / "curated_privacy_safe"
    / "education_attendance"
)

DIRECT_IDENTIFIER_COLUMNS = {
    "student_id",
    "person_id",
    "employee_id",
    "customer_id",
    "national_id",
    "passport",
    "ssn",
    "tc_kimlik",
}

DROP_IF_PRESENT = {
    "email",
    "phone",
    "mobile",
    "home_address",
    "residential_address",
}


def pseudonymize(value, salt):
    if pd.isna(value):
        return value

    payload = (
        salt
        + "::"
        + str(value)
    ).encode("utf-8")

    return hashlib.sha256(
        payload
    ).hexdigest()[:20]


def transform_file(
    input_path,
    output_path,
    salt,
):
    df = pd.read_csv(
        input_path
    )

    changed = []

    for column in list(df.columns):

        normalized = (
            str(column)
            .strip()
            .lower()
        )

        if (
            normalized
            in DIRECT_IDENTIFIER_COLUMNS
        ):
            df[column] = (
                df[column]
                .apply(
                    lambda x:
                    pseudonymize(
                        x,
                        salt,
                    )
                )
            )

            changed.append(
                f"pseudonymized:{column}"
            )

        elif (
            normalized
            in DROP_IF_PRESENT
        ):
            df = df.drop(
                columns=[column]
            )

            changed.append(
                f"dropped:{column}"
            )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_csv(
        output_path,
        index=False,
    )

    return changed


def main():
    salt = os.environ.get(
        "GOVERNANCE_PSEUDONYM_SALT"
    )

    if not salt:
        raise RuntimeError(
            "Set GOVERNANCE_PSEUDONYM_SALT before running."
        )

    files = list(
        INPUT_ROOT.rglob("*.csv")
    )

    print(
        "CSV files discovered:",
        len(files),
    )

    transformed = 0

    for input_path in files:

        relative = (
            input_path
            .relative_to(INPUT_ROOT)
        )

        output_path = (
            OUTPUT_ROOT
            / relative
        )

        changes = transform_file(
            input_path,
            output_path,
            salt,
        )

        if changes:
            transformed += 1

            print(
                "SAFE COPY:",
                relative,
            )

            for change in changes:
                print(
                    "  -",
                    change,
                )

    print()
    print(
        "Files with privacy transformations:",
        transformed,
    )

    print(
        "Output root:",
        OUTPUT_ROOT,
    )


if __name__ == "__main__":
    main()
