from pathlib import Path
import argparse
import json
import os


ROOT = Path(__file__).resolve().parents[1]

OUTPUT = (
    ROOT
    / "hybrid"
    / "capacity_decision.json"
)


def local_capacity():
    """
    Inspect local machine resources.

    We intentionally discover the actual machine rather
    than hard-code laptop specifications.
    """

    cpu_count = os.cpu_count()

    try:
        import psutil

        ram_gib = (
            psutil.virtual_memory().total
            / (1024 ** 3)
        )

    except Exception:
        ram_gib = None

    gpu_available = False
    gpu_count = 0
    gpu_memory_gib = None
    gpu_name = None

    try:
        import torch

        gpu_available = (
            torch.cuda.is_available()
        )

        if gpu_available:
            gpu_count = (
                torch.cuda.device_count()
            )

            props = (
                torch.cuda.get_device_properties(0)
            )

            gpu_name = props.name

            gpu_memory_gib = (
                props.total_memory
                / (1024 ** 3)
            )

    except Exception:
        pass

    return {
        "cpu_threads": cpu_count,
        "ram_gib": ram_gib,
        "gpu_available": gpu_available,
        "gpu_count": gpu_count,
        "gpu_name": gpu_name,
        "gpu_memory_gib": gpu_memory_gib,
    }


def capacity_sufficient(
    local,
    required_cpu,
    required_ram,
    required_gpu_memory,
):
    reasons = []

    if (
        required_cpu is not None
        and local["cpu_threads"] is not None
        and required_cpu
        > local["cpu_threads"]
    ):
        reasons.append(
            "insufficient_cpu"
        )

    if (
        required_ram is not None
        and local["ram_gib"] is not None
        and required_ram
        > local["ram_gib"]
    ):
        reasons.append(
            "insufficient_ram"
        )

    if (
        required_gpu_memory is not None
    ):
        if not local[
            "gpu_available"
        ]:
            reasons.append(
                "gpu_unavailable"
            )

        elif (
            local["gpu_memory_gib"]
            is not None
            and required_gpu_memory
            > local["gpu_memory_gib"]
        ):
            reasons.append(
                "insufficient_gpu_memory"
            )

    return (
        len(reasons) == 0,
        reasons,
    )


def route(
    *,
    cloud_required,
    sufficient,
    temporary_excess,
    sustained_high_load,
):
    # --------------------------------------------------
    # Canonical project policy.
    # --------------------------------------------------

    if cloud_required:

        if sustained_high_load:
            return (
                "FULL_OR_COMMITTED_CLOUD"
            )

        return (
            "FULL_CLOUD_ON_DEMAND_OR_SPOT"
        )

    if sufficient:
        return "LOCAL_PC"

    if temporary_excess:
        return "CLOUD_BURST"

    return (
        "LOCAL_LINUX_SERVER_VS_COMMITTED_CLOUD"
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--cloud-required",
        action="store_true",
    )

    parser.add_argument(
        "--temporary-excess",
        action="store_true",
    )

    parser.add_argument(
        "--sustained-high-load",
        action="store_true",
    )

    parser.add_argument(
        "--required-cpu",
        type=int,
        default=None,
    )

    parser.add_argument(
        "--required-ram-gib",
        type=float,
        default=None,
    )

    parser.add_argument(
        "--required-gpu-memory-gib",
        type=float,
        default=None,
    )

    args = parser.parse_args()

    local = local_capacity()

    sufficient, reasons = (
        capacity_sufficient(
            local,
            args.required_cpu,
            args.required_ram_gib,
            args.required_gpu_memory_gib,
        )
    )

    decision = route(
        cloud_required=(
            args.cloud_required
        ),
        sufficient=sufficient,
        temporary_excess=(
            args.temporary_excess
        ),
        sustained_high_load=(
            args.sustained_high_load
        ),
    )

    result = {
        "local_capacity": local,

        "workload_requirements": {
            "cpu_threads":
                args.required_cpu,
            "ram_gib":
                args.required_ram_gib,
            "gpu_memory_gib":
                args.required_gpu_memory_gib,
        },

        "policy_inputs": {
            "cloud_required":
                args.cloud_required,
            "temporary_excess":
                args.temporary_excess,
            "sustained_high_load":
                args.sustained_high_load,
        },

        "local_capacity_sufficient":
            sufficient,

        "capacity_constraints":
            reasons,

        "routing_decision":
            decision,
    }

    OUTPUT.write_text(
        json.dumps(
            result,
            indent=2,
        )
    )

    print(
        "=== HYBRID CAPACITY ROUTER ==="
    )

    print()
    print("Local machine:")
    print(
        "  CPU threads:",
        local["cpu_threads"],
    )

    print(
        "  RAM:",
        (
            f"{local['ram_gib']:.1f} GiB"
            if local["ram_gib"]
            is not None
            else "unknown"
        ),
    )

    print(
        "  GPU:",
        (
            local["gpu_name"]
            if local["gpu_available"]
            else "none"
        ),
    )

    print(
        "  GPU memory:",
        (
            f"{local['gpu_memory_gib']:.1f} GiB"
            if local["gpu_memory_gib"]
            is not None
            else "n/a"
        ),
    )

    print()
    print(
        "Local capacity sufficient:",
        sufficient,
    )

    if reasons:
        print(
            "Constraints:",
            ", ".join(reasons),
        )

    print()
    print(
        "ROUTING DECISION:",
        decision,
    )

    print()
    print(
        "Report:",
        OUTPUT,
    )


if __name__ == "__main__":
    main()
