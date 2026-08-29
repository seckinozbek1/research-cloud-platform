# Research Cloud Platform

An evolving research-computing and data-platform project used to learn infrastructure, cloud computing, distributed systems, data engineering, deployment, security and observability from first principles.

The platform is developed locally on:

Windows 11 → WSL2 → Ubuntu → Linux shell

The project files should remain in the WSL Linux filesystem:

    ~/research-cloud-platform

rather than under `/mnt/c/`.

The current platform contains:

    research data
        ↓
    preprocessing / data engineering
        ↓
    analytical and serving datasets
        ↓
    Spark processing
        ↓
    FastAPI service
        ↓
    Docker image
        ↓
    Kubernetes
        ↓
    security / IAM controls
        ↓
    Terraform
        ↓
    GitHub Actions CI/CD
        ↓
    Prometheus
        ↓
    Grafana

The project is intentionally cumulative. New infrastructure concepts are added to the same platform rather than implemented as unrelated toy exercises.


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

Clone into the WSL Linux filesystem:

    cd ~
    git clone git@github.com:seckinozbek1/research-cloud-platform.git
    cd research-cloud-platform

The main development branch is:

    main


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

The provider lock file SHOULD be committed:

    terraform/.terraform.lock.hcl

Terraform will later be used to reproduce the platform architecture across AWS, GCP and Azure.

The intended cloud-learning workflow is:

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

The final deployment stage will be attached to a real server/cloud environment later in the course rather than simulated against an inaccessible local kind cluster.

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


## 17. Generate monitoring traffic

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


## 18. One-command local lab

The local environment is orchestrated through:

    scripts/start_local_lab.sh

The design goal is that the user should not have to manually remember which terminal must run which service.

Start:

    cd ~/research-cloud-platform
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


## 19. tmux terminal layout

The local lab creates one tmux session:

    research-cloud

with six named windows:

    0  infra
    1  api
    2  prometheus
    3  grafana
    4  client
    5  work

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


## 20. Stop the local lab

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


## 21. Operational design principles

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


## 22. Git hygiene

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


## 23. Current development workflow

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


## 24. Current scope and next stages

The repository is still an evolving course platform.

The current implementation has reached:

- Linux/system foundations
- networking
- compute
- storage
- relational databases
- cloud fundamentals
- warehouses/data lakes
- ETL/ELT
- Docker
- distributed computing
- Spark
- APIs/serverless concepts
- Kubernetes
- IAM/security
- Terraform
- CI/CD
- application monitoring in progress

Later stages will extend the same platform with:

- reliability engineering
- MLOps
- HPC / SLURM
- MPI
- GPU computing
- distributed ML
- governance/privacy
- FinOps
- hybrid cloud
- multi-cloud
- enterprise architecture

AWS, GCP and Azure exercises will reuse the infrastructure concepts already learned rather than becoming three unrelated product tutorials.
