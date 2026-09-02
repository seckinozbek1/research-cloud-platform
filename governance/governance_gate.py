from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )

import pandas as pd

from governance.lineage import check_staleness


PROJECT_ROOT = Path(__file__).resolve().parents[1]

CATALOG = (
    PROJECT_ROOT
    / "governance"
    / "data_catalog_governed.csv"
)


def main():
    df = pd.read_csv(CATALOG)

    failures = []

    for row in df.itertuples():

        if not bool(
            getattr(
                row,
                "metadata_complete",
                False,
            )
        ):
            failures.append(
                (
                    row.path,
                    "metadata_incomplete",
                )
            )

        if (
            getattr(
                row,
                "privacy_action",
                None,
            )
            == "block_until_review"
        ):
            failures.append(
                (
                    row.path,
                    "privacy_block",
                )
            )

    for item in check_staleness():

        if item["status"] in {
            "potentially_stale",
            "missing",
        }:
            failures.append(
                (
                    item["output"],
                    f"lineage_{item['status']}",
                )
            )

    print("=== GOVERNANCE GATE ===")
    print("Assets:", len(df))
    print("Failures:", len(failures))

    if failures:
        for path, reason in failures[:30]:
            print(
                f"BLOCK  {reason:25} {path}"
            )

        print()
        print("GATE RESULT: BLOCK")
        sys.exit(1)

    print("GATE RESULT: PASS")


if __name__ == "__main__":
    main()
