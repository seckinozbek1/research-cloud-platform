from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = (
    BASE_DIR
    / "data"
    / "education_attendance"
    / "analytics"
    / "district_year_attendance_metrics.csv"
)

app = FastAPI(title="Education Attendance Analytics API")

# Small analytical serving layer: 1,000 rows, loaded once at startup.
metrics = pd.read_csv(DATA_PATH)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "district_year_rows": len(metrics),
    }


@app.get("/districts/{district_id}/attendance")
def district_attendance(district_id: int, year: int | None = None):
    result = metrics[metrics["district_id"] == district_id]

    if year is not None:
        result = result[result["academic_year"] == year]

    if result.empty:
        raise HTTPException(
            status_code=404,
            detail="No attendance metrics found",
        )

    return result.to_dict(orient="records")
