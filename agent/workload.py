from __future__ import annotations

import re
from typing import Any


def _number(patterns: list[str], text: str) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return float(match.group(1))
    return None


def inspect_workload_request(user_request: str) -> dict[str, Any]:
    """
    Extract only workload requirements explicitly stated by the user.

    This is deliberately conservative. It does not infer missing requirements,
    benchmark code, execute workloads, or estimate resource needs.
    """

    text = " ".join(user_request.split())

    cpu_cores = _number(
        [
            r"(?:requires?|needs?|at least|minimum(?: of)?)\s+"
            r"(\d+(?:\.\d+)?)\s*(?:logical\s*)?(?:cpu(?:s)?|cores?)\b",

            r"(\d+(?:\.\d+)?)\s*(?:logical\s*)?(?:cpu(?:s)?|cores?)\s+"
            r"(?:required|needed|minimum)\b",
        ],
        text,
    )

    memory_gib = _number(
        [
            r"(?:requires?|needs?|at least|minimum(?: of)?)\s+"
            r"(\d+(?:\.\d+)?)\s*(?:gb|gib)\s*(?:of\s*)?(?:ram|memory)\b",

            r"(\d+(?:\.\d+)?)\s*(?:gb|gib)\s*(?:ram|memory)\s+"
            r"(?:required|needed|minimum)\b",
        ],
        text,
    )

    gpu_vram_gib = _number(
        [
            r"(?:requires?|needs?|at least|minimum(?: of)?)\s+"
            r"(\d+(?:\.\d+)?)\s*(?:gb|gib)\s*(?:of\s*)?(?:vram|gpu memory)\b",

            r"(\d+(?:\.\d+)?)\s*(?:gb|gib)\s*(?:vram|gpu memory)\s+"
            r"(?:required|needed|minimum)\b",
        ],
        text,
    )

    storage_gib = _number(
        [
            r"(?:requires?|needs?|at least|minimum(?: of)?)\s+"
            r"(\d+(?:\.\d+)?)\s*(?:gb|gib)\s*(?:of\s*)?"
            r"(?:storage|disk space)\b",

            r"(\d+(?:\.\d+)?)\s*(?:gb|gib)\s*(?:storage|disk space)\s+"
            r"(?:required|needed|minimum)\b",
        ],
        text,
    )

    gpu_required: bool | None = None

    if re.search(
        r"\b(?:gpu required|requires? (?:a )?gpu|needs? (?:a )?gpu|must use (?:a )?gpu)\b",
        text,
        flags=re.IGNORECASE,
    ):
        gpu_required = True

    if re.search(
        r"\b(?:cpu[- ]only|no gpu|gpu not allowed)\b",
        text,
        flags=re.IGNORECASE,
    ):
        gpu_required = False

    cloud_required: bool | None = None

    if re.search(
        r"\b(?:cloud required|must run in (?:the )?cloud|must use (?:the )?cloud)\b",
        text,
        flags=re.IGNORECASE,
    ):
        cloud_required = True

    if re.search(
        r"\b(?:must run locally|cloud not allowed|cannot use (?:the )?cloud|no cloud)\b",
        text,
        flags=re.IGNORECASE,
    ):
        cloud_required = False

    requirements = {
        "cpu_cores_required": cpu_cores,
        "memory_gib_required": memory_gib,
        "gpu_required": gpu_required,
        "gpu_vram_gib_required": gpu_vram_gib,
        "storage_gib_required": storage_gib,
        "cloud_required": cloud_required,
    }

    unknowns = [
        key
        for key, value in requirements.items()
        if value is None
    ]

    return {
        "source": "user_request",
        "raw_request": user_request,
        "requirements": requirements,
        "unknowns": unknowns,
        "method": (
            "Conservative deterministic extraction of explicit requirements. "
            "No missing requirement is inferred."
        ),
    }
