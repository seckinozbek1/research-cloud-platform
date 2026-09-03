from __future__ import annotations

from typing import Any


def render_execution_result(
    result: dict[str, Any],
) -> str:
    status = result.get(
        "status",
        "UNKNOWN",
    )

    if status != "SUCCESS":
        details = result.get(
            "technical_details",
            result,
        )

        execution = details.get(
            "execution",
            {},
        )

        code = execution.get(
            "exit_code"
        )

        if code is not None:
            return (
                "The operation did not complete successfully. "
                f"The managed worker exited with code {code}. "
                "I do not have a verified successful output."
            )

        return (
            "The operation did not complete successfully, "
            "and I do not have a verified successful output."
        )

    verification = result.get(
        "verification",
        {},
    )

    verified = bool(
        verification.get(
            "verified"
        )
    )

    payload = verification.get(
        "result",
        {},
    )

    parts = [
        "The operation completed successfully."
    ]

    if verified:
        parts.append(
            "I verified the resulting output."
        )
    else:
        parts.append(
            "The operation finished, but the output "
            "has not been independently verified."
        )

    records = payload.get(
        "records_processed"
    )

    if records is not None:
        parts.append(
            f"It processed {records:,} records."
        )

    details = result.get(
        "technical_details",
        result,
    )

    execution = details.get(
        "execution",
        {},
    )

    if execution.get("exit_code") == 0:
        parts.append(
            "The managed worker exited cleanly with code 0."
        )

    parts.append(
        "The run used the controlled managed-execution path."
    )

    return " ".join(parts)


def render_project_inspection(
    inspection: dict[str, Any],
) -> str:
    if inspection.get("status") != "OK":
        return (
            "I could not inspect the active project safely."
        )

    markers = inspection.get(
        "markers",
        [],
    )

    entrypoints = inspection.get(
        "likely_entrypoints",
        [],
    )

    parts = [
        (
            f"I inspected {inspection.get('files_scanned', 0)} "
            "eligible text/configuration files in the active project."
        )
    ]

    if markers:
        parts.append(
            "I found these project markers: "
            + ", ".join(markers)
            + "."
        )

    if entrypoints:
        parts.append(
            "Likely operational entry points include "
            + ", ".join(entrypoints[:6])
            + "."
        )

    return " ".join(parts)
