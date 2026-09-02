from __future__ import annotations

import json
from typing import Any


def verified_facts(
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """
    Produce deterministic facts only.

    No LLM-generated interpretation is included here.
    """

    env = evidence.get("inspect_environment") or {}
    workload = evidence.get("inspect_workload") or {}
    policy = evidence.get("inspect_policy") or {}

    return {
        "environment": {
            "os": env.get("os"),
            "compute": env.get("compute"),
            "paths": env.get("paths"),
            "git": env.get("git"),
        },
        "workload": {
            "requirements": workload.get("requirements"),
            "unknowns": workload.get("unknowns"),
        },
        "policy": {
            "policy": policy.get("policy"),
            "unknowns": policy.get("unknowns"),
            "conflicts": policy.get("conflicts"),
        },
    }


def print_result(
    evidence: dict[str, Any],
    validated: dict[str, Any],
    commentary: str,
) -> None:
    print("\n=== VERIFIED FACTS ===\n")
    print(
        json.dumps(
            verified_facts(evidence),
            indent=2,
        )
    )

    print("\n=== VALIDATED DECISION ===\n")
    print(
        json.dumps(
            validated,
            indent=2,
        )
    )

    print("\n=== AGENT COMMENTARY (NON-AUTHORITATIVE) ===\n")
    print(commentary)
