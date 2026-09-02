from pathlib import Path
import json
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )

from governance.lineage import check_staleness


CATALOG = (
    PROJECT_ROOT
    / "governance"
    / "data_catalog_governed.csv"
)

POLICY = (
    PROJECT_ROOT
    / "governance"
    / "waste_gis_policy.json"
)


def in_waste_scope(path):
    return (
        "waste_gis" in str(path)
        or "distributed_ml" in str(path)
    )


def main():
    df = pd.read_csv(CATALOG)

    policy = json.loads(
        POLICY.read_text()
    )

    scoped = df[
        df["path"]
        .apply(in_waste_scope)
    ].copy()

    failures = []

    for row in scoped.itertuples():

        if (
            policy["deployment_gate"]
            ["require_metadata"]
            and not bool(
                getattr(
                    row,
                    "metadata_complete",
                    False,
                )
            )
        ):
            failures.append(
                (
                    row.path,
                    "metadata_incomplete",
                )
            )

        if (
            policy["deployment_gate"]
            ["require_privacy_scan"]
            and not bool(
                getattr(
                    row,
                    "privacy_complete",
                    False,
                )
            )
        ):
            failures.append(
                (
                    row.path,
                    "privacy_scan_incomplete",
                )
            )

        sensitivity = getattr(
            row,
            "sensitivity",
            None,
        )

        if (
            policy["deployment_gate"]
            ["block_restricted_review"]
            and sensitivity
            == "restricted_review_required"
        ):
            failures.append(
                (
                    row.path,
                    "restricted_privacy",
                )
            )

    if (
        policy["deployment_gate"]
        ["require_current_lineage"]
    ):
        for item in check_staleness():

            if not in_waste_scope(
                item["output"]
            ):
                continue

            if item["status"] != "current":
                failures.append(
                    (
                        item["output"],
                        f"lineage_{item['status']}",
                    )
                )

    print(
        "=== WASTE-GIS GOVERNANCE GATE ==="
    )

    print(
        "Scoped assets:",
        len(scoped),
    )

    print(
        "Failures:",
        len(failures),
    )

    if failures:
        for path, reason in failures:
            print(
                f"BLOCK  {reason:28} {path}"
            )

        print()
        print(
            "GATE RESULT: BLOCK"
        )

        sys.exit(1)

    print()
    print(
        "GATE RESULT: PASS"
    )


if __name__ == "__main__":
    main()
