from pathlib import Path
import json

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

CATALOG_PATH = (
    PROJECT_ROOT
    / "governance"
    / "data_catalog.csv"
)

POLICY_PATH = (
    PROJECT_ROOT
    / "governance"
    / "metadata_policy.json"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "governance"
    / "data_catalog_enriched.csv"
)


ARCHITECTURAL_TOKENS = {
    "raw",
    "processed",
    "cleaned",
    "curated",
    "gis",
    "artifacts",
    "artifact",
    "analytics",
    "monitoring",
    "predictions",
    "feature_store",
}


def infer_domain(path_string):
    """
    Infer the business/research domain from repository structure.

    Examples:

    data/curated/waste_gis/foo.csv
        -> waste_gis

    data/education_attendance/curated/foo.csv
        -> education_attendance

    artifacts/distributed_ml/foo.json
        -> distributed_ml
    """

    parts = Path(path_string).parts

    if not parts:
        return "unknown"

    # ----------------------------------------------
    # artifacts/<domain>/...
    # ----------------------------------------------

    if parts[0] == "artifacts":
        if len(parts) >= 2:
            return parts[1]

        return "artifacts"

    # ----------------------------------------------
    # data/...
    # ----------------------------------------------

    if parts[0] == "data":

        candidates = [
            p
            for p in parts[1:-1]
            if p not in ARCHITECTURAL_TOKENS
            and not p.startswith("curated")
            and not p.startswith("processed")
            and not p.startswith("clean")
            and not p.startswith("raw")
        ]

        # Prefer known domain-like directory names rather
        # than technical subdirectories.
        technical = {
            "attribution",
            "operations_state",
            "scheduler",
            "simulation",
            "traffic_scenarios",
            "distributed_cleaning",
            "global_resolution",
            "local_cleaning_test",
        }

        candidates = [
            p
            for p in candidates
            if p not in technical
        ]

        if candidates:
            return candidates[0]

    return "general_project_data"


def infer_purpose(domain, layer):
    """
    Purpose is derived generically instead of being stored
    file-by-file in policy.
    """

    if layer == "artifact":
        return (
            f"{domain}_reproducibility_"
            "monitoring_or_experiment"
        )

    if layer == "raw":
        return f"{domain}_source_data"

    if layer == "gis":
        return f"{domain}_geospatial_analysis"

    return f"{domain}_research_and_operations"


def main():

    catalog = pd.read_csv(
        CATALOG_PATH
    )

    policy = json.loads(
        POLICY_PATH.read_text()
    )

    defaults = policy[
        "project_defaults"
    ]

    layer_rules = policy[
        "layer_rules"
    ]

    privacy_policy = policy[
        "privacy_policy"
    ]

    structured_extensions = set(
        privacy_policy[
            "structured_extensions"
        ]
    )

    # ------------------------------------------------------
    # Dynamic metadata derivation
    # ------------------------------------------------------

    catalog["domain"] = (
        catalog["path"]
        .astype(str)
        .apply(infer_domain)
    )

    catalog["data_owner"] = (
        defaults["data_owner"]
    )

    catalog["data_steward"] = (
        defaults["data_steward"]
    )

    # Start unresolved; layer policies fill these.
    catalog["source"] = (
        "review_required"
    )

    catalog["authoritative"] = (
        "review_required"
    )

    catalog["retention_policy"] = (
        "review_required"
    )

    catalog["metadata_rule"] = (
        "none"
    )

    # ------------------------------------------------------
    # Apply generic layer policy.
    # ------------------------------------------------------

    for layer, rule in (
        layer_rules.items()
    ):

        mask = (
            catalog["data_layer"]
            == layer
        )

        if not mask.any():
            continue

        catalog.loc[
            mask,
            "source"
        ] = rule["source"]

        catalog.loc[
            mask,
            "authoritative"
        ] = rule["authoritative"]

        catalog.loc[
            mask,
            "retention_policy"
        ] = rule[
            "retention_policy"
        ]

        catalog.loc[
            mask,
            "metadata_rule"
        ] = f"layer:{layer}"

    # ------------------------------------------------------
    # Purpose derives from domain + layer automatically.
    # ------------------------------------------------------

    catalog["purpose"] = [
        infer_purpose(
            domain,
            layer,
        )
        for domain, layer
        in zip(
            catalog["domain"],
            catalog["data_layer"],
        )
    ]

    # ------------------------------------------------------
    # IMPORTANT:
    #
    # Do not guess sensitivity from directory names.
    #
    # Structured assets proceed automatically to privacy
    # scanning. Other files require review until we build
    # appropriate scanners for their format.
    # ------------------------------------------------------

    catalog["sensitivity"] = (
        "review_required"
    )

    structured_mask = (
        catalog["extension"]
        .isin(
            structured_extensions
        )
    )

    catalog.loc[
        structured_mask,
        "sensitivity"
    ] = privacy_policy[
        "default_structured_status"
    ]

    catalog["quality_status"] = (
        policy[
            "quality_policy"
        ][
            "default_status"
        ]
    )

    # Metadata completeness and privacy clearance are now
    # separate concepts.
    metadata_fields = [
        "data_owner",
        "data_steward",
        "source",
        "purpose",
        "authoritative",
        "retention_policy",
    ]

    unresolved_metadata = (
        catalog[
            metadata_fields
        ]
        .eq(
            "review_required"
        )
        .any(axis=1)
    )

    catalog[
        "metadata_complete"
    ] = (
        ~unresolved_metadata
    )

    catalog[
        "privacy_scan_required"
    ] = (
        catalog["sensitivity"]
        == "pending_privacy_scan"
    )

    # Full governance cannot be complete until privacy and
    # quality checks have also passed.
    catalog[
        "governance_complete"
    ] = False

    catalog.to_csv(
        OUTPUT_PATH,
        index=False,
    )

    print(
        "Adaptive enriched catalog:",
        OUTPUT_PATH,
    )

    print()
    print(
        "Assets:",
        len(catalog),
    )

    print(
        "Metadata complete:",
        int(
            catalog[
                "metadata_complete"
            ].sum()
        ),
    )

    print(
        "Privacy scan required:",
        int(
            catalog[
                "privacy_scan_required"
            ].sum()
        ),
    )

    print()
    print(
        "=== DOMAINS DISCOVERED ==="
    )

    print(
        catalog[
            "domain"
        ]
        .value_counts()
        .head(20)
        .to_string()
    )

    print()
    print(
        "=== LAYER POLICIES ==="
    )

    print(
        catalog[
            "metadata_rule"
        ]
        .value_counts()
        .to_string()
    )

    print()
    print(
        "=== PRIVACY STATE ==="
    )

    print(
        catalog[
            "sensitivity"
        ]
        .value_counts()
        .to_string()
    )


if __name__ == "__main__":
    main()
