from pathlib import Path
import statistics
import time

import numpy as np
import pandas as pd
import torch


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "waste_gis"
    / "bin_daily_generated_waste.csv"
)

SCENARIOS = 2048
REPEATS = 5


def main():
    df = pd.read_csv(INPUT_PATH)

    waste_np = df["generated_waste_kg"].to_numpy(
        dtype=np.float32
    )
    capacity_np = df["capacity_kg"].to_numpy(
        dtype=np.float32
    )

    # 50% → 200% demand stress scenarios.
    multipliers_np = np.linspace(
        0.50,
        2.00,
        SCENARIOS,
        dtype=np.float32,
    )

    observations = len(df)
    operations = observations * SCENARIOS

    print("GPU                  :", torch.cuda.get_device_name(0))
    print("Bin-day observations :", f"{observations:,}")
    print("Demand scenarios     :", f"{SCENARIOS:,}")
    print("Scenario evaluations :", f"{operations:,}")
    print()

    # ---------------------------------------------------------
    # CPU
    # ---------------------------------------------------------

    waste_cpu = torch.from_numpy(waste_np)
    capacity_cpu = torch.from_numpy(capacity_np)
    multipliers_cpu = torch.from_numpy(multipliers_np)

    # Warm-up
    projected = (
        waste_cpu[:, None]
        * multipliers_cpu[None, :]
    )
    excess = torch.clamp(
        projected - capacity_cpu[:, None],
        min=0,
    )
    _ = excess.sum().item()

    cpu_times = []
    cpu_result = None

    for _ in range(REPEATS):
        t0 = time.perf_counter()

        projected = (
            waste_cpu[:, None]
            * multipliers_cpu[None, :]
        )

        excess = torch.clamp(
            projected - capacity_cpu[:, None],
            min=0,
        )

        overflow_events = (
            excess > 0
        ).sum().item()

        total_excess_kg = excess.sum().item()

        cpu_times.append(
            time.perf_counter() - t0
        )

        cpu_result = (
            overflow_events,
            total_excess_kg,
        )

    cpu_time = statistics.median(cpu_times)

    del projected, excess

    # ---------------------------------------------------------
    # GPU
    # ---------------------------------------------------------

    waste_gpu = waste_cpu.cuda()
    capacity_gpu = capacity_cpu.cuda()
    multipliers_gpu = multipliers_cpu.cuda()

    # Warm-up
    projected_gpu = (
        waste_gpu[:, None]
        * multipliers_gpu[None, :]
    )

    excess_gpu = torch.clamp(
        projected_gpu - capacity_gpu[:, None],
        min=0,
    )

    _ = excess_gpu.sum()

    torch.cuda.synchronize()

    gpu_times = []
    gpu_result = None

    for _ in range(REPEATS):
        torch.cuda.synchronize()
        t0 = time.perf_counter()

        projected_gpu = (
            waste_gpu[:, None]
            * multipliers_gpu[None, :]
        )

        excess_gpu = torch.clamp(
            projected_gpu - capacity_gpu[:, None],
            min=0,
        )

        overflow_events_gpu = (
            excess_gpu > 0
        ).sum()

        total_excess_gpu = excess_gpu.sum()

        torch.cuda.synchronize()

        gpu_times.append(
            time.perf_counter() - t0
        )

        gpu_result = (
            overflow_events_gpu.item(),
            total_excess_gpu.item(),
        )

    gpu_time = statistics.median(gpu_times)

    # ---------------------------------------------------------
    # Results
    # ---------------------------------------------------------

    print("CPU median seconds    :", f"{cpu_time:.6f}")
    print("GPU median seconds    :", f"{gpu_time:.6f}")
    print("GPU speedup           :", f"{cpu_time / gpu_time:.2f}x")

    print()
    print(
        "CPU throughput        :",
        f"{operations / cpu_time:,.0f} evaluations/s",
    )
    print(
        "GPU throughput        :",
        f"{operations / gpu_time:,.0f} evaluations/s",
    )

    print()
    print("CPU overflow events   :", f"{cpu_result[0]:,}")
    print("GPU overflow events   :", f"{gpu_result[0]:,}")

    relative_error = abs(
        cpu_result[1] - gpu_result[1]
    ) / max(abs(cpu_result[1]), 1)

    print(
        "Total excess rel.err  :",
        f"{relative_error:.3e}",
    )

    assert cpu_result[0] == gpu_result[0]
    assert relative_error < 1e-5

    print()
    print("Validation            : PASS")


if __name__ == "__main__":
    main()
