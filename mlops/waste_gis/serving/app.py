from pathlib import Path
import json

import mlflow
import pandas as pd
from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[3]

FEATURE_SPEC_PATH = (
    PROJECT_ROOT
    / "mlops"
    / "waste_gis"
    / "feature_store"
    / "feature_spec.json"
)

MLFLOW_DB_PATH = PROJECT_ROOT / "mlflow.db"

MODEL_URI = "models:/waste-demand-forecast@candidate"

spec = json.loads(
    FEATURE_SPEC_PATH.read_text()
)

FEATURES = [
    feature["name"]
    for feature in spec["features"]
]


class PredictionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    population_2025: float
    population_density_2025: float
    road_density_km_per_km2: float
    container_capacity_kg: float
    days_since_last_pickup: int
    weekend: int
    temperature_c: float
    rain_mm: float


app = FastAPI(
    title="Waste Demand Forecast API",
    version="1.0.0",
)

mlflow.set_tracking_uri(
    f"sqlite:///{MLFLOW_DB_PATH}"
)

model = mlflow.pyfunc.load_model(
    MODEL_URI
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "model_uri": MODEL_URI,
    }


@app.post("/predict")
def predict(request: PredictionRequest):
    row = pd.DataFrame(
        [[
            getattr(request, feature)
            for feature in FEATURES
        ]],
        columns=FEATURES,
    )

    prediction = model.predict(row)

    return {
        "predicted_waste_kg": float(
            prediction[0]
        ),
        "model_uri": MODEL_URI,
    }
