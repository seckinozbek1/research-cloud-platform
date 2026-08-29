#!/usr/bin/env bash
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="$ROOT/metadata/security"
STATE_FILE="$STATE_DIR/hardening.state"
CERT_DIR="$STATE_DIR/tls"

mkdir -p "$STATE_DIR" "$CERT_DIR"
touch "$STATE_FILE"

CURRENT_STEP="startup"
LAST_COMMAND=""

fail() {
    local rc=$?
    local failed_command="${BASH_COMMAND:-unknown}"

    echo
    echo "=================================================="
    echo "HARDENING STOPPED"
    echo "Step: $CURRENT_STEP"
    echo "Exit code: $rc"
    echo "Failed command:"
    echo "  $failed_command"
    echo
    echo "Fix the error, then run this same script again."
    echo "Completed steps are recorded in:"
    echo "  $STATE_FILE"
    echo "=================================================="
    exit "$rc"
}

trap 'LAST_COMMAND=$BASH_COMMAND' DEBUG
trap fail ERR

done_step() {
    grep -qxF "$1" "$STATE_FILE"
}

mark_done() {
    if ! done_step "$1"; then
        echo "$1" >> "$STATE_FILE"
    fi
}

run_step() {
    local id="$1"
    local title="$2"
    local fn="$3"

    CURRENT_STEP="$id - $title"

    if done_step "$id"; then
        echo "[SKIP] $id - $title"
        return
    fi

    echo
    echo "=================================================="
    echo "[RUN ] $id - $title"
    echo "=================================================="

    "$fn"

    mark_done "$id"
    echo "[DONE] $id - $title"
}

require_commands() {
    for cmd in kubectl docker openssl git python; do
        command -v "$cmd" >/dev/null
    done
}

step_01_preflight() {
    require_commands

    echo "Checking Kubernetes API connectivity..."

    local ok="no"

    for attempt in 1 2 3; do
        if kubectl cluster-info \
            --request-timeout=5s \
            >/dev/null 2>&1; then
            ok="yes"
            break
        fi

        echo "Kubernetes API attempt ${attempt}/3 failed."
        sleep 2
    done

    if [[ "$ok" != "yes" ]]; then
        echo "ERROR: Kubernetes API is unavailable after bounded retries."
        echo
        echo "--- kubectl context ---"
        kubectl config current-context 2>&1 || true
        echo
        echo "--- cluster-info ---"
        timeout 8 kubectl cluster-info 2>&1 || true
        return 1
    fi

    for resource in \
        "deployment/research-cloud-api" \
        "service/research-cloud-api" \
        "ingress/research-cloud-api"
    do
        if ! kubectl get "$resource" \
            --request-timeout=5s \
            >/dev/null 2>&1; then
            echo "ERROR: required Kubernetes resource missing/unavailable: $resource"
            return 1
        fi
    done

    echo "Preflight checks passed."
}

step_02_secret_hygiene() {
    cd "$ROOT"

    local secret_ignore='kubernetes/api-secret.yaml'
    local runtime_ignore='metadata/security/'

    # Tracked credentials/private material are ambiguous and potentially
    # dangerous. Never attempt to silently untrack them.
    if git ls-files --error-unmatch kubernetes/api-secret.yaml \
        >/dev/null 2>&1; then
        echo "ERROR: kubernetes/api-secret.yaml is tracked by Git."
        echo "Manual review is required. Refusing automatic recovery."
        return 1
    fi

    if git ls-files --error-unmatch metadata/security/tls/tls.key \
        >/dev/null 2>&1; then
        echo "ERROR: TLS private key is tracked by Git."
        echo "Manual credential-remediation review is required."
        return 1
    fi

    # Missing ignore rules are deterministic and safe to repair.
    if ! grep -qxF "$secret_ignore" .gitignore; then
        echo
        echo "# Local Kubernetes secrets" >> .gitignore
        echo "$secret_ignore" >> .gitignore
        echo "Added missing Secret ignore rule."
    fi

    if ! grep -qxF "$runtime_ignore" .gitignore; then
        echo
        echo "# Local security hardening runtime state / certificates" >> .gitignore
        echo "$runtime_ignore" >> .gitignore
        echo "Added missing security-runtime ignore rule."
    fi

    # Catch the known demo token if it accidentally enters tracked files.
    if git grep -n 'demo-local-token' -- \
        . ':!scripts/security_hardening.sh'; then
        echo "ERROR: demo secret value found in tracked project content."
        return 1
    fi

    echo "Secret manifest/private runtime material are untracked and ignored."
}

step_03_service_and_rbac() {
    local service_type
    local service_account
    local can_get
    local can_delete

    service_type="$(kubectl get service research-cloud-api \
        -o jsonpath='{.spec.type}')"
    echo "Service type: $service_type"

    if [[ "$service_type" != "ClusterIP" ]]; then
        echo "ERROR: expected ClusterIP, got: $service_type"
        return 1
    fi

    service_account="$(kubectl get deployment research-cloud-api \
        -o jsonpath='{.spec.template.spec.serviceAccountName}')"
    echo "ServiceAccount: $service_account"

    if [[ "$service_account" != "research-cloud-api" ]]; then
        echo "ERROR: unexpected ServiceAccount: $service_account"
        return 1
    fi

    can_get="$(kubectl auth can-i get pods \
        --as=system:serviceaccount:default:research-cloud-api 2>&1 || true)"
    echo "Can get pods: $can_get"

    if [[ "$can_get" != "yes" ]]; then
        echo "ERROR: workload should be able to read pods."
        return 1
    fi

    can_delete="$(kubectl auth can-i delete pods \
        --as=system:serviceaccount:default:research-cloud-api 2>&1 || true)"
    echo "Can delete pods: $can_delete"

    if [[ "$can_delete" != "no" ]]; then
        echo "ERROR: workload unexpectedly has permission to delete pods."
        return 1
    fi

    echo "RBAC least privilege verified."
}

step_04_container_hardening_manifest() {
    cd "$ROOT"

    python - <<'PYINNER'
from pathlib import Path

p = Path("kubernetes/api-deployment.yaml")
text = p.read_text()

needle = """      serviceAccountName: research-cloud-api
      containers:
"""

replacement = """      serviceAccountName: research-cloud-api
      automountServiceAccountToken: false
      securityContext:
        seccompProfile:
          type: RuntimeDefault
      containers:
"""

if "automountServiceAccountToken:" not in text:
    if needle not in text:
        raise SystemExit(
            "Expected Deployment ServiceAccount/container block not found."
        )
    text = text.replace(needle, replacement, 1)

needle = """        - name: api
          image: research-cloud-api:local
          imagePullPolicy: Never
"""

replacement = """        - name: api
          image: research-cloud-api:local
          imagePullPolicy: Never
          securityContext:
            allowPrivilegeEscalation: false
            runAsNonRoot: true
            runAsUser: 10001
            runAsGroup: 10001
            readOnlyRootFilesystem: true
            capabilities:
              drop:
                - ALL
"""

if "allowPrivilegeEscalation:" not in text:
    if needle not in text:
        raise SystemExit(
            "Expected API container image block not found."
        )
    text = text.replace(needle, replacement, 1)

p.write_text(text)
PYINNER

    # API itself does not need the Kubernetes API token.
    kubectl apply -f kubernetes/api-deployment.yaml

    local rollout_ok="no"

    for attempt in 1 2; do
        echo "Waiting for hardened Deployment rollout (${attempt}/2)..."

        if timeout 130 kubectl rollout status \
            deployment/research-cloud-api \
            --timeout=120s; then
            rollout_ok="yes"
            break
        fi

        echo "Rollout attempt ${attempt}/2 did not complete."
        sleep 3
    done

    if [[ "$rollout_ok" != "yes" ]]; then
        echo
        echo "ERROR: hardened Deployment rollout did not become healthy."
        echo
        echo "--- Deployment ---"
        timeout 8 kubectl get deployment research-cloud-api -o wide \
            2>&1 || true
        echo
        echo "--- Pods ---"
        timeout 8 kubectl get pods -l app=research-cloud-api -o wide \
            2>&1 || true
        echo
        echo "--- Recent events ---"
        timeout 8 kubectl get events \
            --sort-by=.metadata.creationTimestamp \
            2>&1 | tail -40 || true
        echo
        echo "--- Recent API logs ---"
        timeout 10 kubectl logs \
            -l app=research-cloud-api \
            --tail=50 \
            --prefix=true \
            2>&1 || true
        return 1
    fi

    echo "Hardened Deployment rollout completed."
}

step_05_runtime_security_verify() {
    local pod
    local automount
    local escalation
    local readonly
    local nonroot

    kubectl wait \
        --for=condition=Ready \
        pod \
        -l app=research-cloud-api \
        --timeout=60s >/dev/null

    pod="$(
        kubectl get pods \
            -l app=research-cloud-api \
            --field-selector=status.phase=Running \
            -o json |
        python -c '
import json, sys

data = json.load(sys.stdin)

pods = [
    p for p in data["items"]
    if not p["metadata"].get("deletionTimestamp")
]

if not pods:
    raise SystemExit("No non-terminating Running Pod found")

pods.sort(
    key=lambda p: p["metadata"]["creationTimestamp"],
    reverse=True
)

print(pods[0]["metadata"]["name"])
'
    )"

    echo "Verifying Pod: $pod"

    automount="$(kubectl get pod "$pod" \
        -o jsonpath='{.spec.automountServiceAccountToken}')"
    echo "automountServiceAccountToken: $automount"
    [[ "$automount" == "false" ]] || {
        echo "ERROR: service-account token automount is not disabled."
        return 1
    }

    escalation="$(kubectl get pod "$pod" \
        -o jsonpath='{.spec.containers[0].securityContext.allowPrivilegeEscalation}')"
    echo "allowPrivilegeEscalation: $escalation"
    [[ "$escalation" == "false" ]] || {
        echo "ERROR: privilege escalation is not disabled."
        return 1
    }

    readonly="$(kubectl get pod "$pod" \
        -o jsonpath='{.spec.containers[0].securityContext.readOnlyRootFilesystem}')"
    echo "readOnlyRootFilesystem: $readonly"
    [[ "$readonly" == "true" ]] || {
        echo "ERROR: root filesystem is not read-only."
        return 1
    }

    nonroot="$(kubectl get pod "$pod" \
        -o jsonpath='{.spec.containers[0].securityContext.runAsNonRoot}')"
    echo "runAsNonRoot: $nonroot"
    [[ "$nonroot" == "true" ]] || {
        echo "ERROR: container is not required to run as non-root."
        return 1
    }

    echo "Runtime identity:"
    kubectl exec "$pod" -- id

    echo "Runtime securityContext verified."
}

gateway_container() {
    docker ps --format '{{.Names}}' |
        grep '^kindccm-gw-' |
        head -1 || true
}

ensure_gateway_kubernetes_routes() {
    local gw
    local gw_pid
    local node_ip
    local pod_cidr
    local service_ip

    gw="$(gateway_container)"

    if [[ -z "$gw" ]]; then
        echo "ERROR: Gateway container not found."
        return 1
    fi

    gw_pid="$(docker inspect -f '{{.State.Pid}}' "$gw")"

    node_ip="$(
        docker inspect research-cloud-control-plane \
            --format '{{with index .NetworkSettings.Networks "kind"}}{{.IPAddress}}{{end}}'
    )"

    pod_cidr="$(
        kubectl get node research-cloud-control-plane \
            -o jsonpath='{.spec.podCIDR}'
    )"

    service_ip="$(
        kubectl get service research-cloud-api \
            -o jsonpath='{.spec.clusterIP}'
    )"

    if [[ -z "$node_ip" || -z "$pod_cidr" || -z "$service_ip" ]]; then
        echo "ERROR: could not determine Gateway routing inputs."
        echo "node_ip=$node_ip"
        echo "pod_cidr=$pod_cidr"
        echo "service_ip=$service_ip"
        return 1
    fi

    echo "Ensuring Gateway routes:"
    echo "  Pod CIDR:   $pod_cidr via $node_ip"
    echo "  Service IP: $service_ip/32 via $node_ip"

    if sudo -n true 2>/dev/null; then
        sudo nsenter -t "$gw_pid" -n \
            ip route replace "$pod_cidr" via "$node_ip"

        sudo nsenter -t "$gw_pid" -n \
            ip route replace "$service_ip/32" via "$node_ip"
    else
        echo "ERROR: Gateway route repair requires sudo."
        echo "Run 'sudo -v' once, then rerun the hardening script."
        return 1
    fi

    # Verify actual upstream reachability.
    if ! docker exec "$gw" bash -c \
        "timeout 3 bash -c '</dev/tcp/${service_ip}/8000'" \
        >/dev/null 2>&1; then

        echo "ERROR: Gateway still cannot reach Service ${service_ip}:8000."
        return 1
    fi

    echo "Gateway Kubernetes upstream routing verified."
}

step_06_health_after_hardening() {
    local address=""
    local response=""

    echo "Waiting for Ingress address..."

    for attempt in $(seq 1 10); do
        address="$(
            kubectl get ingress research-cloud-api \
                --request-timeout=5s \
                -o jsonpath='{.status.loadBalancer.ingress[0].ip}' \
                2>/dev/null || true
        )"

        [[ -n "$address" ]] && break

        echo "Ingress address attempt ${attempt}/10 not ready."
        sleep 2
    done

    if [[ -z "$address" ]]; then
        echo "ERROR: Ingress never received an address."
        return 1
    fi

    echo "Ingress address: $address"

    # Local WSL host networking may not reach the kind Gateway directly.
    # Therefore verify the real Kubernetes data plane from the kind node.
    ensure_gateway_kubernetes_routes

    response="$(
        docker exec research-cloud-control-plane bash -lc "
            exec 3<>/dev/tcp/${address}/80
            printf 'GET /health HTTP/1.1\r\nHost: research-cloud.local\r\nConnection: close\r\n\r\n' >&3
            timeout 6 cat <&3
        " 2>&1 || true
    )"

    if ! grep -q 'HTTP/1.1 200' <<< "$response"; then
        echo "ERROR: Ingress health endpoint did not return HTTP 200."
        echo
        echo "$response"
        echo
        echo "--- Ingress ---"
        timeout 8 kubectl get ingress research-cloud-api -o wide 2>&1 || true
        echo
        echo "--- Service ---"
        timeout 8 kubectl get service research-cloud-api -o wide 2>&1 || true
        echo
        echo "--- EndpointSlices ---"
        timeout 8 kubectl get endpointslice \
            -l kubernetes.io/service-name=research-cloud-api \
            -o wide 2>&1 || true
        return 1
    fi

    echo "Application health verified through the Kubernetes Ingress data plane."
}

step_07_tls_certificate() {
    cd "$ROOT"

    mkdir -p "$CERT_DIR"

    # Never silently continue if a private key has entered Git tracking.
    if git ls-files --error-unmatch metadata/security/tls/tls.key \
        >/dev/null 2>&1; then
        echo "ERROR: TLS private key is tracked by Git."
        return 1
    fi

    if [[ ! -s "$CERT_DIR/tls.crt" || ! -s "$CERT_DIR/tls.key" ]]; then
        echo "Generating local self-signed TLS certificate."

        openssl req -x509 -nodes -newkey rsa:2048 \
            -keyout "$CERT_DIR/tls.key" \
            -out "$CERT_DIR/tls.crt" \
            -days 7 \
            -subj "/CN=research-cloud.local" \
            -addext "subjectAltName=DNS:research-cloud.local"
    fi

    chmod 600 "$CERT_DIR/tls.key"

    # Validate that the certificate and private key parse correctly.
    if ! timeout 5 openssl x509 \
        -in "$CERT_DIR/tls.crt" \
        -noout \
        >/dev/null 2>&1; then
        echo "ERROR: local TLS certificate is invalid."
        return 1
    fi

    if ! timeout 5 openssl pkey \
        -in "$CERT_DIR/tls.key" \
        -noout \
        >/dev/null 2>&1; then
        echo "ERROR: local TLS private key is invalid."
        return 1
    fi

    # Ensure the key and certificate belong together.
    local cert_pub
    local key_pub

    cert_pub="$(
        openssl x509 -in "$CERT_DIR/tls.crt" -pubkey -noout |
        openssl pkey -pubin -outform DER 2>/dev/null |
        sha256sum |
        awk '{print $1}'
    )"

    key_pub="$(
        openssl pkey -in "$CERT_DIR/tls.key" -pubout -outform DER \
            2>/dev/null |
        sha256sum |
        awk '{print $1}'
    )"

    if [[ "$cert_pub" != "$key_pub" ]]; then
        echo "ERROR: TLS certificate and private key do not match."
        return 1
    fi

    kubectl create secret tls research-cloud-api-tls \
        --cert="$CERT_DIR/tls.crt" \
        --key="$CERT_DIR/tls.key" \
        --dry-run=client \
        -o yaml |
        kubectl apply -f -

    local secret_type
    secret_type="$(
        kubectl get secret research-cloud-api-tls \
            -o jsonpath='{.type}'
    )"

    if [[ "$secret_type" != "kubernetes.io/tls" ]]; then
        echo "ERROR: Kubernetes TLS Secret has unexpected type: $secret_type"
        return 1
    fi

    echo "Local TLS certificate/key and Kubernetes TLS Secret verified."
}

step_08_tls_ingress() {
    cd "$ROOT"

    python - <<'PYINNER'
from pathlib import Path

p = Path("kubernetes/api-ingress.yaml")

desired = """apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: research-cloud-api
spec:
  ingressClassName: cloud-provider-kind
  tls:
    - hosts:
        - research-cloud.local
      secretName: research-cloud-api-tls
  rules:
    - host: research-cloud.local
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: research-cloud-api
                port:
                  number: 8000
"""

p.write_text(desired)
PYINNER

    kubectl apply -f kubernetes/api-ingress.yaml

    ingress_ip() {
        kubectl get ingress research-cloud-api \
            -o jsonpath='{.status.loadBalancer.ingress[0].ip}' \
            2>/dev/null || true
    }

    direct_https_test() {
        local address
        address="$(ingress_ip)"

        [[ -n "$address" ]] || return 1

        curl \
            --fail \
            --silent \
            --show-error \
            --connect-timeout 3 \
            -k \
            --resolve "research-cloud.local:443:${address}" \
            https://research-cloud.local/health \
            >/dev/null
    }

    published_https_port() {
        local container="$1"

        docker port "$container" 443/tcp 2>/dev/null |
            awk '
                $1 ~ /^0\.0\.0\.0:/ {
                    sub(/^0\.0\.0\.0:/, "", $1)
                    print $1
                    exit
                }
            '
    }

    host_port_https_test() {
        local container
        local host_port

        container="$(gateway_container)"
        [[ -n "$container" ]] || return 1

        host_port="$(published_https_port "$container")"
        [[ -n "$host_port" ]] || return 1

        echo "Testing Docker-published HTTPS port: localhost:${host_port}"

        curl \
            --fail \
            --silent \
            --show-error \
            --connect-timeout 3 \
            -k \
            --resolve "research-cloud.local:${host_port}:127.0.0.1" \
            "https://research-cloud.local:${host_port}/health" \
            >/dev/null
    }

    wait_for_gateway() {
        local programmed

        for _ in $(seq 1 18); do
            programmed="$(
                kubectl get gateway kind-ingress-gateway \
                    -o jsonpath='{.status.conditions[?(@.type=="Programmed")].status}' \
                    2>/dev/null || true
            )"

            if [[ "$programmed" == "True" ]]; then
                return 0
            fi

            sleep 3
        done

        return 1
    }

    show_tls_diagnostics() {
        local container
        container="$(gateway_container)"

        echo
        echo "--- Ingress ---"
        kubectl get ingress research-cloud-api -o wide || true

        echo
        echo "--- Gateway ---"
        kubectl get gateway kind-ingress-gateway -o wide || true

        if [[ -n "$container" ]]; then
            echo
            echo "--- Gateway container ---"
            echo "$container"
            docker port "$container" || true
        else
            echo
            echo "--- Gateway container ---"
            echo "No running kindccm gateway container found."
        fi
    }

    #
    # Attempt 1:
    # normal/direct local kind Gateway address.
    #
    echo "Attempt 1: direct HTTPS through Ingress address."

    if direct_https_test; then
        echo "HTTPS verified directly through Ingress address."
        return 0
    fi

    echo "Direct HTTPS unavailable."

    #
    # Attempt 2:
    # WSL/Docker environments may expose the Gateway through a
    # Docker-published host port even when the container IP is not
    # directly reachable from the WSL host.
    #
    echo
    echo "Attempt 2: Docker-published HTTPS port."

    if host_port_https_test; then
        echo "HTTPS verified through Docker-published Gateway port."
        return 0
    fi

    #
    # Attempt 3:
    # Known cloud-provider-kind limitation:
    # if HTTPS was added after the data-plane container was created,
    # port 443 may not have been published. Recreate only the local
    # Gateway data plane and allow the controller to reconcile it.
    #
    echo
    echo "HTTPS still unavailable."
    echo "Checking whether Gateway data plane needs recreation."

    local container
    container="$(gateway_container)"

    if [[ -n "$container" ]]; then
        echo "Existing Gateway container: $container"
        docker port "$container" || true

        echo
        echo "Fallback: recreating local Gateway data plane."
        echo "Temporary local Ingress interruption is expected."

        docker rm -f "$container"
    else
        echo "No Gateway container exists; controller will be asked to recreate it."
    fi

    if kubectl get gateway kind-ingress-gateway >/dev/null 2>&1; then
        kubectl delete gateway kind-ingress-gateway
    fi

    kubectl apply -f kubernetes/api-ingress.yaml

    echo "Waiting for Gateway reconciliation..."

    if ! wait_for_gateway; then
        echo "ERROR: Gateway failed to reach Programmed=True."
        show_tls_diagnostics
        return 1
    fi

    #
    # Give Docker data plane a short bounded window to appear.
    #
    for _ in $(seq 1 12); do
        if [[ -n "$(gateway_container)" ]]; then
            break
        fi
        sleep 2
    done

    echo
    echo "Gateway reconciliation completed."

    show_tls_diagnostics

    #
    # Known WSL2/cloud-provider-kind failure:
    # Gateway Envoy may be attached only to the kind network (172.18.x)
    # while cloud-provider-kind exposes its xDS server on the Docker
    # bridge gateway (172.17.0.1). In that state the container exists
    # and may even be reported Programmed=True, but Envoy receives no
    # dynamic listeners.
    #
    local gw
    gw="$(gateway_container)"

    if [[ -n "$gw" ]]; then
        local has_443

        has_443="$(
            docker exec "$gw" sh -c               'grep -qi ":01BB " /proc/net/tcp /proc/net/tcp6 && echo yes || echo no'
        )"

        if [[ "$has_443" != "yes" ]]; then
            echo
            echo "443 listener is absent inside Envoy."
            echo "Checking xDS connectivity..."

            if ! docker exec "$gw" bash -c                 'timeout 3 bash -c "</dev/tcp/172.17.0.1/43389"'                 >/dev/null 2>&1; then

                echo "xDS is unreachable from the Gateway container."
                echo "Attaching Gateway to Docker bridge network."

                if ! docker network inspect bridge                     --format '{{json .Containers}}' |
                    grep -q "$gw"; then
                    docker network connect bridge "$gw"
                fi
            fi

            if docker exec "$gw" bash -c                 'timeout 3 bash -c "</dev/tcp/172.17.0.1/43389"'                 >/dev/null 2>&1; then

                echo "xDS reachable. Restarting Envoy Gateway container."
                docker restart "$gw" >/dev/null

                for _ in $(seq 1 15); do
                    sleep 2

                    if docker exec "$gw" sh -c                         'grep -q ":01BB " /proc/net/tcp /proc/net/tcp6'; then
                        echo "Envoy 443 listener is now active."
                        break
                    fi
                done
            fi
        fi
    fi

    #
    # Retry both legitimate local paths.
    #
    echo
    echo "Retrying direct HTTPS..."

    if direct_https_test; then
        echo "HTTPS verified directly after Gateway recreation."
        return 0
    fi

    echo "Direct path still unavailable."

    echo
    echo "Retrying Docker-published HTTPS path..."

    if host_port_https_test; then
        echo "HTTPS verified through Docker-published port after fallback."
        return 0
    fi

    echo
    echo "Host-side HTTPS path is still unavailable."
    echo "Testing the actual Kubernetes Gateway data plane from the kind node..."

    local gw
    local gw_kind_ip

    gw="$(gateway_container)"

    if [[ -n "$gw" ]]; then
        gw_kind_ip="$(
            docker inspect "$gw"                 --format '{{with index .NetworkSettings.Networks "kind"}}{{.IPAddress}}{{end}}'
        )"

        if [[ -n "$gw_kind_ip" ]]; then
            if docker exec research-cloud-control-plane bash -c "
                timeout 6 openssl s_client                     -connect ${gw_kind_ip}:443                     -servername research-cloud.local                     -brief < /dev/null 2>&1 |
                grep -q 'CONNECTION ESTABLISHED'
            "; then
                echo
                echo "HTTPS/TLS verified inside the Kubernetes data plane."
                echo "WARNING: WSL/Docker host-port HTTPS remains unavailable."
                echo "This is recorded as a local host-networking limitation,"
                echo "not as a TLS or Kubernetes Gateway failure."
                return 0
            fi
        fi
    fi

    echo
    echo "ERROR: HTTPS failed both host-side and inside the Kubernetes data plane."
    show_tls_diagnostics
    return 1
}

step_09_exposure_inventory() {
    echo "--- Services ---"
    kubectl get services

    echo
    echo "--- Ingress ---"
    kubectl get ingress

    echo
    echo "--- Listening application design ---"
    test "$(kubectl get service research-cloud-api \
        -o jsonpath='{.spec.type}')" = "ClusterIP"

    echo "Application backend is not NodePort/LoadBalancer; Ingress is the intended entry point."
}

step_10_image_scan() {
    # Use Trivy through Docker so no host package installation is required.
    # First pull may take some time and requires Internet access.
    docker run --rm \
        -v /var/run/docker.sock:/var/run/docker.sock \
        aquasec/trivy:latest \
        image \
        --severity HIGH,CRITICAL \
        --ignore-unfixed \
        --exit-code 1 \
        research-cloud-api:local
}

step_11_network_policy_manifest() {
    cd "$ROOT"

    cat > kubernetes/api-networkpolicy.yaml <<'YAML'
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: research-cloud-api
spec:
  podSelector:
    matchLabels:
      app: research-cloud-api
  policyTypes:
    - Ingress
  ingress:
    - ports:
        - protocol: TCP
          port: 8000
YAML

    kubectl apply -f kubernetes/api-networkpolicy.yaml

    echo
    echo "NetworkPolicy object created."
    echo "IMPORTANT: creation alone does NOT prove enforcement."
}

step_12_network_policy_enforcement_warning() {
    # kind clusters may use a CNI that does not enforce NetworkPolicy.
    # We deliberately refuse to claim success without an enforcement test.
    echo "NetworkPolicy requires CNI enforcement verification."
    echo "This local kind cluster must not be called network-isolated merely because the object exists."
    echo "Marking this as reviewed, NOT as production network enforcement."
}

step_13_final_report() {
    cd "$ROOT"

    {
        echo "Research Cloud Platform - Local Security Hardening Report"
        echo
        date -u
        echo
        echo "Deployment:"
        kubectl get deployment research-cloud-api
        echo
        echo "Pods:"
        kubectl get pods -l app=research-cloud-api
        echo
        echo "Ingress:"
        kubectl get ingress research-cloud-api
        echo
        echo "Service:"
        kubectl get service research-cloud-api
        echo
        echo "ServiceAccount:"
        kubectl get serviceaccount research-cloud-api
        echo
        echo "RBAC:"

        can_get="$(
            kubectl auth can-i get pods \
                --as=system:serviceaccount:default:research-cloud-api \
                2>&1 || true
        )"

        can_delete="$(
            kubectl auth can-i delete pods \
                --as=system:serviceaccount:default:research-cloud-api \
                2>&1 || true
        )"

        echo "Can get pods: $can_get"
        echo "Can delete pods: $can_delete"

        if [[ "$can_get" != "yes" ]]; then
            echo "ERROR: expected ServiceAccount to be allowed to get pods."
            return 1
        fi

        if [[ "$can_delete" != "no" ]]; then
            echo "ERROR: expected ServiceAccount to be denied pod deletion."
            return 1
        fi
    } > "$STATE_DIR/report.txt"

    echo "Report written to $STATE_DIR/report.txt"
}

run_step "01" "Preflight" step_01_preflight
run_step "02" "Secret hygiene" step_02_secret_hygiene
run_step "03" "Service exposure and RBAC" step_03_service_and_rbac
run_step "04" "Container hardening manifest" step_04_container_hardening_manifest
run_step "05" "Runtime hardening verification" step_05_runtime_security_verify
run_step "06" "Health verification" step_06_health_after_hardening
run_step "07" "Local TLS certificate" step_07_tls_certificate
run_step "08" "HTTPS Ingress" step_08_tls_ingress
run_step "09" "Exposure inventory" step_09_exposure_inventory
run_step "10" "Container vulnerability scan" step_10_image_scan
run_step "11" "NetworkPolicy manifest" step_11_network_policy_manifest
run_step "12" "NetworkPolicy enforcement boundary" step_12_network_policy_enforcement_warning
run_step "13" "Final report" step_13_final_report

echo
echo "=================================================="
echo "LOCAL HARDENING RUN COMPLETE"
echo "=================================================="
echo
echo "Still intentionally deferred to real-server deployment:"
echo "- real CA / Let's Encrypt certificate"
echo "- host firewall / cloud security group"
echo "- SSH hardening"
echo "- OS security patch policy"
echo "- backup / restore"
echo "- production NetworkPolicy CNI enforcement"
echo "- centralized logs / audit retention"
