# Research Cloud Platform — Enterprise Architecture

Generated: 2026-09-02T10:12:28.695366+00:00

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

- data
- pipelines_ml
- hpc_distributed_compute
- governance_privacy
- finops
- hybrid_placement
- infrastructure_as_code
- containers
- tests
- documentation

## Not discovered in current repository

- none

## Governance state

{
  "governed_catalog_exists": true,
  "lineage_exists": true,
  "waste_gis_gate_exists": true
}

## Hybrid placement state

{
  "workload_profiler": true,
  "adaptive_placement": true,
  "policy_resolver": true,
  "local_server_cloud_comparator": true
}

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
