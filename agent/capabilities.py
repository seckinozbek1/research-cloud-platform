from __future__ import annotations

from typing import Any


CAPABILITIES: dict[str, dict[str, Any]] = {
    "managed_smoke_test": {
        "id": "managed_smoke_test",
        "name": "Safe managed local test",
        "description": (
            "Create an isolated workspace, run a harmless local test workload, "
            "verify its output, and record an audit trail."
        ),
        "approval_required": True,

        # Internal deterministic execution contract.
        # The user does not need to know these infrastructure details.
        "execution_request": (
            "Cloud is not required. "
            "This workload requires 1 CPU core, "
            "requires 1 GB RAM, and is CPU-only."
        ),
    },
}


def public_capabilities() -> list[dict[str, str]]:
    return [
        {
            "id": item["id"],
            "name": item["name"],
            "description": item["description"],
        }
        for item in CAPABILITIES.values()
    ]


def get_capability(
    capability_id: str,
) -> dict[str, Any] | None:
    return CAPABILITIES.get(capability_id)
