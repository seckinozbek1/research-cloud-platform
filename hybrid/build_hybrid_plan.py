from __future__ import annotations

from pathlib import Path
import argparse
import json
import subprocess
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]

LINEAGE_LOG = (
    ROOT
    / "governance"
    / "lineage_events.jsonl"
)

CATALOG = (
    ROOT
    / "governance"
    / "data_catalog_governed.csv"
)

OUT = (
    ROOT
    / "hybrid"
    / "hybrid_execution_plan.json"
)


def load_events():
    if not LINEAGE_LOG.exists():
        return []

    events = []

    with LINEAGE_LOG.open() as f:
        for line in f:
            line = line.strip()

            if line:
                events.append(
                    json.loads(line)
                )

    return events


def latest_inputs(entrypoint):
    matches = [
        event
        for event in load_events()
        if event.get("transformation")
        == entrypoint
    ]

    if not matches:
        return []

    return [
        item["path"]
        for item in matches[-1].get(
            "inputs",
            []
        )
    ]


def transfer_policy(row):
    sensitivity = row[
        "sensitivity"
    ]

    if sensitivity == "restricted_review_required":
        return "BLOCK"

    if sensitivity == "potentially_personal":
        return "CONTROLLED_TRANSFER"

    if sensitivity == "internal_non_personal":
        return "ALLOW"

    return "REVIEW"


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--request",
        required=True,
    )

    args = parser.parse_args()

    request = json.loads(
        Path(args.request).read_text()
    )

    entrypoint = request.get(
        "entrypoint"
    )

    routing = request.get(
        "routing_decision"
    )

    # If the supplied file is a workload request/profile,
    # compute placement for THIS request rather than reading
    # a stale global placement result from another workload.
    if routing is None:
        placement_script = (
            ROOT
            / "hybrid"
            / "adaptive_placement.py"
        )

        subprocess.run(
            [
                sys.executable,
                str(placement_script),
                "--request",
                str(Path(args.request).resolve()),
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        placement_path = (
            ROOT
            / "hybrid"
            / "adaptive_placement_decision.json"
        )

        placement = json.loads(
            placement_path.read_text()
        )

        routing = placement.get(
            "routing_decision"
        )

    inputs = latest_inputs(
        entrypoint
    )

    catalog = pd.read_csv(
        CATALOG
    )

    transfer_assets = []

    overall = "ALLOW"

    priority = {
        "ALLOW": 0,
        "CONTROLLED_TRANSFER": 1,
        "REVIEW": 2,
        "BLOCK": 3,
    }

    for path in inputs:

        rows = catalog[
            catalog["path"] == path
        ]

        if rows.empty:
            decision = "BLOCK"

            transfer_assets.append(
                {
                    "path": path,
                    "decision": decision,
                    "reason":
                        "not_in_governance_catalog",
                }
            )

        else:
            row = rows.iloc[0]

            decision = transfer_policy(
                row
            )

            transfer_assets.append(
                {
                    "path":
                        path,

                    "decision":
                        decision,

                    "sensitivity":
                        row["sensitivity"],

                    "privacy_action":
                        row["privacy_action"],

                    "size_bytes":
                        int(
                            row["size_bytes"]
                        ),
                }
            )

        if (
            priority[decision]
            > priority[overall]
        ):
            overall = decision

    cloud_used = routing in {
        "CLOUD_BURST",
        "FULL_CLOUD_ON_DEMAND_OR_SPOT",
        "FULL_OR_COMMITTED_CLOUD",
    }

    if routing == "LOCAL_LINUX_SERVER_VS_COMMITTED_CLOUD":
        cloud_used = None

    # ------------------------------------------------------
    # Provider-independent hybrid controls.
    # ------------------------------------------------------

    network_policy = {
        "default":
            "TLS_OVER_PUBLIC_PROVIDER_ENDPOINT",

        "private_connectivity_when":
            [
                "restricted_network_requirement",
                "private_on_prem_service_dependency",
                "policy_requires_private_transport",
            ],

        "provider_mapping": {
            "aws":
                "VPC + Site-to-Site VPN / PrivateLink",

            "gcp":
                "VPC + Cloud VPN / Private Service Connect",

            "azure":
                "VNet + VPN Gateway / Private Link",
        },
    }

    identity_policy = {
        "principle":
            "federated_short_lived_identity",

        "avoid":
            "long_lived_static_cloud_credentials",

        "provider_mapping": {
            "aws":
                "IAM roles / workload identity federation",

            "gcp":
                "IAM + Workload Identity Federation",

            "azure":
                "Microsoft Entra ID + managed/workload identity",
        },
    }

    portability_policy = {
        "application":
            "containerized_provider_neutral_workload",

        "infrastructure":
            "provider_adapter_or_terraform_layer",

        "data_interface":
            "object_storage_abstraction",

        "observability":
            "OpenTelemetry_compatible",

        "rule":
            (
                "Provider-specific services may be used only "
                "when their benefit exceeds portability cost."
            ),
    }

    lifecycle = {
        "transfer":
            (
                "minimum_lineage_resolved_inputs_only"
            ),

        "return":
            [
                "artifacts",
                "metrics",
                "logs",
                "lineage_metadata",
            ],

        "cleanup":
            [
                "destroy_temporary_compute",
                "remove_temporary_cloud_data_when_policy_allows",
                "verify_no_idle_resources",
            ],
    }

    result = {
        "routing_decision":
            routing,

        "cloud_used":
            cloud_used,

        "entrypoint":
            entrypoint,

        "lineage_resolved_inputs":
            transfer_assets,

        "overall_transfer_policy":
            overall,

        "network_policy":
            network_policy,

        "identity_policy":
            identity_policy,

        "portability_policy":
            portability_policy,

        "lifecycle":
            lifecycle,
    }

    OUT.write_text(
        json.dumps(
            result,
            indent=2,
        )
    )

    print(
        "=== HYBRID EXECUTION PLAN ==="
    )

    print(
        "Routing:",
        routing,
    )

    print(
        "Cloud used:",
        cloud_used,
    )

    print(
        "Transfer policy:",
        overall,
    )

    print()

    print(
        "Minimum lineage inputs:"
    )

    for item in transfer_assets:
        print(
            f"  {item['decision']:20} "
            f"{item['path']}"
        )

    print()

    print(
        "Identity:",
        identity_policy[
            "principle"
        ],
    )

    print(
        "Networking:",
        network_policy[
            "default"
        ],
    )

    print(
        "Portability:",
        portability_policy[
            "application"
        ],
    )

    print()

    print(
        "Report:",
        OUT,
    )


if __name__ == "__main__":
    main()
