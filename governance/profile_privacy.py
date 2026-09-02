from pathlib import Path
import json
import re

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

CATALOG_PATH = (
    PROJECT_ROOT
    / "governance"
    / "data_catalog_enriched.csv"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "governance"
    / "privacy_profile.csv"
)

SUPPORTED = {
    ".csv",
    ".parquet",
    ".json",
    ".geojson",
}

MAX_ROWS = 2000


EMAIL_RE = re.compile(
    r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
)

PHONE_RE = re.compile(
    r"^\+?[\d\s().-]{7,20}$"
)


PSEUDONYM_RE = re.compile(
    r"^[0-9a-fA-F]{16,64}$"
)

SECRET_RE = re.compile(
    r"(api[_-]?key|secret|password|token|private[_-]?key)",
    re.I,
)


DATE_COLUMN_TOKENS = {
    "date",
    "datetime",
    "timestamp",
    "year",
    "month",
    "day",
    "collection_date",
    "event_date",
    "pickup_time",
    "shift_start",
    "shift_end",
}

COLUMN_SIGNALS = {
    "email": [
        "email",
        "e_mail",
        "mail_address",
    ],

    "phone": [
        "phone",
        "mobile",
        "telephone",
        "tel_no",
    ],

    "person_name": [
        "first_name",
        "last_name",
        "full_name",
        "surname",
        "given_name",
        "person_name",
    ],

    "personal_id": [
        "national_id",
        "passport",
        "ssn",
        "tc_kimlik",
        "identity_number",
        "person_id",
        "customer_id",
        "employee_id",
        "student_id",
    ],

    "address": [
        "home_address",
        "residential_address",
        "postal_address",
    ],

    "date_of_birth": [
        "date_of_birth",
        "birth_date",
        "dob",
    ],

    "precise_location": [
        "latitude",
        "longitude",
        "lat",
        "lon",
        "lng",
    ],
}


def normalize(name):
    return (
        str(name)
        .strip()
        .lower()
        .replace(" ", "_")
        .replace("-", "_")
    )


def read_sample(path, extension):
    if extension == ".csv":
        return pd.read_csv(
            path,
            nrows=MAX_ROWS,
        )

    if extension == ".parquet":
        df = pd.read_parquet(path)

        return df.head(
            MAX_ROWS
        )

    if extension in {
        ".json",
        ".geojson",
    }:
        try:
            return pd.read_json(
                path
            ).head(
                MAX_ROWS
            )
        except Exception:
            # Some JSON artefacts are scalar/nested reports
            # rather than tabular datasets.
            obj = json.loads(
                path.read_text(
                    errors="ignore"
                )
            )

            if isinstance(
                obj,
                list,
            ):
                return pd.json_normalize(
                    obj[:MAX_ROWS]
                )

            if isinstance(
                obj,
                dict,
            ):
                return pd.json_normalize(
                    obj
                )

    raise ValueError(
        "Unsupported structure"
    )


def column_name_signals(columns):
    findings = []

    normalized = {
        str(c): normalize(c)
        for c in columns
    }

    for original, column in (
        normalized.items()
    ):
        if SECRET_RE.search(
            column
        ):
            findings.append(
                (
                    original,
                    "credential_or_secret",
                    5,
                )
            )

        for signal, names in (
            COLUMN_SIGNALS.items()
        ):
            if column in names:
                weight = {
                    "email": 5,
                    "phone": 5,
                    "personal_id": 5,
                    "person_name": 3,
                    "address": 4,
                    "date_of_birth": 4,
                    "precise_location": 2,
                }[signal]

                findings.append(
                    (
                        original,
                        signal,
                        weight,
                    )
                )

    return findings


def value_signals(df):
    findings = []

    for column in df.columns:
        series = (
            df[column]
            .dropna()
            .astype(str)
            .head(500)
        )

        if series.empty:
            continue

        email_hits = int(
            series.str.match(
                EMAIL_RE
            ).sum()
        )

        if email_hits >= 2:
            findings.append(
                (
                    str(column),
                    "email_values",
                    5,
                )
            )

        normalized_column = normalize(
            column
        )

        temporal_column = (
            normalized_column in DATE_COLUMN_TOKENS

            # Explicit temporal suffixes.
            or normalized_column.endswith("_date")
            or normalized_column.endswith("_time")
            or normalized_column.endswith("_timestamp")

            # Explicit temporal prefixes.
            or normalized_column.startswith("date_")
            or normalized_column.startswith("time_")
            or normalized_column.startswith("timestamp_")

            # Known year-valued fields.
            or normalized_column in {
                "academic_year",
                "fiscal_year",
                "calendar_year",
                "school_year",
                "year",
            }
        )

        # Date/time remains privacy-relevant as a
        # quasi-identifier, but it must not be confused
        # with a phone number.
        if temporal_column:
            findings.append(
                (
                    str(column),
                    "temporal_quasi_identifier",
                    2,
                )
            )

        # Phone detection is only applied to non-temporal
        # text columns.
        if (
            df[column].dtype == "object"
            and len(series) >= 5
            and not temporal_column
        ):
            phone_hits = int(
                series.str.match(
                    PHONE_RE
                ).sum()
            )

            if (
                phone_hits
                / len(series)
                >= 0.8
            ):
                findings.append(
                    (
                        str(column),
                        "phone_like_values",
                        4,
                    )
                )

    return findings


def normalize_pseudonymized_identifiers(
    df,
    findings,
):
    """
    Downgrade direct-identifier column-name signals when
    the actual stored values are stable pseudonyms/hashes.

    Pseudonymized identifiers remain privacy-relevant;
    they are not treated as anonymous data.
    """

    updated = []

    for column, signal, weight in findings:

        if (
            signal == "personal_id"
            and column in df.columns
        ):
            values = (
                df[column]
                .dropna()
                .astype(str)
                .head(500)
            )

            if len(values) >= 5:
                matches = (
                    values
                    .str.match(
                        PSEUDONYM_RE
                    )
                    .mean()
                )

                if matches >= 0.95:
                    updated.append(
                        (
                            column,
                            "pseudonymized_identifier",
                            3,
                        )
                    )

                    continue

        updated.append(
            (
                column,
                signal,
                weight,
            )
        )

    return updated


def classify(findings):
    if not findings:
        return (
            "internal_non_personal",
            0,
        )

    score = sum(
        weight
        for _, _, weight
        in findings
    )

    signals = {
        signal
        for _, signal, _
        in findings
    }

    strong = {
        "credential_or_secret",
        "email",
        "email_values",
        "phone",
        "phone_like_values",
        "personal_id",
        "date_of_birth",
    }

    if signals & strong:
        return (
            "restricted_review_required",
            score,
        )

    if score >= 4:
        return (
            "potentially_personal",
            score,
        )

    return (
        "internal_non_personal",
        score,
    )


def main():
    catalog = pd.read_csv(
        CATALOG_PATH
    )

    candidates = catalog[
        catalog["extension"]
        .isin(SUPPORTED)
    ].copy()

    rows = []

    for r in candidates.itertuples():

        path = (
            PROJECT_ROOT
            / r.path
        )

        try:
            sample = read_sample(
                path,
                r.extension,
            )

            findings = (
                column_name_signals(
                    sample.columns
                )
                + value_signals(
                    sample
                )
            )

            findings = (
                normalize_pseudonymized_identifiers(
                    sample,
                    findings,
                )
            )

            classification, score = (
                classify(findings)
            )

            rows.append(
                {
                    "path":
                        r.path,

                    "scan_status":
                        "scanned",

                    "rows_sampled":
                        min(
                            len(sample),
                            MAX_ROWS,
                        ),

                    "columns_scanned":
                        len(
                            sample.columns
                        ),

                    "privacy_score":
                        score,

                    "privacy_classification":
                        classification,

                    "signals":
                        json.dumps(
                            [
                                {
                                    "column":
                                        c,

                                    "signal":
                                        s,

                                    "weight":
                                        w,
                                }
                                for c, s, w
                                in findings
                            ]
                        ),
                }
            )

        except Exception as exc:
            rows.append(
                {
                    "path":
                        r.path,

                    "scan_status":
                        "scan_failed",

                    "rows_sampled":
                        0,

                    "columns_scanned":
                        0,

                    "privacy_score":
                        None,

                    "privacy_classification":
                        "review_required",

                    "signals":
                        json.dumps(
                            {
                                "error":
                                    str(exc)
                            }
                        ),
                }
            )

    result = pd.DataFrame(
        rows
    )

    result.to_csv(
        OUTPUT_PATH,
        index=False,
    )

    print(
        "Privacy profile:",
        OUTPUT_PATH,
    )

    print()
    print(
        "Assets scanned:",
        len(result),
    )

    print()
    print(
        "=== CLASSIFICATION ==="
    )

    print(
        result[
            "privacy_classification"
        ]
        .value_counts(
            dropna=False
        )
        .to_string()
    )

    print()
    print(
        "=== SCAN STATUS ==="
    )

    print(
        result[
            "scan_status"
        ]
        .value_counts()
        .to_string()
    )

    risky = result[
        result[
            "privacy_classification"
        ].isin(
            [
                "potentially_personal",
                "restricted_review_required",
            ]
        )
    ]

    if not risky.empty:
        print()
        print(
            "=== PRIVACY FLAGS ==="
        )

        print(
            risky[
                [
                    "path",
                    "privacy_score",
                    "privacy_classification",
                    "signals",
                ]
            ]
            .head(20)
            .to_string(
                index=False
            )
        )


if __name__ == "__main__":
    main()
