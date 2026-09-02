from __future__ import annotations

import argparse
import json
import uuid
from pathlib import Path
from typing import Any

from agent.execution import (
    create_workspace,
    run_managed_job,
    verify_job,
    write_manifest,
)
from agent.policy import inspect_policy_request
from agent.tools import inspect_environment
from agent.validation import validate_placement
from agent.workload import inspect_workload_request


def build_evidence(
    request: str,
) -> dict[str, Any]:
    return {
        "inspect_environment":
            inspect_environment(),

        "inspect_workload":
            inspect_workload_request(
                request
            ),

        "inspect_policy":
            inspect_policy_request(
                request
            ),
    }


def build_execution_plan(
    request: str,
) -> dict[str, Any]:
    evidence = build_evidence(
        request
    )

    placement = validate_placement(
        evidence
    )

    executable = (
        placement.get("decision")
        == "LOCAL_PC"
    )

    return {
        "request": request,
        "placement": placement,
        "executable": executable,
        "actions": (
            [
                "create_workspace",
                "write_manifest",
                "run_managed_job",
                "verify_job",
                "record_audit_events",
            ]
            if executable
            else []
        ),
    }


def execute(
    request: str,
    approved: bool,
    job_id: str | None = None,
    root: Path | None = None,
) -> dict[str, Any]:
    plan = build_execution_plan(
        request
    )

    if not plan["executable"]:
        return {
            "status": "BLOCKED",
            "reason":
                "Validated placement does not authorize local execution.",
            "plan": plan,
        }

    if not approved:
        return {
            "status":
                "APPROVAL_REQUIRED",
            "plan": plan,
        }

    resolved_job_id = (
        job_id
        or f"job-{uuid.uuid4().hex[:12]}"
    )

    workspace = create_workspace(
        resolved_job_id,
        root,
    )

    manifest = {
        "job_id": resolved_job_id,
        "job_kind": "managed_smoke",
        "original_request": request,
        "validated_placement":
            plan["placement"]["decision"],
    }

    write_manifest(
        resolved_job_id,
        manifest,
        root,
    )

    execution = run_managed_job(
        resolved_job_id,
        root,
    )

    verification = verify_job(
        resolved_job_id,
        root,
    )

    return {
        "status": (
            "SUCCESS"
            if (
                execution["exit_code"] == 0
                and verification["verified"]
            )
            else "FAILED"
        ),
        "job_id": resolved_job_id,
        "workspace": str(workspace),
        "plan": plan,
        "execution": execution,
        "verification": verification,
    }


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "request",
    )

    parser.add_argument(
        "--approve",
        action="store_true",
    )

    parser.add_argument(
        "--job-id",
    )

    args = parser.parse_args()

    result = execute(
        request=args.request,
        approved=args.approve,
        job_id=args.job_id,
    )

    print(
        json.dumps(
            result,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
