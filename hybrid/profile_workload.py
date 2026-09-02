from __future__ import annotations

from pathlib import Path
import argparse
import json
import os
import shlex
import subprocess
import sys
import time

import psutil


ROOT = Path(__file__).resolve().parents[1]
LINEAGE_LOG = ROOT / "governance" / "lineage_events.jsonl"
OUTPUT_DIR = ROOT / "hybrid" / "workload_profiles"

OUTPUT_DIR.mkdir(
    parents=True,
    exist_ok=True,
)


def repo_relative(path):
    p = Path(path)

    if not p.is_absolute():
        p = ROOT / p

    try:
        return str(
            p.resolve().relative_to(
                ROOT.resolve()
            )
        )
    except Exception:
        return str(p.resolve())


def load_lineage():
    if not LINEAGE_LOG.exists():
        return []

    events = []

    with LINEAGE_LOG.open() as f:
        for line in f:
            line = line.strip()

            if line:
                events.append(
                    json.loads(line)
                )

    return events


def lineage_io(entrypoint):
    events = load_lineage()

    matching = [
        e
        for e in events
        if e.get("transformation")
        == entrypoint
    ]

    if not matching:
        return [], []

    latest = matching[-1]

    inputs = [
        x["path"]
        for x in latest.get(
            "inputs",
            []
        )
    ]

    outputs = [
        x["path"]
        for x in latest.get(
            "outputs",
            []
        )
    ]

    return inputs, outputs


def gpu_memory_for_pids(pids):
    """
    Sum GPU memory only for compute processes belonging
    to this workload's process tree.
    """

    if not pids:
        return 0.0

    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,used_memory",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )

        total_mib = 0.0

        for line in result.stdout.splitlines():
            parts = [
                x.strip()
                for x in line.split(",")
            ]

            if len(parts) != 2:
                continue

            try:
                pid = int(parts[0])
                used = float(parts[1])
            except ValueError:
                continue

            if pid in pids:
                total_mib += used

        return total_mib

    except Exception:
        return 0.0


def process_tree(root_process):
    processes = []

    try:
        processes.append(
            psutil.Process(
                root_process.pid
            )
        )
    except Exception:
        return []

    try:
        processes.extend(
            processes[0].children(
                recursive=True
            )
        )
    except Exception:
        pass

    return processes


def sample_process_tree(root_process):
    """
    Aggregate current RAM plus cumulative CPU time across
    the complete workload process tree.
    """

    processes = process_tree(
        root_process
    )

    rss_bytes = 0
    cpu_seconds = 0.0
    pids = []

    for proc in processes:
        try:
            rss_bytes += (
                proc.memory_info().rss
            )

            times = proc.cpu_times()

            cpu_seconds += (
                times.user
                + times.system
            )

            pids.append(
                proc.pid
            )

        except (
            psutil.NoSuchProcess,
            psutil.AccessDenied,
        ):
            continue

    return {
        "rss_bytes":
            rss_bytes,

        "cpu_seconds":
            cpu_seconds,

        "process_count":
            len(pids),

        "pids":
            pids,
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--name",
        required=True,
    )

    parser.add_argument(
        "--entrypoint",
        required=True,
    )

    parser.add_argument(
        "--command",
        required=True,
        help=(
            "Exact local command to profile, quoted as "
            "one shell argument."
        ),
    )

    parser.add_argument(
        "--sample-seconds",
        type=float,
        default=0.25,
    )

    args = parser.parse_args()

    entrypoint = repo_relative(
        args.entrypoint
    )

    lineage_inputs, lineage_outputs = (
        lineage_io(
            entrypoint
        )
    )

    command = shlex.split(
        args.command
    )

    print(
        "=== WORKLOAD PROFILER ==="
    )

    print(
        "Workload:",
        args.name,
    )

    print(
        "Command:",
        " ".join(command),
    )

    print()

    started = time.perf_counter()

    proc = subprocess.Popen(
        command,
        cwd=ROOT,
    )

    peak_rss = 0
    peak_cpu_cores = 0.0
    peak_processes = 0
    peak_gpu_mib = 0.0

    previous_cpu_seconds = None
    previous_sample_time = None

    while proc.poll() is None:

        sample = sample_process_tree(
            proc
        )

        peak_rss = max(
            peak_rss,
            sample["rss_bytes"],
        )

        peak_processes = max(
            peak_processes,
            sample["process_count"],
        )

        now = time.perf_counter()

        if (
            previous_cpu_seconds is not None
            and previous_sample_time is not None
        ):
            elapsed = (
                now - previous_sample_time
            )

            if elapsed > 0:
                cpu_cores = max(
                    0.0,
                    (
                        sample["cpu_seconds"]
                        - previous_cpu_seconds
                    )
                    / elapsed,
                )

                peak_cpu_cores = max(
                    peak_cpu_cores,
                    cpu_cores,
                )

        previous_cpu_seconds = (
            sample["cpu_seconds"]
        )

        previous_sample_time = now

        gpu_mib = gpu_memory_for_pids(
            set(sample["pids"])
        )

        peak_gpu_mib = max(
            peak_gpu_mib,
            gpu_mib,
        )

        time.sleep(
            args.sample_seconds
        )

    return_code = proc.wait()

    ended = time.perf_counter()

    runtime_seconds = (
        ended - started
    )

    peak_ram_gib = (
        peak_rss
        / (1024 ** 3)
    )

    observed_cpu_cores = (
        peak_cpu_cores
    )

    peak_gpu_memory_gib = (
        peak_gpu_mib
        / 1024
    )

    request = {
        "workload_name":
            args.name,

        "entrypoint":
            entrypoint,

        "telemetry_source":
            "actual_local_observation",

        "local_run": {
            "return_code":
                return_code,

            "runtime_seconds":
                runtime_seconds,

            "peak_ram_gib":
                peak_ram_gib,

            "peak_cpu_cores":
                observed_cpu_cores,

            "peak_process_count":
                peak_processes,

            "peak_gpu_memory_gib":
                (
                    peak_gpu_memory_gib
                    if peak_gpu_memory_gib > 0
                    else None
                ),
        },

        # These requirements come directly from observed
        # telemetry. They are measurements, not invented
        # safety margins.
        "required_cpu_threads":
            (
                max(
                    1,
                    int(
                        observed_cpu_cores
                        + 0.999999
                    ),
                )
                if observed_cpu_cores > 0
                else None
            ),

        "required_ram_gib":
            (
                peak_ram_gib
                if peak_ram_gib > 0
                else None
            ),

        "required_gpu_memory_gib":
            (
                peak_gpu_memory_gib
                if peak_gpu_memory_gib > 0
                else None
            ),

        "lineage_inputs":
            lineage_inputs,

        "lineage_outputs":
            lineage_outputs,

        # POLICY FACTS:
        #
        # We do NOT silently turn unknown into False.
        # These may later come from pipeline policy,
        # governance requirements or deployment metadata.
        "cloud_required":
            None,

        "temporary_excess":
            None,

        "sustained_high_load":
            None,

        # No cloud runtime has happened yet.
        # Therefore no fabricated runtime band.
        "actual_cloud_billed_seconds":
            None,

        "cloud_runtime_seconds":
            None,

        # Provider candidates are discovered/resolved
        # later rather than embedded here.
        "cloud_candidates":
            [],
    }

    output = (
        OUTPUT_DIR
        / f"{args.name}.json"
    )

    output.write_text(
        json.dumps(
            request,
            indent=2,
        )
    )

    print()
    print(
        "=== OBSERVED TELEMETRY ==="
    )

    print(
        "Runtime:",
        f"{runtime_seconds:.4f}s",
    )

    print(
        "Peak RAM:",
        f"{peak_ram_gib:.3f} GiB",
    )

    print(
        "Peak CPU:",
        f"{observed_cpu_cores:.2f} logical cores",
    )

    print(
        "Peak workload GPU memory:",
        (
            f"{peak_gpu_memory_gib:.3f} GiB"
            if peak_gpu_memory_gib > 0
            else "none observed"
        ),
    )

    print(
        "Process-tree peak:",
        peak_processes,
    )

    print()
    print(
        "Lineage inputs:",
        len(lineage_inputs),
    )

    for path in lineage_inputs:
        print(
            "  <-",
            path,
        )

    print()
    print(
        "Policy state:",
        "UNKNOWN until resolved",
    )

    print(
        "Profile:",
        output,
    )

    if return_code != 0:
        sys.exit(return_code)


if __name__ == "__main__":
    main()
