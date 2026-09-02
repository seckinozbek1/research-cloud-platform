from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--workspace",
        required=True,
    )
    args = parser.parse_args()

    workspace = Path(args.workspace).resolve()

    marker = workspace / ".agent_workspace"
    manifest_path = workspace / "manifest.json"

    if not marker.exists():
        raise SystemExit(
            "Refusing to execute outside a managed agent workspace."
        )

    if not manifest_path.exists():
        raise SystemExit(
            "Managed workspace has no manifest."
        )

    manifest = json.loads(
        manifest_path.read_text()
    )

    if manifest.get("job_kind") != "managed_smoke":
        raise SystemExit(
            "Unsupported managed job kind."
        )

    values = list(range(1, 1001))
    checksum = sum(x * x for x in values)

    output_dir = workspace / "output"
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    result = {
        "status": "SUCCESS",
        "job_kind": "managed_smoke",
        "records_processed": len(values),
        "checksum": checksum,
    }

    (output_dir / "result.json").write_text(
        json.dumps(
            result,
            indent=2,
        )
    )

    print(
        json.dumps(result)
    )


if __name__ == "__main__":
    main()
