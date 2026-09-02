from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import uuid


PROJECT_ROOT = Path(__file__).resolve().parents[1]

EVENT_LOG = (
    PROJECT_ROOT
    / "governance"
    / "lineage_events.jsonl"
)


def repo_relative(path: str | Path) -> str:
    """
    Convert a path to a stable repository-relative path.
    """

    p = Path(path)

    if not p.is_absolute():
        p = PROJECT_ROOT / p

    try:
        return str(
            p.resolve().relative_to(
                PROJECT_ROOT.resolve()
            )
        )
    except ValueError:
        return str(
            p.resolve()
        )


def sha256_file(path: str | Path) -> str | None:
    """
    Compute SHA-256 without loading the whole file into RAM.
    """

    p = Path(path)

    if not p.is_absolute():
        p = PROJECT_ROOT / p

    if not p.exists():
        return None

    if not p.is_file():
        return None

    digest = hashlib.sha256()

    with p.open("rb") as f:
        for chunk in iter(
            lambda: f.read(1024 * 1024),
            b"",
        ):
            digest.update(chunk)

    return digest.hexdigest()


def git_metadata() -> dict:
    """
    Record source-code version and whether local changes
    existed when the pipeline ran.
    """

    try:
        commit = subprocess.check_output(
            [
                "git",
                "rev-parse",
                "HEAD",
            ],
            cwd=PROJECT_ROOT,
            text=True,
        ).strip()

    except Exception:
        commit = None

    try:
        status = subprocess.check_output(
            [
                "git",
                "status",
                "--porcelain",
            ],
            cwd=PROJECT_ROOT,
            text=True,
        )

        dirty = bool(
            status.strip()
        )

    except Exception:
        dirty = None

    return {
        "git_commit": commit,
        "git_dirty": dirty,
    }


def asset_record(path: str | Path) -> dict:
    """
    Create the immutable file-state record used in a
    lineage event.
    """

    relative = repo_relative(
        path
    )

    absolute = (
        PROJECT_ROOT
        / relative
    )

    return {
        "path": relative,
        "exists": absolute.exists(),
        "sha256": sha256_file(
            absolute
        ),
        "size_bytes": (
            absolute.stat().st_size
            if absolute.exists()
            and absolute.is_file()
            else None
        ),
    }


def record_lineage(
    *,
    inputs: list[str | Path],
    outputs: list[str | Path],
    transformation: str | Path,
    metadata: dict | None = None,
) -> dict:
    """
    Append one pipeline execution event.

    The dependency declaration is explicit, while runtime
    provenance is collected automatically.
    """

    EVENT_LOG.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    git = git_metadata()

    event = {
        "run_id": str(
            uuid.uuid4()
        ),

        "timestamp_utc": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),

        "transformation": (
            repo_relative(
                transformation
            )
        ),

        "inputs": [
            asset_record(path)
            for path in inputs
        ],

        "outputs": [
            asset_record(path)
            for path in outputs
        ],

        **git,

        "metadata": (
            metadata
            or {}
        ),
    }

    with EVENT_LOG.open(
        "a",
        encoding="utf-8",
    ) as f:
        f.write(
            json.dumps(
                event,
                ensure_ascii=False,
            )
            + "\n"
        )

    return event


def load_events() -> list[dict]:
    if not EVENT_LOG.exists():
        return []

    events = []

    with EVENT_LOG.open(
        encoding="utf-8"
    ) as f:

        for line in f:
            line = line.strip()

            if not line:
                continue

            events.append(
                json.loads(
                    line
                )
            )

    return events


def latest_output_events(
    events: list[dict],
) -> dict[str, dict]:
    """
    Find the latest lineage-producing run for each output.
    """

    latest = {}

    for event in events:
        for output in event[
            "outputs"
        ]:

            latest[
                output["path"]
            ] = event

    return latest


def check_staleness() -> list[dict]:
    """
    Compare recorded input hashes with their current hashes.

    If an upstream file changed after an output was produced,
    that output becomes potentially stale.
    """

    events = load_events()

    latest = latest_output_events(
        events
    )

    rows = []

    for output_path, event in (
        latest.items()
    ):

        changed_inputs = []

        for recorded_input in event[
            "inputs"
        ]:

            path = recorded_input[
                "path"
            ]

            current_hash = sha256_file(
                PROJECT_ROOT
                / path
            )

            if (
                current_hash
                != recorded_input[
                    "sha256"
                ]
            ):
                changed_inputs.append(
                    path
                )

        output_exists = (
            PROJECT_ROOT
            / output_path
        ).exists()

        rows.append(
            {
                "output":
                    output_path,

                "status": (
                    "potentially_stale"
                    if changed_inputs
                    else (
                        "current"
                        if output_exists
                        else "missing"
                    )
                ),

                "changed_inputs":
                    changed_inputs,

                "run_id":
                    event[
                        "run_id"
                    ],

                "transformation":
                    event[
                        "transformation"
                    ],
            }
        )

    return rows


def show_events():
    events = load_events()

    print(
        "Lineage events:",
        len(events),
    )

    for event in events[-10:]:

        print()
        print(
            "RUN:",
            event["run_id"],
        )

        print(
            "Transformation:",
            event[
                "transformation"
            ],
        )

        print(
            "Inputs:"
        )

        for item in event[
            "inputs"
        ]:
            print(
                "  <-",
                item["path"],
            )

        print(
            "Outputs:"
        )

        for item in event[
            "outputs"
        ]:
            print(
                "  ->",
                item["path"],
            )


def show_status():
    rows = check_staleness()

    if not rows:
        print(
            "No lineage-tracked outputs."
        )
        return

    print(
        "=== LINEAGE STATUS ==="
    )

    for row in rows:

        print()
        print(
            row["status"].upper(),
            row["output"],
        )

        print(
            "  transformation:",
            row[
                "transformation"
            ],
        )

        if row[
            "changed_inputs"
        ]:
            print(
                "  changed inputs:"
            )

            for path in row[
                "changed_inputs"
            ]:
                print(
                    "   -",
                    path,
                )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "command",
        choices=[
            "events",
            "status",
        ],
    )

    args = parser.parse_args()

    if args.command == "events":
        show_events()

    elif args.command == "status":
        show_status()


if __name__ == "__main__":
    main()
