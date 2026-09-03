from __future__ import annotations

from pathlib import Path

import json
from typing import Any

from agent.llm_client import qwen_chat
from agent.project_inspection import (
    build_project_index,
    inspect_project,
    search_project,
)


def _compact_evidence(
    search: dict[str, Any],
) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []

    for hit in search.get(
        "hits",
        [],
    )[:8]:
        compact.append(
            {
                "path": hit.get("path"),
                "role": hit.get("role"),
                "matched_terms":
                    hit.get("matched_terms", []),
                "excerpt":
                    hit.get("excerpt", "")[:420],
            }
        )

    return compact


def _fallback_message(
    search: dict[str, Any],
) -> str:
    hits = search.get(
        "hits",
        [],
    )

    implementation = [
        hit["path"]
        for hit in hits
        if hit.get("role")
        == "implementation"
    ][:6]

    validation = [
        hit["path"]
        for hit in hits
        if hit.get("role")
        == "validation"
    ][:4]

    documentation = [
        hit["path"]
        for hit in hits
        if hit.get("role")
        == "documentation"
    ][:3]

    parts = [
        (
            "I inspected the project successfully, "
            "but the local language model could not "
            "generate the narrative answer."
        )
    ]

    if implementation:
        parts.append(
            "The strongest implementation matches are: "
            + ", ".join(
                f"`{path}`"
                for path in implementation
            )
            + "."
        )

    if validation:
        parts.append(
            "Related validation/test evidence is in: "
            + ", ".join(
                f"`{path}`"
                for path in validation
            )
            + "."
        )

    if documentation:
        parts.append(
            "Relevant documentation includes: "
            + ", ".join(
                f"`{path}`"
                for path in documentation
            )
            + "."
        )

    return " ".join(parts)


def answer_project_question(
    question: str,
    root: Path | None = None,
) -> dict[str, Any]:
    root = root.resolve() if root else None
    index = build_project_index(root=root)

    inspection = inspect_project(
        index=index,
        root=root,
    )

    search = search_project(
        question,
        index=index,
        root=root,
    )

    evidence = search.get(
        "evidence",
        [],
    )

    if not evidence:
        evidence = inspection.get(
            "evidence",
            [],
        )

    compact = _compact_evidence(
        search
    )

    project_summary = {
        "project_name":
            inspection.get("project_name"),
        "markers":
            inspection.get("markers", []),
        "likely_entrypoints":
            inspection.get(
                "likely_entrypoints",
                [],
            )[:8],
    }

    system = """
You answer questions about an actual local software project.

Use ONLY the supplied project evidence for factual claims about the project.
Do not fill gaps from general model knowledge.

Evidence roles matter:
- implementation = code that implements behavior
- validation = tests/checks that verify behavior
- configuration = configuration or declarative settings
- documentation = explanatory material

Never describe validation/test files as implementing a feature.
If asked where something is implemented, lead with implementation files.
Mention validation or documentation separately when useful.

Mention relevant file paths naturally.
If evidence is insufficient, say exactly what cannot be determined.
Do not claim you executed, benchmarked, profiled, or modified anything.

Keep the answer concise: normally 2-6 short paragraphs or bullets.
""".strip()

    payload = (
        "Question:\n"
        + question
        + "\n\nProject summary:\n"
        + json.dumps(
            project_summary,
            separators=(",", ":"),
        )
        + "\n\nEvidence:\n"
        + json.dumps(
            compact,
            separators=(",", ":"),
        )
    )

    try:
        reply = qwen_chat(
            [
                {
                    "role": "system",
                    "content": system,
                },
                {
                    "role": "user",
                    "content": payload,
                },
            ],
            max_tokens=320,
        )

        status = "OK"
        error = None

    except Exception as exc:
        reply = _fallback_message(
            search
        )

        status = "DEGRADED"
        error = {
            "type":
                type(exc).__name__,
            "message":
                str(exc),
        }

    result: dict[str, Any] = {
        "status": status,
        "message": reply,
        "inspection": inspection,
        "evidence": evidence,
        "search": search,
    }

    if error is not None:
        result["error"] = error

    return result
