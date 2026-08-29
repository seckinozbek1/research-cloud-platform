from pathlib import Path
import json
import socket
import time

import pandas as pd
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_PATH = (
    BASE_DIR
    / "serving"
    / "education_attendance"
    / "district_year_attendance_metrics.csv"
)

class PrettyJSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
        ).encode("utf-8")


app = FastAPI(
    title="Education Attendance Analytics API",
    default_response_class=PrettyJSONResponse,
)


REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "path", "status"],
)

REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "path"],
)


@app.middleware("http")
async def collect_http_metrics(request: Request, call_next):
    start = time.perf_counter()

    response = await call_next(request)

    duration = time.perf_counter() - start

    route = request.scope.get("route")
    path = getattr(route, "path", request.url.path)

    REQUEST_COUNT.labels(
        method=request.method,
        path=path,
        status=response.status_code,
    ).inc()

    REQUEST_DURATION.labels(
        method=request.method,
        path=path,
    ).observe(duration)

    return response


@app.get("/metrics")
def prometheus_metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )

# Load the small analytical serving layer once when the service starts.
metrics = pd.read_csv(DATA_PATH)


def format_record(row: dict) -> dict:
    district_id = int(row["district_id"])
    academic_year = int(row["academic_year"])
    student_days = int(row["student_days"])
    absent_days = int(row["absent_days"])

    absence_rate = float(row["absence_rate"])
    mean_deprivation = float(row["mean_deprivation"])
    rural_share = float(row["rural_share_among_observed"])
    rural_unknown = float(row["rural_unknown_rate"])

    return {
        "district_id": {
            "raw": district_id,
            "human": f"District {district_id}",
        },
        "academic_year": {
            "raw": academic_year,
            "human": str(academic_year),
        },
        "student_days": {
            "raw": student_days,
            "human": f"{student_days:,}",
        },
        "absent_days": {
            "raw": absent_days,
            "human": f"{absent_days:,}",
        },
        "absence_rate": {
            "raw": absence_rate,
            "human": f"{absence_rate:.2%}",
        },
        "mean_deprivation": {
            "raw": mean_deprivation,
            "human": f"{mean_deprivation:.3f}",
        },
        "rural_share_among_observed": {
            "raw": rural_share,
            "human": f"{rural_share:.2%}",
        },
        "rural_unknown_rate": {
            "raw": rural_unknown,
            "human": f"{rural_unknown:.2%}",
        },
    }


def format_records(dataframe: pd.DataFrame) -> list[dict]:
    return [
        format_record(row)
        for row in dataframe.to_dict(orient="records")
    ]


@app.get("/whoami")
def whoami():
    return {
        "pod": socket.gethostname(),
    }


@app.get("/health")
def health():
    return {
        "status": "ok",
        "district_year_rows": len(metrics),
    }


@app.get("/districts/{district_id}/attendance")
def district_attendance(
    district_id: int,
    year: int | None = None,
):
    result = metrics[metrics["district_id"] == district_id]

    if year is not None:
        result = result[result["academic_year"] == year]

    result = result.sort_values(["district_id", "academic_year"])

    if result.empty:
        raise HTTPException(
            status_code=404,
            detail="No attendance metrics found",
        )

    return format_records(result)


@app.get("/districts")
def list_districts(
    year: int | None = None,
    limit: int = 20,
    offset: int = 0,
):
    result = metrics

    if year is not None:
        result = result[result["academic_year"] == year]

    result = result.sort_values(["district_id", "academic_year"])
    result = result.iloc[offset : offset + limit]

    return format_records(result)


from fastapi.responses import PlainTextResponse


@app.get(
    "/reports/districts/{district_id}/attendance",
    response_class=PlainTextResponse,
)
def district_attendance_report(
    district_id: int,
    year: int,
):
    result = metrics[
        (metrics["district_id"] == district_id)
        & (metrics["academic_year"] == year)
    ]

    if result.empty:
        raise HTTPException(
            status_code=404,
            detail="No attendance metrics found",
        )

    row = result.iloc[0]

    return f"""DISTRICT {district_id} — ATTENDANCE SUMMARY, {year}

The district recorded {int(row["student_days"]):,} student-days during {year}.

Students were absent for {int(row["absent_days"]):,} days.
Overall absence rate: {float(row["absence_rate"]):.2%}.

Average deprivation score: {float(row["mean_deprivation"]):.3f}.

Among students whose rural status was known,
{float(row["rural_share_among_observed"]):.2%} were classified as rural.

Rural status was unavailable for
{float(row["rural_unknown_rate"]):.2%} of records.
"""
