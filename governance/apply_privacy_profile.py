from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

CATALOG_PATH = (
    PROJECT_ROOT
    / "governance"
    / "data_catalog_enriched.csv"
)

PROFILE_PATH = (
    PROJECT_ROOT
    / "governance"
    / "privacy_profile.csv"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "governance"
    / "data_catalog_governed.csv"
)


def main():
    catalog = pd.read_csv(
        CATALOG_PATH
    )

    privacy = pd.read_csv(
        PROFILE_PATH
    )

    privacy_fields = privacy[
        [
            "path",
            "scan_status",
            "privacy_score",
            "privacy_classification",
            "signals",
        ]
    ].copy()

    result = catalog.merge(
        privacy_fields,
        on="path",
        how="left",
    )

    # ------------------------------------------------------
    # Assets successfully profiled inherit the profiler's
    # classification automatically.
    # ------------------------------------------------------

    scanned = (
        result["scan_status"]
        == "scanned"
    )

    result.loc[
        scanned,
        "sensitivity"
    ] = result.loc[
        scanned,
        "privacy_classification"
    ]

    result[
        "privacy_complete"
    ] = scanned

    # ------------------------------------------------------
    # Privacy action level.
    #
    # This is deliberately different from sensitivity.
    # It tells downstream governance gates what action to
    # take.
    # ------------------------------------------------------

    def privacy_action(row):

        status = row[
            "sensitivity"
        ]

        if (
            status
            == "restricted_review_required"
        ):
            return "block_until_review"

        if (
            status
            == "potentially_personal"
        ):
            return "allow_with_privacy_controls"

        if (
            status
            == "internal_non_personal"
        ):
            return "standard_internal_controls"

        return "review_required"

    result[
        "privacy_action"
    ] = result.apply(
        privacy_action,
        axis=1,
    )

    # ------------------------------------------------------
    # Governance is not fully complete yet.
    #
    # We still need lineage + quality checks later.
    # For now this tells us whether metadata/privacy are
    # sufficiently resolved.
    # ------------------------------------------------------

    result[
        "metadata_privacy_ready"
    ] = (
        result["metadata_complete"]
        & result["privacy_complete"]
        & ~result[
            "sensitivity"
        ].isin(
            [
                "review_required",
                "restricted_review_required",
            ]
        )
    )

    result[
        "governance_complete"
    ] = False

    result.to_csv(
        OUTPUT_PATH,
        index=False,
    )

    print(
        "Governed catalog:",
        OUTPUT_PATH,
    )

    print()
    print(
        "=== SENSITIVITY ==="
    )

    print(
        result["sensitivity"]
        .value_counts(
            dropna=False
        )
        .to_string()
    )

    print()
    print(
        "=== PRIVACY ACTION ==="
    )

    print(
        result["privacy_action"]
        .value_counts(
            dropna=False
        )
        .to_string()
    )

    print()
    print(
        "Metadata + privacy ready:",
        int(
            result[
                "metadata_privacy_ready"
            ].sum()
        ),
        "/",
        len(result),
    )

    print()
    print(
        "Blocked pending review:",
        int(
            result[
                "privacy_action"
            ].eq(
                "block_until_review"
            )
            .sum()
        ),
    )


if __name__ == "__main__":
    main()
