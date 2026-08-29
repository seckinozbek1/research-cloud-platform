
## 2026-08-29 — Kubernetes security hardening

Security hardening was executed through:

`./scripts/security_hardening.sh`

Runtime output is stored locally under:

`metadata/security/`

Important incident details and recovery steps are recorded in:

`docs/ops-log/2026-08-29-security-hardening.md`

Note: exact terminal history from earlier course sessions was not preserved.
From this checkpoint onward, reusable commands and operational procedures
should be committed to the repository rather than existing only in terminal
history.

## 2026-08-29 — Terraform introduction

```bash
terraform version
mkdir -p terraform
terraform -chdir=terraform init
terraform -chdir=terraform fmt
terraform -chdir=terraform validate
terraform -chdir=terraform plan


### First Terraform lifecycle

terraform -chdir=terraform init
terraform -chdir=terraform fmt
terraform -chdir=terraform validate
terraform -chdir=terraform plan
terraform -chdir=terraform apply
kubectl get namespace research-platform
terraform -chdir=terraform state list
terraform -chdir=terraform show

Created and managed:
kubernetes_namespace_v1.research_platform

