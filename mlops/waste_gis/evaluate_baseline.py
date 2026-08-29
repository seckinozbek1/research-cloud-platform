from pathlib import Path

import pandas as pd
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

TEST_DAYS = 30


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

    y_true = test["waste_kg"]
    y_pred = test["previous_waste_kg"]

    mae = mean_absolute_error(y_true, y_pred)
    rmse = mean_squared_error(y_true, y_pred) ** 0.5
    r2 = r2_score(y_true, y_pred)

    print("Baseline evaluation completed.")
    print(f"Cutoff date       : {cutoff.date()}")
    print(f"Train rows        : {len(train):,}")
    print(f"Test rows         : {len(test):,}")
    print(
        f"Train dates       : "
        f"{train['collection_date'].min().date()} → "
        f"{train['collection_date'].max().date()}"
    )
    print(
        f"Test dates        : "
        f"{test['collection_date'].min().date()} → "
        f"{test['collection_date'].max().date()}"
    )
    print()
    print("Baseline: previous_waste_kg")
    print(f"MAE               : {mae:,.2f} kg")
    print(f"RMSE              : {rmse:,.2f} kg")
    print(f"R²                : {r2:.4f}")


if __name__ == "__main__":
    main()
