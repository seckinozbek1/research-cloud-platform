from __future__ import annotations
from agent.runtime_context import get_runtime_context

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_RUNTIME = Path(
    os.environ.get(
        "RESEARCH_CLOUD_RUNTIME",
        str(get_runtime_context().runtime_root),
    )
)

DEFAULT_ROOT = (
    DEFAULT_RUNTIME
    / "agent-managed"
)

ALLOWED_JOB_KINDS = {
    "managed_smoke",
}

JOB_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$"
)


def _root(
    root: Path | None = None,
) -> Path:
    return (
        root
        if root is not None
        else DEFAULT_ROOT
    ).resolve()


def _validate_job_id(
    job_id: str,
) -> None:
    if not JOB_ID_PATTERN.fullmatch(job_id):
        raise ValueError(
            "Invalid job_id. Only letters, numbers, "
            "underscore and hyphen are allowed."
        )


def workspace_path(
    job_id: str,
    root: Path | None = None,
) -> Path:
    _validate_job_id(job_id)

    base = _root(root)
    workspace = (
        base / job_id
    ).resolve()

    if workspace.parent != base:
        raise ValueError(
            "Workspace escaped sandbox root."
        )

    return workspace


def _audit(
    event: str,
    job_id: str,
    payload: dict[str, Any] | None = None,
    root: Path | None = None,
) -> None:
    base = _root(root)

    audit_dir = (
        base / "_audit"
    )

    audit_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    record = {
        "timestamp": (
            datetime.now(timezone.utc)
            .isoformat()
        ),
        "event": event,
        "job_id": job_id,
        "payload": payload or {},
    }

    with (
        audit_dir
        / "execution_events.jsonl"
    ).open("a") as f:
        f.write(
            json.dumps(record)
            + "\n"
        )


def create_workspace(
    job_id: str,
    root: Path | None = None,
) -> Path:
    workspace = workspace_path(
        job_id,
        root,
    )

    workspace.mkdir(
        parents=True,
        exist_ok=False,
    )

    for name in [
        "input",
        "scratch",
        "output",
        "logs",
    ]:
        (
            workspace / name
        ).mkdir()

    (
        workspace
        / ".agent_workspace"
    ).write_text(
        "managed-by=operations-meta-agent\n"
    )

    _audit(
        "workspace_created",
        job_id,
        root=root,
    )

    return workspace


def write_manifest(
    job_id: str,
    manifest: dict[str, Any],
    root: Path | None = None,
) -> Path:
    workspace = workspace_path(
        job_id,
        root,
    )

    if not workspace.exists():
        raise FileNotFoundError(
            "Managed workspace does not exist."
        )

    job_kind = manifest.get(
        "job_kind"
    )

    if job_kind not in ALLOWED_JOB_KINDS:
        raise ValueError(
            f"Unsupported job_kind: {job_kind}"
        )

    if "command" in manifest:
        raise ValueError(
            "Arbitrary command execution is not allowed."
        )

    path = (
        workspace
        / "manifest.json"
    )

    path.write_text(
        json.dumps(
            manifest,
            indent=2,
        )
    )

    _audit(
        "manifest_written",
        job_id,
        {
            "job_kind": job_kind,
        },
        root,
    )

    return path


def run_managed_job(
    job_id: str,
    root: Path | None = None,
) -> dict[str, Any]:
    workspace = workspace_path(
        job_id,
        root,
    )

    manifest_path = (
        workspace
        / "manifest.json"
    )

    if not manifest_path.exists():
        raise FileNotFoundError(
            "Manifest does not exist."
        )

    manifest = json.loads(
        manifest_path.read_text()
    )

    if (
        manifest.get("job_kind")
        != "managed_smoke"
    ):
        raise ValueError(
            "Unsupported managed job."
        )

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "agent.managed_worker",
            "--workspace",
            str(workspace),
        ],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    log_path = (
        workspace
        / "logs"
        / "worker.log"
    )

    log_path.write_text(
        result.stdout
        + "\n--- STDERR ---\n"
        + result.stderr
    )

    execution = {
        "exit_code": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }

    _audit(
        "job_executed",
        job_id,
        {
            "exit_code":
                result.returncode,
        },
        root,
    )

    return execution


def verify_job(
    job_id: str,
    root: Path | None = None,
) -> dict[str, Any]:
    workspace = workspace_path(
        job_id,
        root,
    )

    result_path = (
        workspace
        / "output"
        / "result.json"
    )

    if not result_path.exists():
        verified = {
            "verified": False,
            "reason":
                "result.json missing",
        }

        _audit(
            "verification_failed",
            job_id,
            verified,
            root,
        )

        return verified

    result = json.loads(
        result_path.read_text()
    )

    verified = {
        "verified":
            result.get("status")
            == "SUCCESS",
        "result": result,
    }

    _audit(
        (
            "verification_passed"
            if verified["verified"]
            else "verification_failed"
        ),
        job_id,
        verified,
        root,
    )

    return verified
