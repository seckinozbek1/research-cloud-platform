from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


MODEL_KNOWLEDGE = "MODEL_KNOWLEDGE"
CONVERSATION = "CONVERSATION"
PROJECT_FILE = "PROJECT_FILE"
RUNTIME_OBSERVATION = "RUNTIME_OBSERVATION"
EXECUTION_RESULT = "EXECUTION_RESULT"
WEB_EVIDENCE = "WEB_EVIDENCE"
POLICY = "POLICY"


@dataclass(frozen=True)
class Evidence:
    type: str
    source: str
    role: str | None = None
    detail: str | None = None
    excerpt: str | None = None


def evidence_dict(
    evidence: Evidence,
) -> dict[str, Any]:
    return {
        key: value
        for key, value in asdict(evidence).items()
        if value is not None
    }
