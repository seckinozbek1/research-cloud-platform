# Research Cloud Platform — Course State

## Current application position

Milestone 3 application work is in progress.

### APIs + serverless

Current API implementation:

- FastAPI + Uvicorn installed in `.venv`
- dependencies recorded in `requirements.lock.txt`
- API implementation: `src/api.py`
- API bound to localhost during development
- health endpoint implemented
- district attendance endpoint implemented
- optional academic-year filtering implemented
- 404 behaviour verified

### Data serving architecture

Authoritative large processed dataset:

`data/education_attendance/curated_national/national_attendance_curated.csv`

Approximate size:

- 1,694,823 data rows
- ~288 MB

Spark-derived analytical serving dataset:

`data/education_attendance/analytics/district_year_attendance_metrics.csv`

Shape:

- 1,000 district-year rows
- 8 analytical fields

The stable analytics CSV and Spark output were verified to contain the same
district-year keys, counts, and analytical results. The only observed
difference was floating-point summation precision in `mean_deprivation`
(~5e-16 maximum difference).

Current API flow:

curated national attendance data
→ Spark aggregation
→ district-year analytical metrics
→ FastAPI
→ HTTP/JSON client

Large generated education datasets remain intentionally git-ignored.

### Serverless storage-event simulation

Implemented:

- `src/serverless_register_dataset.py`
- simulated object-storage event payload with:
  - bucket
  - object name
  - event type
- `object_created` events register raw datasets in `metadata/metadata.sqlite`
- irrelevant event types are ignored
- missing objects return an explicit error
- repeated delivery is idempotent through the unique dataset path

Conceptual cloud mapping:

- S3 event → AWS Lambda
- Cloud Storage event → Google Cloud Function
- Blob event → Azure Function

## Milestone 3 application progress

APIs + serverless application block completed: 5/5 A.

Verified end-to-end:

- large curated education workload feeds analytical aggregates
- FastAPI serves district/year analytics
- deterministic pagination
- machine-facing client output
- educator-facing human-readable client output
- localhost-only development exposure
- simulated object-storage event trigger
- metadata registration
- duplicate-event idempotency
- missing-object handling
- irrelevant-event filtering

Next application topic:

Kubernetes — 0/7 A
