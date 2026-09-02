# FinOps

FinOps in `research-cloud-platform` is implemented as part of the
adaptive workload-placement architecture rather than as a static price
catalog.

## Canonical implementation

The active implementation is primarily in:

- `hybrid/adaptive_placement.py`
- `hybrid/compare_local_server_cloud.py`
- `hybrid/profile_workload.py`
- `hybrid/resolve_and_place.py`

## Principle

The system hard-codes decision workflow and governance policy only.

Operational facts are discovered or supplied at runtime:

- workload CPU/RAM/GPU requirements
- runtime
- storage footprint
- provider
- region
- machine/SKU candidates
- cloud pricing
- billing observations
- local-server acquisition cost
- power consumption
- electricity tariff
- maintenance cost

No static provider price is treated as authoritative.

## Cost semantics

When actual usage or billing is available, the system may use the
observed point value.

When a required fact is uncertain but bounded, the system uses a range.

When the necessary information cannot be resolved, the result remains
`UNKNOWN` rather than using an invented fallback.

## Placement relationship

FinOps feeds the placement decision:

LOCAL PC
→ CLOUD BURST for temporary excess
→ LOCAL LINUX SERVER vs COMMITTED/FULL CLOUD for sustained excess

A workload that is explicitly required to run in cloud bypasses the
local-capacity branch and enters cloud placement evaluation directly.

## Live cloud pricing

`hybrid/adaptive_placement.py` contains provider adapters for:

- Azure Retail Prices API
- AWS Price List API
- Google Cloud Billing Catalog API

Availability depends on the credentials or API access required by each
provider.

## Local server economics

`hybrid/compare_local_server_cloud.py` evaluates dedicated Linux-server
economics only when the required external facts are available. Missing
facts remain `UNKNOWN`.

## Generated outputs

Cost reports, price observations, workload profiles, and placement
decisions are runtime artifacts and are intentionally excluded from
version control.
