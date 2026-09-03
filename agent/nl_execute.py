from __future__ import annotations

import argparse
import json
from typing import Any

from agent.capabilities import (
    get_capability,
)
from agent.execute_task import execute
from agent.nl_planner import (
    plan_natural_language_request,
)


def handle_request(
    user_request: str,
    approved: bool = False,
    job_id: str | None = None,
) -> dict[str, Any]:
    plan = plan_natural_language_request(
        user_request
    )

    if plan["status"] != "PLAN_READY":
        return plan

    capability_id = (
        plan["capability"]["id"]
    )

    capability = get_capability(
        capability_id
    )

    if capability is None:
        return {
            "status": "BLOCKED",
            "message": (
                "The requested operation is not "
                "an approved capability."
            ),
        }

    if (
        capability["approval_required"]
        and not approved
    ):
        return {
            "status": "APPROVAL_REQUIRED",
            "message": (
                "I can prepare an isolated workspace, run a harmless local "
                "test, verify the output, and record an audit trail. "
                "I will not modify your project source files or create paid "
                "cloud resources."
            ),
            "plan": plan,
        }

    result = execute(
        request=
            capability["execution_request"],
        approved=True,
        job_id=job_id,
    )

    if result.get("status") == "SUCCESS":
        return {
            "status": "SUCCESS",
            "message": (
                "The managed task completed successfully. "
                "The workspace was created, the test ran, the output was "
                "verified, and the execution was recorded in the audit log."
            ),
            "job_id": result["job_id"],
            "workspace": result["workspace"],
            "verification":
                result["verification"],
            "technical_details": result,
        }

    return {
        "status": result.get(
            "status",
            "FAILED",
        ),
        "message": (
            "The task could not be completed by the "
            "controlled execution layer."
        ),
        "technical_details": result,
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

    result = handle_request(
        user_request=args.request,
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
