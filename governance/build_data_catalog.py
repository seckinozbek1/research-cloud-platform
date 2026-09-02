from pathlib import Path
import hashlib

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

SCAN_ROOTS = [
    PROJECT_ROOT / "data",
    PROJECT_ROOT / "artifacts",
]

OUTPUT = (
    PROJECT_ROOT
    / "governance"
    / "data_catalog.csv"
)

# Files that are usually source code/config rather than data assets.
SKIP_SUFFIXES = {
    ".py",
    ".pyc",
    ".sh",
}


def sha256(path, chunk_size=1024 * 1024):
    """
    Produce a content fingerprint.

    If the file changes, the checksum changes.
    This gives us basic provenance/version evidence.
    """
    digest = hashlib.sha256()

    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            digest.update(chunk)

    return digest.hexdigest()


def data_layer(relative_path):
    """
    Infer the architectural layer from the directory path.

    This is architectural metadata, not a privacy classification.
    """
    parts = set(relative_path.parts)

    if "raw" in parts:
        return "raw"

    if "curated" in parts:
        return "curated"

    if "processed" in parts or "cleaned" in parts:
        return "processed"

    if "gis" in parts:
        return "gis"

    if relative_path.parts[0] == "artifacts":
        return "artifact"

    return "other"


def main():
    rows = []

    for scan_root in SCAN_ROOTS:
        if not scan_root.exists():
            continue

        for path in sorted(scan_root.rglob("*")):
            if not path.is_file():
                continue

            if path.suffix.lower() in SKIP_SUFFIXES:
                continue

            relative = path.relative_to(
                PROJECT_ROOT
            )

            stat = path.stat()

            rows.append(
                {
                    # ------------------------------
                    # Technical inventory
                    # ------------------------------
                    "asset_id":
                        relative.as_posix(),

                    "path":
                        relative.as_posix(),

                    "filename":
                        path.name,

                    "extension":
                        path.suffix.lower(),

                    "size_bytes":
                        stat.st_size,

                    "size_mb":
                        round(
                            stat.st_size
                            / (1024 ** 2),
                            4,
                        ),

                    "data_layer":
                        data_layer(relative),

                    "sha256":
                        sha256(path),

                    # ------------------------------
                    # Governance metadata
                    #
                    # Do NOT guess these.
                    # They will be populated by
                    # governance policy/review.
                    # ------------------------------
                    "data_owner":
                        "review_required",

                    "data_steward":
                        "review_required",

                    "source":
                        "review_required",

                    "purpose":
                        "review_required",

                    "sensitivity":
                        "review_required",

                    "authoritative":
                        "review_required",

                    "retention_policy":
                        "review_required",

                    "quality_status":
                        "not_checked",
                }
            )

    catalog = pd.DataFrame(rows)

    if catalog.empty:
        raise RuntimeError(
            "No data assets found."
        )

    catalog.to_csv(
        OUTPUT,
        index=False,
    )

    print(
        "Data catalog created:",
        OUTPUT,
    )

    print(
        "Assets catalogued:",
        len(catalog),
    )

    print()
    print("=== BY DATA LAYER ===")

    print(
        catalog[
            "data_layer"
        ]
        .value_counts()
        .to_string()
    )

    print()
    print("=== BY FILE TYPE ===")

    print(
        catalog[
            "extension"
        ]
        .value_counts()
        .head(20)
        .to_string()
    )

    print()
    print("=== TOTAL SIZE ===")

    print(
        f"{catalog['size_mb'].sum():,.2f} MB"
    )


if __name__ == "__main__":
    main()
