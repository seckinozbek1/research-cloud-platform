from pathlib import Path

import mlflow
import mlflow.sklearn
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATA_PATH = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "waste_gis"
    / "waste_operations.csv"
)

MLFLOW_DB_PATH = PROJECT_ROOT / "mlflow.db"

EXPERIMENT_NAME = "waste-volume-forecasting"
TEST_DAYS = 30

FEATURES = [
    "population_2025",
    "population_density_2025",
    "road_density_km_per_km2",
    "container_capacity_kg",
    "days_since_last_pickup",
    "weekend",
    "temperature_c",
    "rain_mm",
    "previous_waste_kg",
]

TARGET = "waste_kg"


def metrics(y_true, y_pred):
    return {
        "mae": mean_absolute_error(y_true, y_pred),
        "rmse": mean_squared_error(y_true, y_pred) ** 0.5,
        "r2": r2_score(y_true, y_pred),
    }


def main() -> None:
    df = pd.read_csv(
        DATA_PATH,
        parse_dates=["collection_date"],
    )

    cutoff = (
        df["collection_date"].max()
        - pd.to_timedelta(TEST_DAYS - 1, unit="D")
    )

    train = df[df["collection_date"] < cutoff].copy()
    test = df[df["collection_date"] >= cutoff].copy()

    X_train = train[FEATURES]
    y_train = train[TARGET]

    X_test = test[FEATURES]
    y_test = test[TARGET]

    baseline_pred = test["previous_waste_kg"]

    model = LinearRegression()
    model.fit(X_train, y_train)

    model_pred = model.predict(X_test)

    baseline = metrics(y_test, baseline_pred)
    linear = metrics(y_test, model_pred)

    mlflow.set_tracking_uri(f"sqlite:///{MLFLOW_DB_PATH}")
    mlflow.set_experiment(EXPERIMENT_NAME)

    with mlflow.start_run(run_name="linear-regression-v1") as run:
        mlflow.log_params(
            {
                "model_type": "LinearRegression",
                "test_days": TEST_DAYS,
                "feature_count": len(FEATURES),
                "target": TARGET,
                "train_rows": len(train),
                "test_rows": len(test),
                "cutoff_date": cutoff.date().isoformat(),
            }
        )

        mlflow.log_metrics(
            {
                "baseline_mae": baseline["mae"],
                "baseline_rmse": baseline["rmse"],
                "baseline_r2": baseline["r2"],
                "model_mae": linear["mae"],
                "model_rmse": linear["rmse"],
                "model_r2": linear["r2"],
            }
        )

        mlflow.sklearn.log_model(
            sk_model=model,
            name="model",
        )

        print("MLflow run completed.")
        print(f"Experiment : {EXPERIMENT_NAME}")
        print(f"Run ID     : {run.info.run_id}")
        print()
        print("=== NAIVE BASELINE ===")
        print(f"MAE  : {baseline['mae']:,.2f} kg")
        print(f"RMSE : {baseline['rmse']:,.2f} kg")
        print(f"R²   : {baseline['r2']:.4f}")
        print()
        print("=== LINEAR REGRESSION ===")
        print(f"MAE  : {linear['mae']:,.2f} kg")
        print(f"RMSE : {linear['rmse']:,.2f} kg")
        print(f"R²   : {linear['r2']:.4f}")


if __name__ == "__main__":
    main()
