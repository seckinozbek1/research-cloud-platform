from __future__ import annotations

import os
import threading
import time
import uuid
from typing import Any

from agent.capabilities import get_capability
from agent.execute_task import execute
from agent.nl_planner import plan_natural_language_request


_PENDING: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()


def _approval_ttl() -> int:
    try:
        return max(
            30,
            int(
                os.environ.get(
                    "AGENT_APPROVAL_TTL_SECONDS",
                    "900",
                )
            ),
        )
    except ValueError:
        return 900


def clear_pending_approvals() -> None:
    with _LOCK:
        _PENDING.clear()


def analyse_user_request(
    user_request: str,
    conversation_context: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    request = user_request.strip()

    if not request:
        return {
            "status": "CLARIFICATION_REQUIRED",
            "question": "What would you like me to do?",
        }

    plan = plan_natural_language_request(
        request,
        conversation_context=conversation_context,
    )

    if plan.get("status") != "PLAN_READY":
        return plan

    approval_id = uuid.uuid4().hex

    with _LOCK:
        _PENDING[approval_id] = {
            "created_at": time.monotonic(),
            "request": request,
            "plan": plan,
            "session_id": session_id,
        }

    return {
        "status": "APPROVAL_REQUIRED",
        "approval_id": approval_id,
        "plan": plan,
    }


def execute_approved_plan(
    approval_id: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    with _LOCK:
        record = _PENDING.get(
            approval_id
        )

        if record is None:
            return {
                "status": "APPROVAL_NOT_FOUND",
                "message": (
                    "This approval is invalid, expired, "
                    "or has already been used."
                ),
            }

        expected_session = record.get(
            "session_id"
        )

        if (
            expected_session is not None
            and session_id != expected_session
        ):
            return {
                "status": "APPROVAL_SESSION_MISMATCH",
                "message": (
                    "This approval belongs to another session."
                ),
            }

        _PENDING.pop(
            approval_id,
            None,
        )

    age = (
        time.monotonic()
        - record["created_at"]
    )

    if age > _approval_ttl():
        return {
            "status": "APPROVAL_EXPIRED",
            "message": (
                "The approval expired. "
                "Please analyse the request again."
            ),
        }

    plan = record["plan"]

    capability = get_capability(
        plan["capability"]["id"]
    )

    if capability is None:
        return {
            "status": "BLOCKED",
            "message": (
                "The approved capability is no longer registered."
            ),
        }

    result = execute(
        request=capability["execution_request"],
        approved=True,
    )

    if result.get("status") == "SUCCESS":
        return {
            "status": "SUCCESS",
            "job_id": result["job_id"],
            "verification": result["verification"],
            "technical_details": result,
        }

    return {
        "status": result.get(
            "status",
            "FAILED",
        ),
        "technical_details": result,
    }
