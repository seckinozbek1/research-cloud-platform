from pathlib import Path
import subprocess
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]

STEPS = [
    "governance/build_data_catalog.py",
    "governance/enrich_data_catalog.py",
    "governance/profile_privacy.py",
    "governance/apply_privacy_profile.py",
]


def main():
    for step in STEPS:
        print()
        print("=" * 70)
        print("RUNNING:", step)
        print("=" * 70)

        subprocess.run(
            [sys.executable, step],
            cwd=PROJECT_ROOT,
            check=True,
        )

    print()
    print("=" * 70)
    print("LINEAGE STATUS")
    print("=" * 70)

    subprocess.run(
        [
            sys.executable,
            "governance/lineage.py",
            "status",
        ],
        cwd=PROJECT_ROOT,
        check=True,
    )

    print()
    print("Governance refresh complete.")


if __name__ == "__main__":
    main()
