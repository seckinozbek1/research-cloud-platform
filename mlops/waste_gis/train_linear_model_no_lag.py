from pathlib import Path
import hashlib
import json
import subprocess

import mlflow
import mlflow.sklearn
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score


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
RUN_NAME = "linear-regression-no-lag-reproducible-v1"

TEST_DAYS = 30

FEATURE_SPEC_PATH = (
    PROJECT_ROOT
    / "mlops"
    / "waste_gis"
    / "feature_store"
    / "feature_spec.json"
)

FEATURE_SPEC = json.loads(
    FEATURE_SPEC_PATH.read_text()
)

FEATURES = [
    feature["name"]
    for feature in FEATURE_SPEC["features"]
]

TARGET = FEATURE_SPEC["target"]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def main() -> None:
    df = pd.read_csv(
        DATA_PATH,
        parse_dates=["collection_date"],
    )

    cutoff_date = (
        df["collection_date"].max()
        - pd.to_timedelta(TEST_DAYS - 1, unit="D")
    )

    train = df[
        df["collection_date"] < cutoff_date
    ].copy()

    test = df[
        df["collection_date"] >= cutoff_date
    ].copy()

    X_train = train[FEATURES]
    y_train = train[TARGET]

    X_test = test[FEATURES]
    y_test = test[TARGET]

    model = LinearRegression()
    model.fit(X_train, y_train)

    pred = model.predict(X_test)

    mae = mean_absolute_error(y_test, pred)
    rmse = mean_squared_error(
        y_test,
        pred,
    ) ** 0.5
    r2 = r2_score(y_test, pred)

    baseline_pred = test["previous_waste_kg"]

    baseline_mae = mean_absolute_error(
        y_test,
        baseline_pred,
    )

    baseline_rmse = mean_squared_error(
        y_test,
        baseline_pred,
    ) ** 0.5

    baseline_r2 = r2_score(
        y_test,
        baseline_pred,
    )

    data_hash = sha256_file(DATA_PATH)
    commit = git_commit()

    reproducibility_metadata = {
        "training_data_path": str(
            DATA_PATH.relative_to(PROJECT_ROOT)
        ),
        "training_data_sha256": data_hash,
        "features": FEATURES,
        "target": TARGET,
        "test_days": TEST_DAYS,
        "cutoff_date": str(cutoff_date.date()),
        "train_rows": len(train),
        "test_rows": len(test),
        "git_commit": commit,
    }

    metadata_path = (
        PROJECT_ROOT
        / "metadata"
        / "waste_gis_training_metadata.json"
    )

    metadata_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    metadata_path.write_text(
        json.dumps(
            reproducibility_metadata,
            indent=2,
        )
    )

    mlflow.set_tracking_uri(
        f"sqlite:///{MLFLOW_DB_PATH}"
    )

    mlflow.set_experiment(
        EXPERIMENT_NAME
    )

    with mlflow.start_run(
        run_name=RUN_NAME
    ):
        mlflow.log_params(
            {
                "model_type": "LinearRegression",
                "test_days": TEST_DAYS,
                "feature_count": len(FEATURES),
                "target": TARGET,
                "train_rows": len(train),
                "test_rows": len(test),
                "cutoff_date": str(
                    cutoff_date.date()
                ),
                "training_data_sha256": data_hash,
                "git_commit": commit,
            }
        )

        mlflow.log_metrics(
            {
                "baseline_mae": baseline_mae,
                "baseline_rmse": baseline_rmse,
                "baseline_r2": baseline_r2,
                "model_mae": mae,
                "model_rmse": rmse,
                "model_r2": r2,
            }
        )

        mlflow.log_artifact(
            str(metadata_path),
            artifact_path="reproducibility",
        )

        mlflow.log_text(
            json.dumps(
                FEATURES,
                indent=2,
            ),
            "reproducibility/features.json",
        )

        mlflow.sklearn.log_model(
            sk_model=model,
            name="model",
            input_example=X_train.head(5),
        )

        run = mlflow.active_run()

        print("Reproducible training run completed.")
        print(f"Run ID              : {run.info.run_id}")
        print(f"Run name            : {RUN_NAME}")
        print(f"Training data hash  : {data_hash}")
        print(f"Git commit          : {commit}")
        print(f"Feature count       : {len(FEATURES)}")
        print(f"Cutoff date         : {cutoff_date.date()}")
        print()
        print(f"MAE                 : {mae:,.2f}")
        print(f"RMSE                : {rmse:,.2f}")
        print(f"R²                  : {r2:.4f}")


if __name__ == "__main__":
    main()
