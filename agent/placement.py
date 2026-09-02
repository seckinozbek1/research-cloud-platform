from __future__ import annotations

from typing import Any

from hybrid.adaptive_placement import (
    capacity_check,
    route_workload,
)


def _normalize_environment(
    environment: dict[str, Any],
) -> dict[str, Any]:
    compute = environment["compute"]
    gpu = compute.get("gpu")

    return {
        "cpu_threads": compute.get("logical_cpu_count"),
        "ram_gib": compute.get("memory_total_gib"),
        "gpu_count": 1 if gpu else 0,
        "gpu_name": gpu.get("name") if gpu else None,
        "gpu_memory_gib": (
            gpu["memory_total_mib"] / 1024
            if gpu
            and gpu.get("memory_total_mib") is not None
            else None
        ),
    }


def _normalize_workload(
    workload: dict[str, Any],
) -> dict[str, Any]:
    req = workload["requirements"]

    return {
        "required_cpu_threads":
            req.get("cpu_cores_required"),

        "required_ram_gib":
            req.get("memory_gib_required"),

        "required_gpu_memory_gib":
            req.get("gpu_vram_gib_required"),

        "gpu_required":
            req.get("gpu_required"),

        "cloud_required":
            req.get("cloud_required"),

        # These will later come from policy/workload
        # characterization tools.
        "temporary_excess": None,
        "sustained_high_load": None,
    }


def resolve_agent_placement(
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """
    Adapter between case-agnostic agent evidence and the existing
    deterministic hybrid placement engine.

    The adapter refuses to interpret missing workload facts as evidence
    of local sufficiency.
    """

    environment = evidence.get("inspect_environment")
    workload = evidence.get("inspect_workload")

    if environment is None:
        return {
            "decision": "UNKNOWN",
            "status": "INPUT_REQUIRED",
            "missing": ["inspect_environment"],
            "authority": "deterministic_placement_adapter",
        }

    if workload is None:
        return {
            "decision": "UNKNOWN",
            "status": "INPUT_REQUIRED",
            "missing": ["inspect_workload"],
            "authority": "deterministic_placement_adapter",
        }

    request = _normalize_workload(workload)
    local = _normalize_environment(environment)

    # ---------------------------------------------------------
    # Explicit cloud requirement takes precedence.
    #
    # The canonical router itself handles the remaining policy
    # questions such as sustained usage.
    # ---------------------------------------------------------

    if request["cloud_required"] is True:
        route = route_workload(
            request,
            local_sufficient=False,
        )

        return {
            "decision": route,
            "status": (
                "INPUT_REQUIRED"
                if route.startswith("POLICY_INPUT_REQUIRED:")
                else "RESOLVED"
            ),
            "authority": "hybrid.adaptive_placement.route_workload",
            "local_capacity": local,
            "normalized_request": request,
        }

    # ---------------------------------------------------------
    # Cloud-required policy itself is still unknown.
    # Do not invent False.
    # ---------------------------------------------------------

    if request["cloud_required"] is None:
        return {
            "decision": "POLICY_INPUT_REQUIRED:CLOUD_REQUIRED",
            "status": "INPUT_REQUIRED",
            "missing": ["cloud_required"],
            "authority": "hybrid.adaptive_placement.route_workload",
            "local_capacity": local,
            "normalized_request": request,
        }

    # ---------------------------------------------------------
    # cloud_required is explicitly False.
    #
    # Before deciding that local capacity is sufficient, require
    # workload-specific CPU and RAM evidence.
    # ---------------------------------------------------------

    missing = []

    if request["required_cpu_threads"] is None:
        missing.append("cpu_cores_required")

    if request["required_ram_gib"] is None:
        missing.append("memory_gib_required")

    if request["gpu_required"] is None:
        missing.append("gpu_required")

    if (
        request["gpu_required"] is True
        and request["required_gpu_memory_gib"] is None
    ):
        missing.append("gpu_vram_gib_required")

    if missing:
        return {
            "decision": "UNKNOWN",
            "status": "INPUT_REQUIRED",
            "missing": missing,
            "reason": (
                "Local sufficiency cannot be established from "
                "incomplete workload resource requirements."
            ),
            "authority": "deterministic_placement_adapter",
            "local_capacity": local,
            "normalized_request": request,
        }

    local_sufficient, constraints = capacity_check(
        local,
        request,
    )

    route = route_workload(
        request,
        local_sufficient,
    )

    return {
        "decision": route,
        "status": (
            "INPUT_REQUIRED"
            if route.startswith("POLICY_INPUT_REQUIRED:")
            else "RESOLVED"
        ),
        "authority": "hybrid.adaptive_placement",
        "local_sufficient": local_sufficient,
        "constraints": constraints,
        "local_capacity": local,
        "normalized_request": request,
    }
