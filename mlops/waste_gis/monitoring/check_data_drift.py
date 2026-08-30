from pathlib import Path
import json

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[3]

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
    / "monitoring"
    / "data_drift_report.json"
)

DRIFT_THRESHOLD = 1.0


def main():
    spec = json.loads(
        FEATURE_SPEC_PATH.read_text()
    )

    timestamp_col = spec["timestamp"]

    features = [
        feature["name"]
        for feature in spec["features"]
    ]

    df = pd.read_parquet(
        FEATURE_TABLE_PATH
    ).sort_values(timestamp_col)

    dates = sorted(
        df[timestamp_col].drop_duplicates()
    )

    midpoint = len(dates) // 2

    reference_dates = dates[:midpoint]
    current_dates = dates[midpoint:]

    reference = df[
        df[timestamp_col].isin(reference_dates)
    ]

    current = df[
        df[timestamp_col].isin(current_dates)
    ]

    report = {
        "threshold": DRIFT_THRESHOLD,
        "reference_start": str(
            min(reference_dates).date()
        ),
        "reference_end": str(
            max(reference_dates).date()
        ),
        "current_start": str(
            min(current_dates).date()
        ),
        "current_end": str(
            max(current_dates).date()
        ),
        "features": {},
    }

    drifted_features = []

    for feature in features:
        ref_mean = float(
            reference[feature].mean()
        )

        ref_std = float(
            reference[feature].std()
        )

        current_mean = float(
            current[feature].mean()
        )

        if ref_std == 0:
            drift_score = 0.0
        else:
            drift_score = abs(
                current_mean - ref_mean
            ) / ref_std

        is_drifted = (
            drift_score >= DRIFT_THRESHOLD
        )

        if is_drifted:
            drifted_features.append(feature)

        report["features"][feature] = {
            "reference_mean": ref_mean,
            "reference_std": ref_std,
            "current_mean": current_mean,
            "drift_score": drift_score,
            "drifted": is_drifted,
        }

    report["drifted_feature_count"] = len(
        drifted_features
    )

    report["drifted_features"] = (
        drifted_features
    )

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

    print("Data drift check completed.")
    print(
        "Reference : "
        f"{report['reference_start']} "
        "→ "
        f"{report['reference_end']}"
    )
    print(
        "Current   : "
        f"{report['current_start']} "
        "→ "
        f"{report['current_end']}"
    )
    print(
        "Threshold : "
        f"{DRIFT_THRESHOLD:.2f}"
    )
    print()

    for feature, values in report[
        "features"
    ].items():
        print(
            f"{feature:30} "
            f"score={values['drift_score']:.3f} "
            f"drifted={values['drifted']}"
        )

    print()
    print(
        "Drifted features:",
        len(drifted_features),
    )

    print(
        "Report:",
        OUTPUT_PATH,
    )


if __name__ == "__main__":
    main()
