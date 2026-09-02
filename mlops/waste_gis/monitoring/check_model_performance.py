from pathlib import Path
import json

import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


PROJECT_ROOT = Path(__file__).resolve().parents[3]

FEATURE_TABLE_PATH = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "waste_gis"
    / "feature_store"
    / "waste_demand_v1.parquet"
)

PREDICTION_PATH = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "waste_gis"
    / "predictions"
    / "waste_demand_candidate.parquet"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "waste_gis"
    / "monitoring"
    / "model_performance_report.json"
)

REFERENCE_MAE = 4230.332226
DEGRADATION_THRESHOLD = 1.25


def main():
    truth = pd.read_parquet(
        FEATURE_TABLE_PATH
    )[
        [
            "zone_id",
            "collection_date",
            "waste_kg",
        ]
    ]

    predictions = pd.read_parquet(
        PREDICTION_PATH
    )

    df = truth.merge(
        predictions,
        on=[
            "zone_id",
            "collection_date",
        ],
        how="inner",
        validate="one_to_one",
    )

    mae = mean_absolute_error(
        df["waste_kg"],
        df["predicted_waste_kg"],
    )

    rmse = mean_squared_error(
        df["waste_kg"],
        df["predicted_waste_kg"],
    ) ** 0.5

    r2 = r2_score(
        df["waste_kg"],
        df["predicted_waste_kg"],
    )

    mae_ratio = mae / REFERENCE_MAE

    degraded = (
        mae_ratio >= DEGRADATION_THRESHOLD
    )

    report = {
        "rows": len(df),
        "mae": mae,
        "rmse": rmse,
        "r2": r2,
        "reference_mae": REFERENCE_MAE,
        "mae_ratio": mae_ratio,
        "degradation_threshold": DEGRADATION_THRESHOLD,
        "performance_degraded": degraded,
    }

    OUTPUT_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_PATH.write_text(
        json.dumps(
            report,
            indent=2,
        )
    )

    print("Model performance check completed.")
    print(f"Rows                : {len(df):,}")
    print(f"MAE                 : {mae:,.2f}")
    print(f"RMSE                : {rmse:,.2f}")
    print(f"R²                  : {r2:.4f}")
    print(f"Reference MAE       : {REFERENCE_MAE:,.2f}")
    print(f"MAE ratio           : {mae_ratio:.3f}")
    print(
        "Performance degraded:",
        degraded,
    )
    print("Report              :", OUTPUT_PATH)


if __name__ == "__main__":
    main()
