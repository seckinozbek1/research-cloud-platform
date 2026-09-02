from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any

from agent.workload import inspect_workload_request
from agent.policy import inspect_policy_request


def _run_readonly(command: list[str]) -> str | None:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()
    except Exception:
        return None


def _memory_gib() -> float | None:
    meminfo = Path("/proc/meminfo")

    if not meminfo.exists():
        return None

    for line in meminfo.read_text().splitlines():
        if line.startswith("MemTotal:"):
            kib = int(line.split()[1])
            return round(kib / 1024 / 1024, 2)

    return None


def inspect_environment() -> dict[str, Any]:
    """
    Read-only inspection of the current execution environment.

    This function does not modify files, start services,
    provision infrastructure, or access credentials.
    """

    repo = Path(
        os.environ.get(
            "RESEARCH_CLOUD_REPO",
            os.getcwd(),
        )
    ).resolve()

    runtime = os.environ.get("RESEARCH_CLOUD_RUNTIME")

    gpu = None

    if shutil.which("nvidia-smi"):
        gpu_output = _run_readonly(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.free",
                "--format=csv,noheader,nounits",
            ]
        )

        if gpu_output:
            parts = [part.strip() for part in gpu_output.splitlines()[0].split(",")]

            if len(parts) == 3:
                gpu = {
                    "name": parts[0],
                    "memory_total_mib": int(parts[1]),
                    "memory_free_mib": int(parts[2]),
                }

    git_branch = _run_readonly(
        ["git", "-C", str(repo), "branch", "--show-current"]
    )

    git_status = _run_readonly(
        ["git", "-C", str(repo), "status", "--short"]
    )

    source_fs = _run_readonly(
        ["df", "-T", str(repo)]
    )

    runtime_fs = (
        _run_readonly(["df", "-T", runtime])
        if runtime
        else None
    )

    return {
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        "compute": {
            "logical_cpu_count": os.cpu_count(),
            "memory_total_gib": _memory_gib(),
            "gpu": gpu,
        },
        "paths": {
            "repo": str(repo),
            "runtime": runtime,
            "python": shutil.which("python"),
        },
        "git": {
            "branch": git_branch,
            "working_tree_clean": git_status == "",
            "status": git_status or "",
        },
        "filesystems": {
            "source": source_fs,
            "runtime": runtime_fs,
        },
    }


TOOLS = {
    "inspect_environment": inspect_environment,
    "inspect_workload": inspect_workload_request,
    "inspect_policy": inspect_policy_request,
}


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "inspect_environment",
            "description": (
                "Inspect the current local execution environment, including "
                "CPU, RAM, GPU, source/runtime paths, filesystem placement "
                "and Git state. Read-only."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    }
    ,
    {
        "type": "function",
        "function": {
            "name": "inspect_workload",
            "description": (
                "Inspect workload requirements explicitly stated in the "
                "current user request. Missing requirements remain unknown. "
                "Read-only and non-executing."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    }
    ,
    {
        "type": "function",
        "function": {
            "name": "inspect_policy",
            "description": (
                "Inspect explicit workload-placement policy facts in the "
                "current user request, including whether cloud is required, "
                "whether excess capacity is temporary, and whether high load "
                "is sustained. Missing facts remain unknown. Read-only."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    }
]


if __name__ == "__main__":
    print(json.dumps(inspect_environment(), indent=2))
