from pathlib import Path
import csv
import time

from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
import pandas as pd

INPUT_PATH = Path(
    "data/education_attendance/curated_national/"
    "national_attendance_imputed.csv"
)

start = time.perf_counter()

rows = []

with INPUT_PATH.open("r", newline="", encoding="utf-8") as f:
    reader = csv.DictReader(f)

    for row in reader:
        if row["rural"] == "":
            continue

        rows.append(
            {
                "district_id": row["district_id"],
                "academic_year": row["academic_year"],
                "deprivation_score": float(row["deprivation_score"]),
                "absent": int(row["absent"]),
                "rural": int(row["rural"]),
            }
        )

df = pd.DataFrame(rows)

print(f"Complete rural rows: {len(df):,}")

X = df[
    [
        "district_id",
        "academic_year",
        "deprivation_score",
        "absent",
    ]
]

y = df["rural"]

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.20,
    random_state=42,
    stratify=y,
)

categorical = [
    "district_id",
    "academic_year",
]

numeric = [
    "deprivation_score",
    "absent",
]

preprocessor = ColumnTransformer(
    transformers=[
        (
            "categorical",
            OneHotEncoder(
                handle_unknown="ignore"
            ),
            categorical,
        ),
        (
            "numeric",
            "passthrough",
            numeric,
        ),
    ]
)

model = Pipeline(
    steps=[
        ("preprocessor", preprocessor),
        (
            "classifier",
            LogisticRegression(
                max_iter=500,
                n_jobs=-1,
            ),
        ),
    ]
)

model.fit(X_train, y_train)

pred = model.predict(X_test)
prob = model.predict_proba(X_test)[:, 1]

majority_class = y_train.mode()[0]

baseline_pred = [
    majority_class
    for _ in range(len(y_test))
]

print()
print("BASELINE")
print("--------")
print(
    f"Accuracy:          "
    f"{accuracy_score(y_test, baseline_pred):.4f}"
)

print()
print("LOGISTIC MODEL")
print("--------------")
print(
    f"Accuracy:          "
    f"{accuracy_score(y_test, pred):.4f}"
)
print(
    f"Balanced accuracy: "
    f"{balanced_accuracy_score(y_test, pred):.4f}"
)
print(
    f"ROC AUC:           "
    f"{roc_auc_score(y_test, prob):.4f}"
)

elapsed = time.perf_counter() - start

print()
print(f"Elapsed: {elapsed:.3f} seconds")
