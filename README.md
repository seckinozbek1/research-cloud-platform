# Research Cloud Platform

A cumulative research-computing, data-platform and infrastructure project built
to develop systems-level competence across cloud computing, distributed systems,
data engineering, research computing, MLOps, governance and enterprise
architecture.

The primary development environment is:

    Windows 11
        ↓
    WSL2
        ↓
    Ubuntu
        ↓
    Linux shell
        ↓
    ~/research-cloud-platform

The canonical checkout on the primary development workstation is:

Windows:

    C:\Users\<windows-user>\local\<project-folder>

WSL view:

    <project-root>

This project previously used the WSL-native Linux filesystem. It was moved to a
single Windows-local location to make the repository easier to locate and manage
consistently across Windows and WSL.

The trade-off is explicit: WSL-native storage can provide better Linux I/O
performance for some file-intensive workloads. Performance-sensitive temporary
data or runtime state may therefore still be placed on Linux-native storage when
there is a measured reason to do so.


### Canonical source vs Linux-native runtime

The canonical Git checkout and source tree live at:

Windows:

    C:\Users\<windows-user>\local\<project-folder>

WSL:

    <project-root>

Performance-sensitive execution state is kept separately in the WSL-native
Linux filesystem:

    <runtime-root>

This directory is not a second Git checkout.

The distinction is deliberate:

    source / Git / configuration
        → Windows-local canonical repository

    Python virtual environment
    caches
    temporary files
    Spark local / shuffle state
    Ray temporary state
    MLflow runtime state
    large intermediate outputs
    HPC / distributed-computing scratch
        → WSL-native runtime storage

Source locality, compute locality and data/runtime locality are therefore
treated as separate architectural decisions.

Enter the configured local runtime with:

    cd <project-root>
    bash scripts/enter_runtime.sh

The project began as a local data and API platform and progressively expanded
into a broader research-computing and enterprise architecture.

The final system is easier to understand as several interacting planes rather
than as one linear technology stack.

Data plane:

    raw / operational data
        ↓
    ingestion and preprocessing
        ↓
    curated / analytical / serving data
        ↓
    models and analytical artefacts

Compute plane:

    local CPU / GPU
    Docker containers
    Kubernetes
    Spark
    SLURM / MPI
    distributed machine learning
    optional cloud execution targets

Control plane:

    IAM / security
    Terraform / Infrastructure as Code
    CI/CD
    observability
    reliability
    MLOps
    governance / privacy
    metadata / lineage
    FinOps

Placement plane:

    workload telemetry
        +
    policy
        +
    local capacity
        +
    governance
        +
    economics
        ↓
    execution decision

The placement layer can evaluate workloads for:

    LOCAL_PC
    CLOUD_BURST
    LOCAL_LINUX_SERVER
    FULL / COMMITTED CLOUD

The architecture is concept-first and provider-neutral. AWS, Google Cloud and
Azure are treated as alternative implementations of infrastructure concepts,
rather than as three unrelated product catalogues.

The project is intentionally cumulative. New concepts are integrated into the
same platform instead of being implemented as disconnected toy exercises.

Two workloads show that evolution particularly clearly.

The earlier education-attendance pipeline remains the main API and
data-platform example.

The later Karşıyaka waste-GIS system became the primary cumulative workload for
MLOps, research computing, HPC, GPU and distributed-ML experiments, governance,
FinOps and hybrid-placement work.

The consolidated enterprise reference architecture is documented in:

    enterprise/ARCHITECTURE.md


## 1. Prerequisites

A fresh machine should have the following available before attempting to run the complete platform.

### Host environment

- Windows 11
- WSL2
- Ubuntu
- Git
- Python 3
- Docker
- Java 17
- kubectl
- kind
- Terraform
- tmux
- SSH access to GitHub

Useful verification commands:

    wsl --status

Inside Ubuntu:

    python3 --version
    git --version
    docker --version
    java -version
    kubectl version --client
    kind version
    terraform version
    tmux -V
    ssh -T git@github.com

GitHub authentication should succeed with a message similar to:

    Hi <username>! You've successfully authenticated

Do not place GitHub private keys or other credentials in this repository.


## 2. Clone the repository

On the primary development workstation, clone into the canonical local
directory:

    mkdir -p /mnt/c/Users/<windows-user>/local

    git clone \
      git@github.com:seckinozbek1/research-cloud-platform.git \
      <project-root>

    cd <project-root>

On Windows, the same directory is:

    C:\Users\<windows-user>\local\<project-folder>

Use the repository's default branch for the stable version of the platform.

Feature work may be developed on topic branches and merged after validation.
The README therefore does not hard-code a temporary development branch name.


## 3. Python environment

Create and activate the project virtual environment:

    python3 -m venv .venv
    source .venv/bin/activate

Install the project dependencies:

    pip install -r requirements.lock.txt

The API has a deliberately smaller dependency set:

    requirements.api.txt

This keeps the production/container API image separate from the much larger research-computing environment.


## 4. Project data layout

The project follows a research/data-platform progression rather than treating every dataset as application state.

Important layers include:

    data/
        raw or working research data

    analytical/
        analytical outputs

    serving/
        small curated datasets intended for services/APIs

    metadata/
        runtime metadata and local operational state

The current API serving dataset is:

    serving/education_attendance/district_year_attendance_metrics.csv

The current education-attendance workload ultimately produces approximately 1,000 district-year aggregate rows for the API serving layer.

Large local datasets, runtime metadata and other machine-specific artefacts should not be committed to Git unless intentionally curated for version control.


## 5. Spark and distributed data processing

The project uses PySpark for distributed-style data processing.

The local environment uses:

- OpenJDK 17
- PySpark
- Apache Spark execution through Python

Verify Java:

    java -version

Verify PySpark from the active virtual environment:

    python -c "import pyspark; print(pyspark.__version__)"

Spark is used to transform larger research data into smaller curated outputs suitable for downstream analytics and serving.


## 6. FastAPI service

The API implementation is:

    src/api.py

The service reads the curated serving layer rather than scanning the full research dataset for every request.

Important endpoints include:

    /health

    /whoami

    /districts

    /districts/{district_id}/attendance

    /reports/districts/{district_id}/attendance

    /metrics

Run the API manually for development:

    source .venv/bin/activate

    uvicorn src.api:app \
      --host 127.0.0.1 \
      --port 8001

Test:

    curl http://127.0.0.1:8001/health

Expected structure:

    {
      "status": "ok",
      "district_year_rows": 1000
    }

The `/health` endpoint answers whether the application is functioning.

The `/metrics` endpoint exposes operational measurements for Prometheus.


## 7. Docker

The API is packaged as a Docker image.

Build locally:

    docker build -t research-cloud-api:local .

The repository contains a `.dockerignore` file.

This is important.

Large or sensitive local directories such as the following must not enter the Docker build context:

    data/
    analytical/
    metadata/
    logs/
    .venv/
    terraform/
    .git/
    .github/

Before tightening `.dockerignore`, the Docker build context was approximately 926 MB.

After excluding local research/runtime material, the context fell to approximately:

    462 kB

This improves build speed and reduces the risk of accidentally including local data, credentials or infrastructure state in a container image.


## 8. Kubernetes

The local Kubernetes environment uses kind.

The principal local cluster is:

    research-cloud

The API architecture includes:

    Deployment
        ↓
    multiple API Pods
        ↓
    ClusterIP Service
        ↓
    Ingress

The project Kubernetes manifests are under:

    kubernetes/

The platform has exercised:

- multiple replicas
- Service-based discovery
- readiness probes
- liveness probes
- self-healing
- request distribution across Pods
- ConfigMaps
- Secrets
- resource requests
- resource limits
- Horizontal Pod Autoscaling
- Metrics Server
- Ingress
- TLS
- scheduling behaviour

Useful inspection commands:

    kubectl get pods
    kubectl get deployments
    kubectl get services
    kubectl get ingress
    kubectl get hpa

The `/whoami` endpoint can be used to see which Pod answered a request.


## 9. Local Kubernetes ingress support

The local environment uses:

    cloud-provider-kind --enable-lb-port-mapping

This process supports the local kind ingress/load-balancer path.

It is started automatically by the local-lab orchestration described later in this README.

Do not treat the routing workarounds used for this WSL/kind environment as a production cloud-networking design. Managed Kubernetes and production CNIs are expected to provide the corresponding routing behaviour.


## 10. Security and IAM

The local Kubernetes application has been hardened beyond its original development configuration.

Implemented controls include:

- dedicated Kubernetes ServiceAccount
- RBAC Role
- RBAC RoleBinding
- least-privilege API access
- service-account token automount disabled where unnecessary
- `runAsNonRoot`
- explicit non-root UID/GID
- `allowPrivilegeEscalation: false`
- read-only root filesystem
- Linux capabilities dropped
- RuntimeDefault seccomp profile
- ClusterIP service exposure
- TLS for ingress
- secret exclusion from Git
- container vulnerability scanning
- NetworkPolicy definition

The API container was reduced to a minimal API-specific dependency set and patched until the relevant Trivy scan reported:

    0 HIGH
    0 CRITICAL

The Kubernetes secret file:

    kubernetes/api-secret.yaml

must remain local and is excluded by `.gitignore`.

Never commit:

- passwords
- private keys
- API tokens
- cloud credentials
- Kubernetes secret values
- Terraform state containing sensitive values


## 11. Terraform

Terraform is used as Infrastructure as Code.

The current introductory Terraform configuration is under:

    terraform/

Important files:

    terraform/main.tf
    terraform/variables.tf
    terraform/outputs.tf
    terraform/.terraform.lock.hcl

Initialise:

    terraform -chdir=terraform init

Validate:

    terraform -chdir=terraform fmt
    terraform -chdir=terraform validate

Preview infrastructure changes:

    terraform -chdir=terraform plan

Apply:

    terraform -chdir=terraform apply

Inspect state:

    terraform -chdir=terraform state list
    terraform -chdir=terraform show

Inspect outputs:

    terraform -chdir=terraform output

Preview destruction without actually deleting resources:

    terraform -chdir=terraform plan -destroy

The current learning resource is the Kubernetes namespace:

    research-platform

The exercise demonstrates:

- providers
- resources
- state
- variables
- outputs
- create
- update in place
- plan
- apply
- destroy planning
- reconciliation

Terraform local runtime material must not be committed:

    terraform/.terraform/
    terraform/*.tfstate
    terraform/*.tfstate.*
    hybrid/workload_profiles/
    hybrid/adaptive_placement_decision.json
    hybrid/capacity_decision.json
    hybrid/hybrid_execution_plan.json
    hybrid/local_server_vs_cloud.json
    enterprise/architecture_snapshot.json
    artifacts/distributed_ml/*runtime*_metrics.json
    MLflow runtime state

The provider lock file SHOULD be committed:

    terraform/.terraform.lock.hcl

Terraform represents the Infrastructure-as-Code layer of the platform.
Provider-specific implementations can extend the same architecture across AWS,
Google Cloud and Azure without changing the underlying systems model.

The provider-learning workflow is:

    understand the infrastructure concept
        ↓
    inspect it once through the native provider interface
        ↓
    implement it with Terraform
        ↓
    port the architecture across providers


## 12. GitHub and CI/CD

The repository uses GitHub Actions.

Workflow:

    .github/workflows/ci.yml

Current pipeline:

    git push
        ↓
    GitHub Actions
        ↓
    test
        ↓
    build-and-publish

The test stage runs in a fresh GitHub Ubuntu runner and validates the application independently of the developer machine.

The pipeline performs operations including:

- repository checkout
- Python setup
- API dependency installation
- Python source validation
- Docker Buildx setup
- container build

A successful test allows the publishing job to run.

The resulting API container is published to GitHub Container Registry:

    GHCR

Conceptually:

    source repository
        ↓
    CI tests
        ↓
    container build
        ↓
    container registry
        ↓
    deployment target

Deployment targets are intentionally decoupled from the CI pipeline. The same
build artefact can be used with local, Kubernetes, HPC or cloud execution paths
when workload and policy requirements justify them. The repository does not
claim a permanent production deployment on every cloud provider.

The same pipeline concepts transfer directly to systems such as:

- Jenkins
- GitLab CI
- Azure DevOps

For example:

    GitHub Actions workflow  ≈ Jenkins pipeline
    GitHub runner            ≈ Jenkins agent
    workflow YAML            ≈ Jenkinsfile
    job/stage dependency     ≈ pipeline gate


## 13. Local secrets

Local credentials are stored separately from version-controlled configuration.

Template:

    environment/local_secrets.env.example

Real local file:

    environment/local_secrets.env

The real file is excluded from Git.

Create it before starting a fresh local lab.

Example structure:

    GF_SECURITY_ADMIN_USER=admin
    GF_SECURITY_ADMIN_PASSWORD=CHANGE_ME

Do NOT commit the real password.

For Grafana, choose a non-default admin password.

To enter it without placing the password directly in shell history:

    read -s -p "Grafana admin password: " GRAFANA_PASSWORD
    echo

    printf 'GF_SECURITY_ADMIN_USER=admin\nGF_SECURITY_ADMIN_PASSWORD=%s\n' \
      "$GRAFANA_PASSWORD" > environment/local_secrets.env

    chmod 600 environment/local_secrets.env
    unset GRAFANA_PASSWORD

Verify that Git ignores it:

    git check-ignore -v environment/local_secrets.env

Do not use:

    cat environment/local_secrets.env

during demonstrations or support conversations because that would print the secret to the terminal.


## 14. Observability

The current observability stack is:

    FastAPI
       │
       │ /metrics
       ▼
    Prometheus
       │
       ▼
    Grafana

### Application metrics

The API exports Prometheus-compatible metrics including:

    http_requests_total

and:

    http_request_duration_seconds

The request counter records dimensions such as:

- HTTP method
- route template
- status code

Route templates are used instead of raw IDs where possible.

For example:

    /districts/{district_id}/attendance

rather than creating a separate time series for every district ID.

This reduces metric-cardinality growth.


## 15. Prometheus

Configuration:

    monitoring/prometheus.yml

Prometheus currently scrapes the local API approximately every five seconds.

The local configuration targets:

    127.0.0.1:8001

Prometheus runs using host networking in the current WSL local-lab arrangement so that it can reach the host-bound FastAPI service.

Prometheus health:

    curl http://127.0.0.1:9090/-/healthy

Check scrape targets:

    curl -s http://127.0.0.1:9090/api/v1/targets

A healthy API target should show:

    health: up
    lastError: ""

Prometheus stores the scraped observations as time-series data.


## 16. Grafana

Grafana visualises metrics stored in Prometheus.

Provisioning configuration is under:

    monitoring/grafana/provisioning/

Dashboard definitions are under:

    monitoring/grafana/dashboards/

The Prometheus datasource is provisioned automatically.

The principal dashboard is:

    Research Cloud API

Dashboard UID:

    research-cloud-api

Current panels include:

- Request Rate
- Error Rate
- Average Request Latency

The dashboard is configured for automatic refresh approximately every:

    5 seconds

This means traffic should become visible without manually refreshing the browser.

Grafana is locally exposed at:

    http://127.0.0.1:3000

The startup script opens the provisioned dashboard directly rather than opening the empty Grafana home page.

The local environment permits anonymous Viewer access so ordinary dashboard viewing does not require repeatedly entering the admin password.

Administrative credentials remain separate in:

    environment/local_secrets.env


## 17. Local SLO alerting

Prometheus evaluates local reliability rules defined in:

    monitoring/alerts.yml

Current production-like local objectives include:

    5xx error ratio < 0.1%
    p95 request latency < 300 ms

The latency alert requires the threshold to remain violated for two minutes before firing. This avoids immediately alerting on very short transient spikes.

The local alert lifecycle is:

    normal
        ↓
    pending
        ↓
    firing
        ↓
    resolved

The local lab runs:

    scripts/alert_watcher.sh

in a dedicated tmux window named:

    alerts

The watcher polls the Prometheus alerts API and makes new firing alerts visible instead of requiring the user to continuously inspect Grafana.

When a new alert fires:

- the alert is printed prominently in the `alerts` window
- the tmux alert message is surfaced
- the `alerts` window is brought to the foreground
- repeated polling does not continuously duplicate the same firing notification
- resolution is printed explicitly when the condition clears

This local mechanism is for the development lab.

In a production environment, notification routing would normally be handled through systems such as Alertmanager and integrations such as email, Slack or incident-management platforms.

The alert pipeline has been tested end to end using a temporary deterministic alert and verified through:

    pending → firing → visible notification → resolved

The temporary test rule is not part of the normal configuration.

## 18. Generate monitoring traffic

To produce visible API traffic locally, use the `client` tmux window.

Successful traffic example:

    for i in {1..100}; do
      curl -s http://127.0.0.1:8001/health > /dev/null
      curl -s 'http://127.0.0.1:8001/districts?limit=5' > /dev/null
      curl -s http://127.0.0.1:8001/districts/1/attendance > /dev/null
    done

This generates approximately 300 successful requests.

Example 404 traffic:

    for i in {1..20}; do
      curl -s http://127.0.0.1:8001/districts/999999/attendance > /dev/null
    done

Note that the current Error Rate dashboard query focuses on server-side `5xx` responses.

A `404` is a client-side `4xx` response and therefore does not automatically count as a `5xx` service failure.


## 19. One-command local lab

The local environment is orchestrated through:

    scripts/start_local_lab.sh

The design goal is that the user should not have to manually remember which terminal must run which service.

Start:

    cd <project-root>
    ./scripts/start_local_lab.sh

The script performs the local operational startup, including:

- visible `sudo` preflight
- stale local-lab container cleanup
- tmux session creation
- API startup
- Prometheus startup
- Grafana startup
- client shell creation
- work shell creation
- service readiness checks
- Windows-side Grafana reachability checks
- automatic browser launch
- automatic tmux attach

Known interactive authentication must remain visible.

Passwords are never embedded into the orchestration script.


## 20. tmux terminal layout

The local lab creates one tmux session:

    research-cloud

with six core named windows:

    0  infra
    1  api
    2  prometheus
    3  grafana
    4  client
    5  work

The reliability workflow may additionally use a dedicated window named:

    alerts

for the local alert watcher. This is an operational monitoring window rather
than one of the six core service/development windows.

Roles:

    infra
        long-running local infrastructure helper

    api
        FastAPI service

    prometheus
        Prometheus server

    grafana
        Grafana server

    client
        curl and client-side test commands

    work
        normal development and administration

Useful tmux navigation:

    Ctrl+b, then 0-5
        jump directly to a window

    Ctrl+b, then n
        next window

    Ctrl+b, then p
        previous window

    Ctrl+b, then w
        show window list

    Ctrl+b, then d
        detach without stopping the session

Reattach:

    tmux attach -t research-cloud

The tmux configuration should make the active session/window visible.

The shell prompt inside tmux should also display the current window, for example:

    [research-cloud-platform | client]

or:

    [research-cloud-platform | work]

This is deliberate: operational commands should not depend on remembering an invisible terminal role.


## 21. Stop the local lab

Detach from tmux if necessary:

    Ctrl+b, then d

Stop the managed session:

    ./scripts/stop_local_lab.sh

This stops the processes associated with the tmux local-lab session.

It does NOT imply destruction of:

- the Git repository
- local research data
- the kind Kubernetes cluster
- Terraform-managed infrastructure outside the session
- cloud infrastructure

Those resources require their own explicit cleanup procedures.


## 22. Operational design principles

The local environment follows several rules.

### Reproducibility

Important setup and operation should exist as:

- code
- configuration
- scripts
- version-controlled documentation

rather than depending on remembered shell history.

### User-visible interaction

If startup requires:

- a sudo password
- an SSH passphrase
- a confirmation
- another known interactive choice

the interaction should be visible rather than hidden in a background process.

### Secrets

Actual credentials remain local.

Only templates and setup instructions are committed.

### Long-running processes

Long-running services should not consume random terminal tabs that the user must remember manually.

They are managed through named tmux windows and startup/stop scripts.

### Health before browser launch

A service being started is not the same as a service being ready.

The local-lab startup should verify readiness before declaring success.

### Canonical path vs debugging history

This README contains the preferred working path.

Experimental failures, debugging commands and incident history belong in:

    docs/session_commands.md

and relevant operational logs.

They should not become mandatory setup steps for a new user.


## 23. Git hygiene

Before committing:

    git status --short

Local runtime files and credentials should remain absent from staged changes.

Examples that should normally remain untracked/ignored:

    .venv/
    data/
    metadata/
    environment/local_secrets.env
    kubernetes/api-secret.yaml
    terraform/.terraform/
    terraform/*.tfstate
    terraform/*.tfstate.*

Files that SHOULD normally be committed include:

    source code
    Kubernetes manifests
    Terraform source files
    Terraform provider lock file
    CI/CD workflow
    Prometheus configuration
    Grafana provisioning
    Grafana dashboard definitions
    startup/stop scripts
    secret templates
    documentation


## 24. Current development workflow

A typical local development cycle is:

    ./scripts/start_local_lab.sh

        ↓

    use work/client tmux windows

        ↓

    modify code/configuration

        ↓

    validate locally

        ↓

    inspect:

        git status --short

        ↓

    commit

        ↓

    git push

        ↓

    GitHub Actions

        ↓

    test

        ↓

    build-and-publish

        ↓

    GHCR container artifact

The monitoring dashboard remains available during local operation so behaviour can be observed while traffic is generated.

## 25. MLOps GIS workflow

The main MLOps application is a geospatial waste-demand and municipal-operations
system based on Karşıyaka.

The purpose of the workload is not merely to predict waste volume. It provides
a cumulative application through which data engineering, model lifecycle,
operations, research computing, governance and infrastructure decisions can be
connected.

The spatial context includes:

- the real Karşıyaka administrative boundary
- the OpenStreetMap drivable road network
- WorldPop population data
- OpenStreetMap activity / POI context

The synthetic operational substrate includes:

- 100 m demand cells
- 1,200 physical bins
- 858 collection points
- 3 hubs
- 12 trucks
- vehicle-specific travel times
- traffic scenarios
- temporary road disruption
- rain
- crew availability
- shifts and breaks
- maintenance
- vehicle failures

The MLOps lifecycle implemented around this workload includes:

    operational / curated data
        ↓
    feature preparation
        ↓
    temporal train / test separation
        ↓
    reproducible training
        ↓
    MLflow experiment and artefact tracking
        ↓
    feature contract
        ↓
    batch inference
        ↓
    online serving
        ↓
    drift monitoring
        ↓
    prediction-performance monitoring
        ↓
    retraining decision

The temporal holdout is deliberate. It evaluates the model against later
observations rather than relying on a random split that would be less
representative of future inference.

The operational simulator also preserves state across time.

Explicit bin backlog and street waste make it possible to compare infrastructure
and collection-flow policies using service-level outcomes rather than treating
each simulated day as independent.

Relevant implementation is under:

    mlops/waste_gis/

Local MLflow runtime state remains outside version control.


## 26. Course coverage and repository evidence

The structured cloud, distributed-systems and research-computing programme that
produced this platform is complete.

The syllabus was followed in the following 26-topic learning order:

1. Linux and basic systems
2. networking
3. compute and virtual machines
4. storage
5. relational databases
6. AWS / GCP / Azure fundamentals
7. warehouses, data lakes and lakehouse concepts
8. ETL / ELT
9. Docker
10. distributed computing
11. Spark
12. APIs and serverless concepts
13. Kubernetes
14. IAM and security
15. Terraform
16. CI/CD
17. monitoring and reliability
18. MLOps
19. HPC and SLURM
20. MPI
21. GPU computing
22. distributed machine learning
23. governance and privacy
24. FinOps
25. hybrid and multi-cloud architecture
26. full enterprise architecture

Batch and streaming architectures and academic research-computing concerns are
also part of the broader syllabus and are connected to the relevant data,
distributed-computing and HPC sections.

Course coverage and repository implementation are not treated as identical
claims.

Some syllabus topics are architectural or conceptual by nature. The repository
does not pretend that every vendor-specific service discussed during the course
was deployed in production.

Concrete implementation evidence in the repository and local lab includes:

- Linux / WSL development and operations
- Spark-based data processing
- FastAPI serving
- Docker containerisation
- local Kubernetes workloads
- Kubernetes security controls
- Terraform
- GitHub Actions CI/CD and container build/publish
- Prometheus and Grafana observability
- local SLO-style reliability alerting
- the Karşıyaka MLOps lifecycle
- SLURM job arrays exercised against a local Docker-based SLURM lab
- MPI within a SLURM allocation
- CUDA-backed GPU computation
- PyTorch distributed training
- Ray Train
- optimizer and parameter-sharding exercises
- governance and privacy profiling
- data lineage
- adaptive workload profiling and placement
- FinOps-aware local-versus-cloud decision logic
- automated integration / integrity tests
- an enterprise architecture snapshot and reference document

The repository therefore represents both a learning record and a working
research-platform architecture.


## 27. HPC, SLURM, MPI and academic research computing

The project was exercised against a local Docker-based SLURM research-computing
lab.

The SLURM cluster runtime itself was operated as a local lab environment; the
repository contains the workload, worker and scheduling artefacts used against
that environment.

The Karşıyaka travel-matrix workload was decomposed into six independent:

    truck type × traffic scenario

combinations.

SLURM job arrays produced a canonical output containing 21,600 rows.

The distributed result was checked against the single-process canonical output.

MPI was then exercised inside a SLURM allocation using OpenMPI and mpi4py.

The distinction is important:

    SLURM
        allocates and schedules resources

    MPI
        coordinates communication among processes

The implementation also exposed a central research-computing lesson:

    distributed != automatically faster

For relatively small workloads, process startup, scheduling and communication
overhead can exceed the compute saved through parallelism.

This section connects cloud infrastructure to academic/research-computing
concerns such as:

- reproducibility
- batch scheduling
- shared compute
- provenance
- resource allocation
- scaling experiments
- workload portability


## 28. GPU computing and distributed machine learning

CUDA-backed PyTorch workloads run against the NVIDIA GPU exposed through WSL.

GPU benchmarking distinguishes:

    device compute time

from:

    end-to-end runtime

including transfer and orchestration overhead.

A corrected dense-compute benchmark demonstrated substantial acceleration on
the GPU.

The Karşıyaka overflow benchmark evaluated more than 73 million scenario
combinations and achieved a substantial GPU speedup while preserving equivalent
results.

Distributed-machine-learning exercises include:

- PyTorch DistributedDataParallel
- multi-process CPU training
- CPU / GPU model partitioning
- ZeroRedundancyOptimizer
- parameter-sharding / FSDP-style mechanics
- DeepSpeed ZeRO configuration
- Ray Train

The exercises distinguish different scaling problems.

DDP primarily addresses throughput scaling.

Optimizer and parameter sharding address memory duplication.

Model parallelism addresses models that cannot fit on one device.

Ray provides a higher-level orchestration layer.

Measured cases where orchestration overhead makes execution slower are retained
as engineering evidence rather than hidden.


## 29. Governance, privacy and lineage

Governance is implemented as an adaptive metadata and policy layer rather than
as a hard-coded list of filenames.

The governance workflow can:

- discover repository data assets
- infer data layers and domains
- enrich metadata
- profile privacy-sensitive fields
- distinguish direct and pseudonymized identifiers
- retain temporal values as potential quasi-identifiers
- apply sensitivity and privacy actions
- enforce workload-scoped governance gates

Lineage is maintained through append-only execution events.

Recorded provenance can include:

- run identifier
- timestamp
- transformation
- input assets
- output assets
- hashes
- Git state

This allows the platform to reason about where an artefact came from and whether
an upstream input has changed.

The Karşıyaka and distributed-ML scope is checked through a dedicated governance
gate.

The hybrid layer also uses lineage to resolve the minimum known input set
required by a workload before a potential transfer across an execution boundary.

Relevant implementation is under:

    governance/


## 30. FinOps and adaptive hybrid placement

FinOps is integrated into workload placement rather than implemented as a
static provider-price spreadsheet.

The central rule is:

    hard-code policy and decision workflow
        ↓
    discover operational facts at runtime

Operational facts include:

- workload CPU requirements
- RAM requirements
- GPU / VRAM requirements
- runtime
- storage footprint
- provider
- region
- machine / SKU candidate
- current cloud pricing
- observed billing
- local-server acquisition cost
- power consumption
- electricity tariff
- maintenance cost

When actual usage or billing is available, an observed point value can be used.

When a required fact is uncertain but bounded, the system can represent a
range.

When required information cannot be resolved, the result remains:

    UNKNOWN

rather than receiving an invented fallback.

The canonical placement decision tree is:

    Is cloud specifically required?
        |
       yes
        |
        +--> cloud placement evaluation
        |
       no
        |
        v
    Is the current PC sufficient?
        |
       yes --> LOCAL_PC
        |
       no
        |
        v
    Is the excess temporary?
        |
       yes --> CLOUD_BURST
        |
       no
        |
        v
    LOCAL_LINUX_SERVER
        versus
    COMMITTED / FULL CLOUD

The local profiler measures workload runtime, CPU, RAM, process-tree and
workload-specific GPU use.

The hybrid planner combines:

- telemetry
- policy
- local capacity
- lineage
- governance
- economics

before selecting or planning an execution path.

Relevant implementation is under:

    hybrid/
    finops/

The adaptive-placement code includes live-pricing adapters for Azure, AWS and
Google Cloud where the required public API access, API key or credentials are
available.

These adapters resolve pricing information for supplied or otherwise resolved
cloud candidates.

The repository does not claim fully autonomous discovery of every compatible
provider SKU.

It also does not claim that the hybrid planner currently provisions arbitrary
AWS, Google Cloud or Azure infrastructure and transfers production data
automatically.

The current implementation is a placement, pricing and execution-planning
control layer rather than a universal cloud provisioner.

Static provider prices are not treated as authoritative.


## 31. Hybrid and multi-cloud architecture

The platform is local-first when local execution satisfies capacity, policy and
economic requirements, but it is not local-only.

Hybrid execution is designed around:

- minimum necessary data movement
- governance before transfer
- provenance across execution boundaries
- short-lived or federated workload identity
- explicit cleanup of temporary cloud resources
- provider-neutral application logic where useful
- provider-specific adapters where justified

Multi-cloud is not treated as an automatic objective.

It becomes reasonable when requirements such as the following justify the
additional complexity:

- regulation
- resilience
- geography
- customer or institutional constraints
- specialized provider capabilities
- acquisition history
- meaningful vendor diversification

The architecture therefore separates:

    provider-neutral core logic

from:

    provider-specific implementation adapters

AWS, Google Cloud and Azure are mapped to common infrastructure concepts, but
the project does not represent three independent production deployments.


## 32. Enterprise architecture

The consolidated architecture separates several interacting planes.

Data plane:

    raw / operational data
        ↓
    ingestion and preprocessing
        ↓
    curated / analytical / serving layers
        ↓
    models and analytical artefacts

Compute plane:

    local CPU / GPU
    Docker
    Kubernetes
    Spark
    SLURM / MPI
    distributed ML
    optional cloud targets

Control plane:

    IAM / security
    governance / privacy
    lineage
    Terraform
    CI/CD
    observability
    reliability
    MLOps
    FinOps

Placement plane:

    telemetry
      + policy
      + capacity
      + governance
      + economics
        ↓
    execution decision

The reference architecture is maintained in:

    enterprise/ARCHITECTURE.md

The repository can also generate a machine-readable architecture snapshot from
evidence that actually exists in the project.

The architecture deliberately distinguishes domain-specific logic from
commodity infrastructure.

This supports build-versus-buy decisions without assuming that either
self-hosting or managed cloud services are always preferable.


## 33. Automated validation

The repository contains a small automated integration and integrity test suite
for critical cross-cutting invariants.

It is intentionally described as a targeted validation suite rather than as
comprehensive production test coverage.

Current tests verify that:

- the Karşıyaka governance gate passes
- the measured DDP workload routes to LOCAL_PC when local capacity is sufficient
- lineage events exist
- lineage events contain the expected provenance structure
- DDP training lineage links its input data to its output metrics

Run:

    python -m unittest discover -s tests -p 'test_*.py' -v

The enterprise architecture discovery layer also checks for implementation
evidence across capability groups such as:

- data
- ML pipelines
- HPC / distributed compute
- governance
- FinOps
- hybrid placement
- Infrastructure as Code
- containers
- tests
- documentation

The local five-test suite and the GitHub Actions pipeline should not be assumed
to be the same test surface unless the CI workflow explicitly invokes these
tests.


## 34. Engineering principles

### Measure rather than assume

Do not assume that:

- more CPU cores are automatically faster
- a GPU is always faster
- distributed execution improves runtime
- cloud is always cheaper
- local compute is free
- multi-cloud automatically improves resilience

Profile the workload and measure the result.


### Capacity first, provider second

Begin with:

    compute
    memory
    GPU / VRAM
    storage
    networking
    latency
    reliability
    governance
    cost

Then map those requirements to AWS, Google Cloud, Azure, local hardware, HPC or
another execution environment.


### Governance before movement

A technically possible data transfer is not automatically acceptable.

Lineage, privacy classification and organizational policy should be evaluated
before data crosses an execution boundary.


### Provider-neutral where useful, provider-specific where justified

Portability has value, but so do managed services and provider-specific
optimization.

Vendor lock-in is treated as an architectural trade-off rather than as an
automatic failure.


### Reproducibility over remembered operations

Important system state should be represented through:

- source code
- configuration
- Infrastructure as Code
- tests
- metadata
- lineage
- documentation

rather than depending on remembered shell history.


## 35. Scope and limitations

This repository is a research, engineering and learning platform.

It is not a claim of operating a production multi-region enterprise cloud.

It demonstrates real local implementation and experimentation across:

- data engineering
- APIs
- containers
- Kubernetes
- Infrastructure as Code
- CI/CD
- observability and reliability
- MLOps
- HPC and MPI
- GPU computing
- distributed machine learning
- governance and lineage
- FinOps-aware workload placement
- hybrid / multi-cloud architectural reasoning
- enterprise architecture

AWS, Google Cloud and Azure mappings connect provider-neutral concepts to
concrete implementation options.

The project does not claim that every provider-specific managed service was
deployed.

The project does not claim an always-on production cloud environment.

The project does not claim a production multi-cloud deployment.

The local Docker-based SLURM lab used for research-computing exercises is an
execution environment associated with the project rather than evidence that this
repository itself contains a production HPC cluster.

The adaptive hybrid layer currently plans placement and pricing decisions; it is
not presented as a universal autonomous cloud provisioner.

Future work can therefore focus on real applications, operational automation and
new research workloads rather than extending a checklist of course topics.

## Local Operations Meta-Agent

An experimental case-agnostic Operations Meta-Agent extends the platform with
a local LLM reasoning layer over deterministic infrastructure controls.

The architecture deliberately separates LLM reasoning from operational
authority:

    user request
        |
        v
    local Qwen meta-agent
        |
        +--> inspect_environment()
        +--> inspect_workload()
        +--> inspect_policy()
        |
        v
    deterministic placement adapter
        |
        v
    existing hybrid/adaptive_placement.py
        |
        v
    validated operational decision

The LLM may select tools and explain evidence, but its prose is not treated as
an authoritative placement decision. Missing operational facts remain UNKNOWN.

Current validated routing includes:

- `LOCAL_PC`
- `CLOUD_BURST`
- `FULL_CLOUD_ON_DEMAND_OR_SPOT`
- `FULL_OR_COMMITTED_CLOUD`
- `LOCAL_LINUX_SERVER_VS_COMMITTED_CLOUD`
- explicit `POLICY_INPUT_REQUIRED:*` states

The initial agent is read-only. It does not provision cloud infrastructure,
delete resources, modify infrastructure, or execute arbitrary shell commands.

### Two-terminal local workflow

The development workflow intentionally uses two terminals.

**PROMPT**

Used for Git, Python, tests, agent interaction and normal repository work:

    cd <project-root>
    bash scripts/enter_runtime.sh

**DEVOPS QWEN**

Used only for the local Qwen inference server and its GPU/runtime logs:

    cd <project-root>
    bash scripts/start_qwen_server.sh

The model server binds to `127.0.0.1:8080` and is not intentionally exposed to
the public network.

The model itself and its runtime cache live outside Git under the WSL-native
runtime filesystem. The default model is Qwen3-8B GGUF Q4_K_M.

This split keeps source control and agent development independent from the
long-running local inference process and makes model crashes, agent exceptions,
GPU usage and server logs easier to isolate.

### Portable runtime activation

The repository does not require a specific username, home directory, drive,
or installation path.

Activate an existing runtime in the current shell with:

    source scripts/enter_runtime.sh

Runtime resolution follows this order:

1. `RESEARCH_CLOUD_RUNTIME`
2. an existing `~/research-cloud-runtime` legacy development runtime
3. the operating system's per-user application-data location

Additional installation-specific overrides are available through:

- `RESEARCH_CLOUD_PROJECT_ROOT`
- `RESEARCH_CLOUD_RUNTIME`
- `RESEARCH_CLOUD_VENV`
- `RESEARCH_CLOUD_MANAGED_ROOT`
- `RESEARCH_CLOUD_MODEL_CACHE`
- `LLAMA_BIN`
- `QWEN_MODEL`
- `QWEN_HOST`
- `QWEN_PORT`
- `QWEN_CONTEXT_SIZE`

Machine-specific paths are configuration, not application logic.

### Operations Meta-Agent web UI

The local web interface is served by FastAPI and uses the same controlled
natural-language planning, approval, execution, verification, and audit
layers as the command-line development interface.

Start the local model server, then launch the UI API with:

    uvicorn agent.web_app:app --host 127.0.0.1 --port 8000

Open `http://127.0.0.1:8000` in a browser.

The UI contains no external CDN dependency and approval tokens are bound to
server-side analysed plans and are single-use.

### Session project location

The Operations Meta-Agent can inspect a project location selected explicitly
by the user for the current chat session.

For example:

    Use /path/to/project as the project location

When running through WSL, Windows paths such as:

    C:\Users\name\project

are translated to the corresponding WSL-mounted path when available.

The selected project root is validated before use and remains scoped to the
current chat session. Subsequent project questions use that root without
changing the global runtime configuration or another session's project root.

The inspection boundary continues to treat the selected root as the filesystem
boundary for project reads and searches.

