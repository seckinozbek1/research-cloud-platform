from pathlib import Path
import json

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]

SPEC_PATH = (
    PROJECT_ROOT
    / "mlops"
    / "waste_gis"
    / "feature_store"
    / "feature_spec.json"
)

SOURCE_PATH = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "waste_gis"
    / "waste_operations.csv"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "waste_gis"
    / "feature_store"
    / "waste_demand_v1.parquet"
)


def main():
    spec = json.loads(
        SPEC_PATH.read_text()
    )

    source = pd.read_csv(
        SOURCE_PATH,
        parse_dates=[
            spec["timestamp"]
        ],
    )

    feature_names = [
        feature["name"]
        for feature in spec["features"]
    ]

    required = [
        spec["entity"],
        spec["timestamp"],
        *feature_names,
        spec["target"],
    ]

    missing = [
        column
        for column in required
        if column not in source.columns
    ]

    if missing:
        raise RuntimeError(
            f"Missing source columns: {missing}"
        )

    table = source[required].copy()

    for feature in spec["features"]:
        table[feature["name"]] = (
            table[feature["name"]]
            .astype(feature["dtype"])
        )

    if table[
        [
            spec["entity"],
            spec["timestamp"],
        ]
    ].duplicated().any():
        raise RuntimeError(
            "Duplicate entity/timestamp rows "
            "in feature table."
        )

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    table.to_parquet(
        OUTPUT_PATH,
        index=False,
    )

    print("Local feature table materialized.")
    print(
        f"Feature set   : "
        f"{spec['feature_set']}"
    )
    print(
        f"Entity        : "
        f"{spec['entity']}"
    )
    print(
        f"Rows          : "
        f"{len(table):,}"
    )
    print(
        f"Features      : "
        f"{len(feature_names)}"
    )
    print(
        f"Date range    : "
        f"{table[spec['timestamp']].min().date()} "
        f"→ "
        f"{table[spec['timestamp']].max().date()}"
    )
    print(
        f"Missing values: "
        f"{int(table[feature_names].isna().sum().sum()):,}"
    )
    print(f"Output        : {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
