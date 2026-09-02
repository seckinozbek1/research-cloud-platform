from pathlib import Path
import json

import mlflow
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

FEATURE_SPEC_PATH = (
    PROJECT_ROOT
    / "mlops"
    / "waste_gis"
    / "feature_store"
    / "feature_spec.json"
)

FEATURE_TABLE_PATH = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "waste_gis"
    / "feature_store"
    / "waste_demand_v1.parquet"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "waste_gis"
    / "predictions"
    / "waste_demand_candidate.parquet"
)

MODEL_URI = "models:/waste-demand-forecast@candidate"


def main():
    spec = json.loads(
        FEATURE_SPEC_PATH.read_text()
    )

    features = [
        feature["name"]
        for feature in spec["features"]
    ]

    table = pd.read_parquet(
        FEATURE_TABLE_PATH
    )

    mlflow.set_tracking_uri(
        f"sqlite:///{PROJECT_ROOT / 'mlflow.db'}"
    )

    model = mlflow.pyfunc.load_model(
        MODEL_URI
    )

    predictions = model.predict(
        table[features]
    )

    result = table[
        [
            spec["entity"],
            spec["timestamp"],
        ]
    ].copy()

    result["predicted_waste_kg"] = predictions

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    result.to_parquet(
        OUTPUT_PATH,
        index=False,
    )

    print("Batch inference completed.")
    print(f"Model URI   : {MODEL_URI}")
    print(f"Rows        : {len(result):,}")
    print(
        "Date range  : "
        f"{result[spec['timestamp']].min().date()} "
        "→ "
        f"{result[spec['timestamp']].max().date()}"
    )
    print(
        "Mean predict: "
        f"{result['predicted_waste_kg'].mean():,.2f} kg"
    )
    print(f"Output      : {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
