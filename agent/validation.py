from __future__ import annotations

from typing import Any

from agent.placement import resolve_agent_placement


def validate_placement(
    evidence: dict[str, Any],
) -> dict[str, Any]:
    """
    Operational placement authority.

    LLM prose is never treated as a placement decision.
    """
    return resolve_agent_placement(evidence)
