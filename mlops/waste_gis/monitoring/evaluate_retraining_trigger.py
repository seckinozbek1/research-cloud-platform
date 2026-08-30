from pathlib import Path
import json


PROJECT_ROOT = Path(__file__).resolve().parents[3]

DRIFT_REPORT_PATH = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "waste_gis"
    / "monitoring"
    / "data_drift_report.json"
)

PERFORMANCE_REPORT_PATH = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "waste_gis"
    / "monitoring"
    / "model_performance_report.json"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "waste_gis"
    / "monitoring"
    / "retraining_trigger.json"
)

MIN_DRIFTED_FEATURES = 2


def main():
    drift = json.loads(
        DRIFT_REPORT_PATH.read_text()
    )

    performance = json.loads(
        PERFORMANCE_REPORT_PATH.read_text()
    )

    drifted_count = int(
        drift["drifted_feature_count"]
    )

    drift_triggered = (
        drifted_count >= MIN_DRIFTED_FEATURES
    )

    performance_triggered = bool(
        performance["performance_degraded"]
    )

    retrain_required = (
        drift_triggered
        or performance_triggered
    )

    reasons = []

    if drift_triggered:
        reasons.append(
            f"{drifted_count} features drifted"
        )

    if performance_triggered:
        reasons.append(
            "model performance degraded"
        )

    if not reasons:
        reasons.append(
            "no retraining condition met"
        )

    result = {
        "retrain_required": retrain_required,
        "data_drift_triggered": drift_triggered,
        "performance_triggered": performance_triggered,
        "drifted_feature_count": drifted_count,
        "drifted_features": drift["drifted_features"],
        "mae": performance["mae"],
        "reference_mae": performance["reference_mae"],
        "mae_ratio": performance["mae_ratio"],
        "performance_degraded": performance[
            "performance_degraded"
        ],
        "reason": "; ".join(reasons),
    }

    OUTPUT_PATH.write_text(
        json.dumps(
            result,
            indent=2,
        )
    )

    print("Combined retraining policy evaluated.")
    print(
        "Data drift trigger   :",
        drift_triggered,
    )
    print(
        "Performance trigger  :",
        performance_triggered,
    )
    print(
        "Retrain required     :",
        retrain_required,
    )
    print(
        "Reason               :",
        result["reason"],
    )
    print(
        "Output               :",
        OUTPUT_PATH,
    )


if __name__ == "__main__":
    main()
