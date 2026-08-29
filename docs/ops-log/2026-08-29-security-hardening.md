# Security hardening incident log — 2026-08-29

## Scope

Local kind Kubernetes deployment for `research-cloud-api`.

## Failures encountered and resolutions

### 1. RBAC expected denial returned exit code 1

`kubectl auth can-i delete pods` correctly returned `no`, but also returned
exit status 1. With `set -e`, the runner interpreted the expected denial as
a script failure.

Resolution:
- capture output with `|| true`
- explicitly validate expected values:
  - get pods = yes
  - delete pods = no

This occurred in both the RBAC verification step and the final report.

### 2. Runtime verification selected a stale rollout Pod

After a Deployment rollout, selecting `.items[0]` could select a terminating
or stale Pod.

Resolution:
- wait for Ready Pods
- filter Running Pods
- exclude objects with `deletionTimestamp`
- select an active non-terminating Pod before runtime checks

### 3. HTTPS Gateway existed but Envoy had no listeners

Kubernetes reported the Gateway as programmed, but HTTPS timed out.

Envoy logs showed:

`StreamAggregatedResources ... No route to host`

Root cause:
- cloud-provider-kind xDS server listened on `172.17.0.1`
- Envoy Gateway container was attached only to the `kind` Docker network
- Envoy could not reach the xDS control plane
- dynamic listeners for ports 80 and 443 were never loaded

Resolution:
- attach Gateway container to Docker `bridge` network
- verify xDS reachability
- restart Envoy
- confirm dynamic listeners `listener-80` and `listener-443`

### 4. WSL/Docker host-published HTTPS timed out

After xDS recovery:
- TLS from inside Envoy succeeded
- TLS from the kind node to the Gateway succeeded
- TLS 1.3 certificate negotiation was verified
- host-side Docker published-port access still timed out

Resolution:
- treat Kubernetes data-plane TLS verification as authoritative for this
  local lab
- report host-side WSL/Docker access as a local networking limitation,
  not a TLS/Gateway configuration failure

### 5. API image contained unnecessary Spark/Hadoop dependencies

The API image installed the full project `requirements.lock.txt`, including
PySpark. Trivy found multiple HIGH/CRITICAL vulnerabilities in Spark/Hadoop
transitive Java dependencies.

Resolution:
- create a minimal API runtime dependency set
- remove PySpark/Spark/Hadoop from the serving image
- separate compute dependencies from serving dependencies

Result:
- large Java attack surface removed

### 6. Remaining OpenSSL vulnerabilities in base image

After dependency minimization, Trivy reported three HIGH vulnerabilities in
Debian OpenSSL packages.

Resolution:
- patch OpenSSL packages during image build
- rebuild from a fresh base
- rerun Trivy

Final result:
- HIGH: 0
- CRITICAL: 0

### 7. Final report appeared to hang

The report body was redirected to a file, so the terminal appeared silent.
The actual failure was again an expected RBAC denial returning exit code 1.

Resolution:
- handle expected RBAC denial explicitly
- retain report at `metadata/security/report.txt`

## Verified local security state

- non-root container
- privilege escalation disabled
- Linux capabilities dropped
- read-only root filesystem
- RuntimeDefault seccomp
- ServiceAccount token automount disabled
- least-privilege RBAC
- ClusterIP Service
- TLS-configured Ingress/Gateway
- vulnerability scan: 0 HIGH / 0 CRITICAL
- NetworkPolicy object present
- NetworkPolicy enforcement not claimed without CNI verification

## Deferred to real deployment

- publicly trusted CA / Let's Encrypt
- host firewall / cloud security group
- SSH hardening
- OS patch policy
- production NetworkPolicy enforcement
- backup / restore
- centralized logging and audit retention
- production key / secret management
