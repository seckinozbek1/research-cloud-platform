from pathlib import Path
from datetime import datetime, timezone
import json


ROOT = Path(__file__).resolve().parents[1]

OUT_JSON = (
    ROOT
    / "enterprise"
    / "architecture_snapshot.json"
)

OUT_MD = (
    ROOT
    / "enterprise"
    / "ARCHITECTURE.md"
)


COMPONENT_RULES = {
    "data": [
        "data",
    ],

    "pipelines_ml": [
        "mlops",
    ],

    "hpc_distributed_compute": [
        "hpc",
    ],

    "governance_privacy": [
        "governance",
    ],

    "finops": [
        "finops",
    ],

    "hybrid_placement": [
        "hybrid",
    ],

    "infrastructure_as_code": [
        "terraform",
    ],

    "containers": [
        "docker",
    ],

    "tests": [
        "tests",
    ],

    "documentation": [
        "docs",
    ],
}


def discover_special_evidence():
    """
    Discover capabilities that may exist without a
    conventionally named top-level directory.

    We report only evidence that actually exists.
    """

    ignore_parts = {
        ".git",
        ".venv",
        "__pycache__",
        "node_modules",
    }

    container_patterns = [
        "Dockerfile",
        "Dockerfile.*",
        "docker-compose.yml",
        "docker-compose.yaml",
        "docker-compose.*.yml",
        "docker-compose.*.yaml",
        "compose.yml",
        "compose.yaml",
        "compose.*.yml",
        "compose.*.yaml",
    ]

    test_patterns = [
        "test_*.py",
        "*_test.py",
        "conftest.py",
        "pytest.ini",
    ]

    def discover(patterns):
        found = set()

        for pattern in patterns:
            for path in ROOT.rglob(pattern):

                if any(
                    part in ignore_parts
                    for part in path.parts
                ):
                    continue

                if path.is_file():
                    found.add(
                        str(
                            path.relative_to(ROOT)
                        )
                    )

        return sorted(found)

    containers = discover(
        container_patterns
    )

    tests = discover(
        test_patterns
    )

    # Additional project-level test configuration evidence.
    for filename in [
        "pyproject.toml",
        "setup.cfg",
        "tox.ini",
    ]:
        path = ROOT / filename

        if not path.exists():
            continue

        content = path.read_text(
            errors="ignore"
        ).lower()

        if (
            "pytest" in content
            or "unittest" in content
            or "[tool.pytest" in content
        ):
            tests.append(filename)

    return {
        "containers": sorted(
            set(containers)
        ),

        "tests": sorted(
            set(tests)
        ),
    }


def discover_components():
    result = {}

    special = (
        discover_special_evidence()
    )

    for capability, paths in (
        COMPONENT_RULES.items()
    ):
        found = []

        for relative in paths:
            path = ROOT / relative

            if path.exists():
                found.append(relative)

        # Containers may live under HPC/SLURM or another
        # subdirectory instead of ROOT/docker/.
        if capability == "containers":
            found.extend(
                special["containers"]
            )

        # Tests may be colocated with application modules
        # instead of ROOT/tests/.
        if capability == "tests":
            found.extend(
                special["tests"]
            )

        found = sorted(
            set(found)
        )

        result[capability] = {
            "implemented": bool(found),
            "paths": found,
        }

    return result


def discover_governance_state():
    governed = (
        ROOT
        / "governance"
        / "data_catalog_governed.csv"
    )

    lineage = (
        ROOT
        / "governance"
        / "lineage_events.jsonl"
    )

    return {
        "governed_catalog_exists":
            governed.exists(),

        "lineage_exists":
            lineage.exists(),

        "waste_gis_gate_exists":
            (
                ROOT
                / "governance"
                / "waste_gis_gate.py"
            ).exists(),
    }


def discover_hybrid_state():
    return {
        "workload_profiler":
            (
                ROOT
                / "hybrid"
                / "profile_workload.py"
            ).exists(),

        "adaptive_placement":
            (
                ROOT
                / "hybrid"
                / "adaptive_placement.py"
            ).exists(),

        "policy_resolver":
            (
                ROOT
                / "hybrid"
                / "resolve_and_place.py"
            ).exists(),

        "local_server_cloud_comparator":
            (
                ROOT
                / "hybrid"
                / "compare_local_server_cloud.py"
            ).exists(),
    }


def architecture_markdown(snapshot):
    components = snapshot["components"]

    implemented = [
        name
        for name, state
        in components.items()
        if state["implemented"]
    ]

    missing = [
        name
        for name, state
        in components.items()
        if not state["implemented"]
    ]

    implemented_text = "\n".join(
        f"- {x}"
        for x in implemented
    )

    missing_text = (
        "\n".join(
            f"- {x}"
            for x in missing
        )
        if missing
        else "- none"
    )

    governance_json = json.dumps(
        snapshot["governance"],
        indent=2,
    )

    hybrid_json = json.dumps(
        snapshot["hybrid"],
        indent=2,
    )

    return f"""# Research Cloud Platform — Enterprise Architecture

Generated: {snapshot["generated_utc"]}

## Architectural objective

One governed research/enterprise platform that can execute workloads
locally, on dedicated infrastructure, or in public cloud according to
resource requirements, policy, governance, and economics.

## Data plane

raw data
    |
    v
ingestion / preprocessing
    |
    v
storage / curated datasets
    |
    v
analytics / ML
    |
    v
model and analytical artifacts

## Compute plane

LOCAL PC
    |
    +-- sufficient capacity
    |       |
    |       +--> execute locally
    |
    +-- insufficient capacity
            |
            +-- temporary excess
            |       |
            |       +--> CLOUD BURST
            |
            +-- sustained load
                    |
                    +--> LOCAL LINUX SERVER
                         versus
                         FULL / COMMITTED CLOUD

A cloud-specific requirement bypasses the local-capacity decision and
routes directly into cloud placement evaluation.

## Control plane

IAM / security
governance / privacy
metadata / lineage
CI/CD
infrastructure as code
observability / reliability
MLOps
FinOps

## Adaptive workload placement

Operational facts are discovered rather than embedded in policy:

workload
    |
    v
telemetry
    |
    v
lineage dependencies
    |
    v
governance controls
    |
    v
local capacity inspection
    |
    v
placement workflow
    |
    v
live provider pricing when cloud is required

Only workflow and governance rules are policy.

Prices, instance types, workload resource requirements, runtime,
storage footprint and provider selection are runtime facts.

## Hybrid data movement

Only lineage-resolved minimum inputs should move to cloud.

local canonical data
    |
    v
governance gate
    |
    v
minimum required transfer
    |
    v
temporary cloud compute
    |
    v
artifact / metrics / logs
    |
    v
local platform
    |
    v
cloud cleanup

## Enterprise operating principles

1. Least privilege and short-lived identities.
2. Governance before sensitive data movement.
3. Explicit lineage and provenance.
4. Observability before autonomous remediation.
5. Local-first when appropriate, not local-only.
6. Cloud resources are ephemeral unless persistence is justified.
7. Unknown price or usage information remains UNKNOWN.
8. Actual billing measurements override estimates.
9. Provider-specific services require a benefit that justifies lock-in.
10. Build versus buy is decided per capability, not ideologically.

## Implemented capability groups

{implemented_text}

## Not discovered in current repository

{missing_text}

## Governance state

{governance_json}

## Hybrid placement state

{hybrid_json}

## Vendor mapping

| Concept | AWS | GCP | Azure |
|---|---|---|---|
| Compute | EC2 | Compute Engine | Virtual Machines |
| Object storage | S3 | Cloud Storage | Blob Storage |
| Managed Kubernetes | EKS | GKE | AKS |
| Serverless | Lambda | Cloud Run / Functions | Functions / Container Apps |
| IAM | IAM | Cloud IAM | Entra ID + Azure RBAC |
| Monitoring | CloudWatch | Cloud Monitoring | Azure Monitor |
| Private network | VPC | VPC | VNet |
| Hybrid VPN | Site-to-Site VPN | Cloud VPN | VPN Gateway |
| IaC | Terraform / CloudFormation | Terraform | Terraform / Bicep |
| Managed ML | SageMaker | Vertex AI | Azure Machine Learning |

## Research use

Reproducible pipelines, HPC/GPU bursting, controlled research data,
provenance, experiment tracking and cost-aware infrastructure.

## Corporate use

The same architecture extends to multiple source systems, teams,
environments and applications by adding stronger identity boundaries,
data contracts, service ownership, SLAs/SLOs, disaster recovery,
streaming and managed enterprise services.
"""


def main():
    snapshot = {
        "generated_utc":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "components":
            discover_components(),

        "governance":
            discover_governance_state(),

        "hybrid":
            discover_hybrid_state(),
    }

    OUT_JSON.write_text(
        json.dumps(
            snapshot,
            indent=2,
        )
    )

    OUT_MD.write_text(
        architecture_markdown(
            snapshot
        )
    )

    print(
        "=== ENTERPRISE ARCHITECTURE SNAPSHOT ==="
    )

    for name, state in (
        snapshot["components"].items()
    ):
        status = (
            "IMPLEMENTED"
            if state["implemented"]
            else "NOT DISCOVERED"
        )

        print(
            f"{status:15} {name}"
        )

    print()

    print(
        "Architecture:",
        OUT_MD,
    )

    print(
        "Machine-readable snapshot:",
        OUT_JSON,
    )


if __name__ == "__main__":
    main()
