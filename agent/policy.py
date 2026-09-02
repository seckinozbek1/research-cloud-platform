from __future__ import annotations

import re
from typing import Any


def _matches(patterns: list[str], text: str) -> bool:
    return any(
        re.search(pattern, text, flags=re.IGNORECASE)
        for pattern in patterns
    )


def _explicit_bool(
    text: str,
    true_patterns: list[str],
    false_patterns: list[str],
) -> tuple[bool | None, bool]:
    true_match = _matches(true_patterns, text)
    false_match = _matches(false_patterns, text)

    if true_match and false_match:
        return None, True

    if true_match:
        return True, False

    if false_match:
        return False, False

    return None, False


def inspect_policy_request(
    user_request: str,
) -> dict[str, Any]:
    """
    Extract explicit placement-policy facts from a user request.

    Missing or ambiguous facts remain UNKNOWN.
    No operational policy is inferred from workload size or hardware.
    """

    text = " ".join(user_request.split())

    cloud_required, cloud_conflict = _explicit_bool(
        text,
        true_patterns=[
            r"\bcloud required\b",
            r"\bmust run in (?:the )?cloud\b",
            r"\bmust use (?:the )?cloud\b",
        ],
        false_patterns=[
            r"\bcloud (?:is )?not required\b",
            r"\bmust run locally\b",
            r"\bcloud not allowed\b",
            r"\bcannot use (?:the )?cloud\b",
            r"\bno cloud\b",
        ],
    )

    temporary_excess, temporary_conflict = _explicit_bool(
        text,
        true_patterns=[
            r"\btemporary excess\b",
            r"\btemporary (?:capacity )?(?:spike|shortage|overflow)\b",
            r"\bshort[- ]term (?:spike|burst|excess)\b",
            r"\bone[- ]off\b",
            r"\bone[- ]time\b",
            r"\btransient (?:spike|burst|excess)\b",
        ],
        false_patterns=[
            r"\bnot temporary\b",
            r"\bpermanent capacity (?:need|requirement)\b",
            r"\bongoing capacity (?:need|requirement)\b",
            r"\bsustained excess\b",
        ],
    )

    sustained_high_load, sustained_conflict = _explicit_bool(
        text,
        true_patterns=[
            r"\bsustained high load\b",
            r"\bcontinuous(?:ly)? high load\b",
            r"\bongoing high load\b",
            r"\bpersistent high load\b",
            r"\blong[- ]term high load\b",
        ],
        false_patterns=[
            r"\bnot sustained\b",
            r"\bone[- ]off\b",
            r"\bone[- ]time\b",
            r"\btemporary (?:capacity )?(?:spike|overflow)\b",
            r"\bshort[- ]term (?:spike|burst)\b",
        ],
    )

    policy = {
        "cloud_required": cloud_required,
        "temporary_excess": temporary_excess,
        "sustained_high_load": sustained_high_load,
    }

    conflicts = []

    if cloud_conflict:
        conflicts.append("cloud_required")

    if temporary_conflict:
        conflicts.append("temporary_excess")

    if sustained_conflict:
        conflicts.append("sustained_high_load")

    unknowns = [
        key
        for key, value in policy.items()
        if value is None and key not in conflicts
    ]

    return {
        "source": "user_request",
        "policy": policy,
        "unknowns": unknowns,
        "conflicts": conflicts,
        "method": (
            "Conservative deterministic extraction of explicit "
            "placement-policy statements. Missing facts are not inferred."
        ),
    }
