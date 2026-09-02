from pathlib import Path
import json
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]

POLICIES = (
    ROOT
    / "hybrid"
    / "policies"
    / "workloads.json"
)

PROFILE_DIR = (
    ROOT
    / "hybrid"
    / "workload_profiles"
)


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python hybrid/resolve_and_place.py WORKLOAD"
        )

    workload = sys.argv[1]

    profile_path = (
        PROFILE_DIR
        / f"{workload}.json"
    )

    if not profile_path.exists():
        raise SystemExit(
            f"Missing profile: {profile_path}"
        )

    request = json.loads(
        profile_path.read_text()
    )

    policies = (
        json.loads(POLICIES.read_text())
        if POLICIES.exists()
        else {}
    )

    policy = policies.get(
        workload,
        {}
    )

    # Policy overrides UNKNOWN values only.
    for key in [
        "cloud_required",
        "temporary_excess",
        "sustained_high_load",
    ]:
        if (
            request.get(key) is None
            and key in policy
        ):
            request[key] = policy[key]

    resolved_path = (
        PROFILE_DIR
        / f"{workload}_resolved.json"
    )

    resolved_path.write_text(
        json.dumps(
            request,
            indent=2,
        )
    )

    print(
        "Resolved policy:",
        {
            k: request.get(k)
            for k in [
                "cloud_required",
                "temporary_excess",
                "sustained_high_load",
            ]
        },
    )

    subprocess.run(
        [
            sys.executable,
            "hybrid/adaptive_placement.py",
            "--request",
            str(resolved_path),
        ],
        cwd=ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
