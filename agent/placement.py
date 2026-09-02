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


def _normalize_request(
    workload: dict[str, Any],
    policy: dict[str, Any],
) -> dict[str, Any]:
    req = workload["requirements"]
    pol = policy["policy"]

    return {
        "required_cpu_threads":
            req.get("cpu_cores_required"),

        "required_ram_gib":
            req.get("memory_gib_required"),

        "required_gpu_memory_gib":
            req.get("gpu_vram_gib_required"),

        "gpu_required":
            req.get("gpu_required"),

        # Placement-policy facts come from the dedicated
        # deterministic policy inspector.
        "cloud_required":
            pol.get("cloud_required"),

        "temporary_excess":
            pol.get("temporary_excess"),

        "sustained_high_load":
            pol.get("sustained_high_load"),
    }


def resolve_agent_placement(
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """
    Deterministic bridge between agent evidence and the existing
    canonical hybrid placement engine.

    Missing facts are never converted into False defaults.
    """

    environment = evidence.get("inspect_environment")
    workload = evidence.get("inspect_workload")
    policy = evidence.get("inspect_policy")

    missing_tools = []

    if environment is None:
        missing_tools.append("inspect_environment")

    if workload is None:
        missing_tools.append("inspect_workload")

    if policy is None:
        missing_tools.append("inspect_policy")

    if missing_tools:
        return {
            "decision": "UNKNOWN",
            "status": "INPUT_REQUIRED",
            "missing": missing_tools,
            "authority": "deterministic_placement_adapter",
        }

    if policy.get("conflicts"):
        return {
            "decision": "UNKNOWN",
            "status": "CONFLICTING_INPUT",
            "conflicts": policy["conflicts"],
            "reason": (
                "Conflicting explicit placement-policy statements "
                "must be resolved before routing."
            ),
            "authority": "deterministic_placement_adapter",
        }

    local = _normalize_environment(environment)
    request = _normalize_request(workload, policy)

    # ---------------------------------------------------------
    # Canonical first question: Is cloud explicitly required?
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
    # Explicit cloud requirement bypasses local sufficiency.
    # Canonical router determines on-demand vs sustained cloud.
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
    # cloud_required is explicitly False.
    # Resource evidence is required before local sufficiency
    # can be asserted.
    # ---------------------------------------------------------

    missing_requirements = []

    if request["required_cpu_threads"] is None:
        missing_requirements.append("cpu_cores_required")

    if request["required_ram_gib"] is None:
        missing_requirements.append("memory_gib_required")

    if request["gpu_required"] is None:
        missing_requirements.append("gpu_required")

    if (
        request["gpu_required"] is True
        and request["required_gpu_memory_gib"] is None
    ):
        missing_requirements.append("gpu_vram_gib_required")

    if missing_requirements:
        return {
            "decision": "UNKNOWN",
            "status": "INPUT_REQUIRED",
            "missing": missing_requirements,
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
