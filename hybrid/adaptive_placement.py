from __future__ import annotations

from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[1]

LINEAGE_LOG = ROOT / "governance" / "lineage_events.jsonl"
OUTPUT = ROOT / "hybrid" / "adaptive_placement_decision.json"


# ============================================================
# LOCAL CAPACITY DISCOVERY
# ============================================================

def discover_local_capacity():
    result = {
        "cpu_threads": os.cpu_count(),
        "ram_gib": None,
        "gpu_count": 0,
        "gpu_name": None,
        "gpu_memory_gib": None,
    }

    try:
        import psutil
        result["ram_gib"] = (
            psutil.virtual_memory().total
            / (1024 ** 3)
        )
    except Exception:
        pass

    try:
        import torch

        if torch.cuda.is_available():
            result["gpu_count"] = (
                torch.cuda.device_count()
            )

            p = torch.cuda.get_device_properties(0)

            result["gpu_name"] = p.name
            result["gpu_memory_gib"] = (
                p.total_memory
                / (1024 ** 3)
            )
    except Exception:
        pass

    return result


# ============================================================
# LINEAGE-DRIVEN INPUT DISCOVERY
# ============================================================

def load_lineage():
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


def lineage_inputs(entrypoint):
    entrypoint = str(
        Path(entrypoint)
    )

    events = load_lineage()

    matching = [
        event
        for event in events
        if event.get("transformation")
        == entrypoint
    ]

    if not matching:
        return []

    latest = matching[-1]

    return [
        item["path"]
        for item in latest.get(
            "inputs",
            []
        )
    ]


# ============================================================
# RESOURCE REQUIREMENT INPUT
#
# These values are NOT embedded here.
# They come from a workload request produced by telemetry,
# scheduler, CI, user, profiler, etc.
# ============================================================

def load_request(path):
    return json.loads(
        Path(path).read_text()
    )


def capacity_check(local, req):
    constraints = []

    cpu = req.get(
        "required_cpu_threads"
    )

    ram = req.get(
        "required_ram_gib"
    )

    gpu_mem = req.get(
        "required_gpu_memory_gib"
    )

    if (
        cpu is not None
        and local["cpu_threads"] is not None
        and cpu > local["cpu_threads"]
    ):
        constraints.append(
            "insufficient_cpu"
        )

    if (
        ram is not None
        and local["ram_gib"] is not None
        and ram > local["ram_gib"]
    ):
        constraints.append(
            "insufficient_ram"
        )

    if gpu_mem is not None:

        if not local["gpu_count"]:
            constraints.append(
                "gpu_unavailable"
            )

        elif (
            local["gpu_memory_gib"]
            is not None
            and gpu_mem
            > local["gpu_memory_gib"]
        ):
            constraints.append(
                "insufficient_gpu_memory"
            )

    return (
        len(constraints) == 0,
        constraints,
    )


# ============================================================
# CANONICAL ROUTING WORKFLOW
# ============================================================

def route_workload(
    request,
    local_sufficient,
):
    cloud_required = request.get(
        "cloud_required"
    )

    sustained = request.get(
        "sustained_high_load"
    )

    temporary = request.get(
        "temporary_excess"
    )

    # --------------------------------------------------
    # Canonical workflow.
    #
    # UNKNOWN policy facts stay UNKNOWN.
    # We never invent False defaults.
    # --------------------------------------------------

    if cloud_required is None:
        return "POLICY_INPUT_REQUIRED:CLOUD_REQUIRED"

    if cloud_required is True:

        if sustained is None:
            return "POLICY_INPUT_REQUIRED:SUSTAINED_HIGH_LOAD"

        if sustained:
            return "FULL_OR_COMMITTED_CLOUD"

        return "FULL_CLOUD_ON_DEMAND_OR_SPOT"

    # cloud_required is explicitly False from here.

    if local_sufficient:
        return "LOCAL_PC"

    if temporary is None:
        return "POLICY_INPUT_REQUIRED:TEMPORARY_EXCESS"

    if temporary:
        return "CLOUD_BURST"

    if sustained is None:
        return "POLICY_INPUT_REQUIRED:SUSTAINED_HIGH_LOAD"

    return (
        "LOCAL_LINUX_SERVER_VS_COMMITTED_CLOUD"
    )


# ============================================================
# LIVE PRICE PROVIDERS
# ============================================================

def http_json(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent":
                "research-cloud-platform-finops/1"
        },
    )

    with urllib.request.urlopen(
        req,
        timeout=30,
    ) as r:
        return json.loads(
            r.read().decode()
        )


def azure_price(candidate):
    """
    Candidate fields expected:
      provider=azure
      region
      sku

    No credentials required.
    """

    region = candidate.get("region")
    sku = candidate.get("sku")

    if not region or not sku:
        return {
            "status": "UNKNOWN",
            "reason":
                "region_or_sku_missing",
        }

    filt = (
        "serviceName eq 'Virtual Machines'"
        f" and armRegionName eq '{region}'"
        f" and armSkuName eq '{sku}'"
    )

    url = (
        "https://prices.azure.com/api/retail/prices?"
        + urllib.parse.urlencode(
            {
                "$filter": filt,
                "currencyCode": "USD",
            }
        )
    )

    try:
        data = http_json(url)

        items = [
            x
            for x in data.get(
                "Items",
                []
            )
            if x.get("unitPrice")
            is not None
        ]

        if not items:
            return {
                "status": "UNKNOWN",
                "reason":
                    "no_matching_price",
            }

        prices = [
            float(x["unitPrice"])
            for x in items
        ]

        return {
            "status": "LIVE",
            "currency": "USD",
            "hourly_min": min(prices),
            "hourly_max": max(prices),
            "records": len(prices),
        }

    except Exception as e:
        return {
            "status": "UNKNOWN",
            "reason": str(e),
        }


def aws_price(candidate):
    """
    Requires configured AWS credentials and boto3.

    Candidate fields:
      provider=aws
      service_code
      filters

    Operational SKU/region facts are supplied dynamically
    by the caller, not hard-coded here.
    """

    try:
        import boto3
    except Exception:
        return {
            "status": "UNKNOWN",
            "reason":
                "boto3_not_available",
        }

    service = candidate.get(
        "service_code",
        "AmazonEC2",
    )

    filters = candidate.get(
        "filters"
    )

    if not filters:
        return {
            "status": "UNKNOWN",
            "reason":
                "aws_filters_missing",
        }

    try:
        client = boto3.client(
            "pricing",
            region_name="us-east-1",
        )

        response = client.get_products(
            ServiceCode=service,
            Filters=[
                {
                    "Type": "TERM_MATCH",
                    "Field": k,
                    "Value": str(v),
                }
                for k, v
                in filters.items()
            ],
            FormatVersion="aws_v1",
            MaxResults=100,
        )

        prices = []

        for raw in response.get(
            "PriceList",
            []
        ):
            product = json.loads(raw)

            terms = (
                product.get(
                    "terms",
                    {}
                )
                .get(
                    "OnDemand",
                    {}
                )
            )

            for term in terms.values():

                dimensions = term.get(
                    "priceDimensions",
                    {}
                )

                for dimension in (
                    dimensions.values()
                ):
                    usd = (
                        dimension.get(
                            "pricePerUnit",
                            {}
                        )
                        .get("USD")
                    )

                    if usd is not None:
                        value = float(usd)

                        if value > 0:
                            prices.append(
                                value
                            )

        if not prices:
            return {
                "status": "UNKNOWN",
                "reason":
                    "no_matching_price",
            }

        return {
            "status": "LIVE",
            "currency": "USD",
            "hourly_min": min(prices),
            "hourly_max": max(prices),
            "records": len(prices),
        }

    except Exception as e:
        return {
            "status": "UNKNOWN",
            "reason": str(e),
        }


def gcp_price(candidate):
    """
    Requires GOOGLE_CLOUD_BILLING_API_KEY.

    Candidate fields:
      provider=gcp
      service_id
      sku_filter

    Uses Google's live public Cloud Billing Catalog.
    """

    key = os.environ.get(
        "GOOGLE_CLOUD_BILLING_API_KEY"
    )

    if not key:
        return {
            "status": "UNKNOWN",
            "reason":
                "GOOGLE_CLOUD_BILLING_API_KEY_not_set",
        }

    service_id = candidate.get(
        "service_id"
    )

    sku_filter = candidate.get(
        "sku_filter"
    )

    if not service_id:
        return {
            "status": "UNKNOWN",
            "reason":
                "service_id_missing",
        }

    url = (
        "https://cloudbilling.googleapis.com/"
        f"v1/services/{service_id}/skus?"
        + urllib.parse.urlencode(
            {
                "key": key,
                "pageSize": 5000,
            }
        )
    )

    try:
        data = http_json(url)

        matched = []

        for sku in data.get(
            "skus",
            []
        ):
            desc = (
                sku.get(
                    "description",
                    ""
                )
            )

            if (
                sku_filter
                and sku_filter.lower()
                not in desc.lower()
            ):
                continue

            for info in sku.get(
                "pricingInfo",
                []
            ):

                expression = info.get(
                    "pricingExpression",
                    {}
                )

                for tier in expression.get(
                    "tieredRates",
                    []
                ):
                    price = tier.get(
                        "unitPrice",
                        {}
                    )

                    units = int(
                        price.get(
                            "units",
                            "0",
                        )
                    )

                    nanos = int(
                        price.get(
                            "nanos",
                            0,
                        )
                    )

                    value = (
                        units
                        + nanos / 1e9
                    )

                    if value > 0:
                        matched.append(
                            value
                        )

        if not matched:
            return {
                "status": "UNKNOWN",
                "reason":
                    "no_matching_price",
            }

        return {
            "status": "LIVE",
            "currency": "USD",
            "price_min": min(matched),
            "price_max": max(matched),
            "records": len(matched),
            "note":
                "Unit depends on matched SKU pricingExpression.",
        }

    except Exception as e:
        return {
            "status": "UNKNOWN",
            "reason": str(e),
        }


def live_price(candidate):
    provider = (
        candidate.get(
            "provider",
            ""
        )
        .lower()
    )

    if provider == "azure":
        return azure_price(candidate)

    if provider == "aws":
        return aws_price(candidate)

    if provider == "gcp":
        return gcp_price(candidate)

    return {
        "status": "UNKNOWN",
        "reason":
            "unsupported_provider",
    }


# ============================================================
# COST ESTIMATION
# ============================================================

def estimate_cost(price, request):
    """
    Point estimate only with actual cloud billed duration.

    Otherwise explicit band if a duration interval is supplied.

    Otherwise UNKNOWN.
    """

    if price.get("status") != "LIVE":
        return {
            "type": "UNKNOWN"
        }

    hourly_min = price.get(
        "hourly_min"
    )

    hourly_max = price.get(
        "hourly_max"
    )

    # GCP generic Catalog entries may not map cleanly
    # to hourly VM pricing without a resolved SKU unit.
    if (
        hourly_min is None
        or hourly_max is None
    ):
        return {
            "type": "UNKNOWN",
            "reason":
                "resolved_price_is_not_normalized_to_hourly",
        }

    actual_seconds = request.get(
        "actual_cloud_billed_seconds"
    )

    if actual_seconds is not None:

        point = (
            hourly_min
            * actual_seconds
            / 3600
        )

        return {
            "type": "ACTUAL_POINT_ESTIMATE",
            "usd": point,
        }

    runtime = request.get(
        "cloud_runtime_seconds"
    )

    if (
        isinstance(runtime, dict)
        and runtime.get("min")
        is not None
        and runtime.get("max")
        is not None
    ):

        low = (
            hourly_min
            * runtime["min"]
            / 3600
        )

        high = (
            hourly_max
            * runtime["max"]
            / 3600
        )

        return {
            "type":
                "BOUNDED_ESTIMATE",

            "usd_min":
                low,

            "usd_max":
                high,
        }

    return {
        "type": "UNKNOWN",
        "reason":
            "cloud_runtime_not_observed_or_bounded",
    }


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--request",
        required=True,
        help=(
            "JSON workload request. "
            "No workload facts are hard-coded."
        ),
    )

    args = parser.parse_args()

    request = load_request(
        args.request
    )

    local = discover_local_capacity()

    sufficient, constraints = (
        capacity_check(
            local,
            request,
        )
    )

    routing = route_workload(
        request,
        sufficient,
    )

    entrypoint = request.get(
        "entrypoint"
    )

    inputs = (
        lineage_inputs(entrypoint)
        if entrypoint
        else []
    )

    candidates = request.get(
        "cloud_candidates",
        []
    )

    priced_candidates = []

    for candidate in candidates:

        pricing = live_price(
            candidate
        )

        cost = estimate_cost(
            pricing,
            request,
        )

        priced_candidates.append(
            {
                "candidate":
                    candidate,

                "pricing":
                    pricing,

                "cost":
                    cost,
            }
        )

    result = {
        "request":
            request,

        "local_capacity":
            local,

        "local_capacity_sufficient":
            sufficient,

        "constraints":
            constraints,

        "routing_decision":
            routing,

        "lineage_resolved_inputs":
            inputs,

        "cloud_candidates":
            priced_candidates,
    }

    OUTPUT.write_text(
        json.dumps(
            result,
            indent=2,
        )
    )

    print(
        "=== ADAPTIVE PLACEMENT ENGINE ==="
    )

    print(
        "Routing:",
        routing,
    )

    print(
        "Local sufficient:",
        sufficient,
    )

    if constraints:
        print(
            "Constraints:",
            ", ".join(
                constraints
            ),
        )

    print()

    print(
        "Lineage inputs:",
        len(inputs),
    )

    for path in inputs:
        print(
            "  <-",
            path,
        )

    print()

    if not candidates:

        print(
            "Cloud candidates: none supplied/discovered"
        )

    for item in priced_candidates:

        c = item["candidate"]
        p = item["pricing"]
        cost = item["cost"]

        print(
            c.get(
                "provider",
                "unknown",
            ),
            c.get(
                "sku",
                c.get(
                    "sku_filter",
                    "",
                ),
            ),
        )

        print(
            "  pricing:",
            p.get(
                "status"
            ),
        )

        print(
            "  cost:",
            cost.get(
                "type"
            ),
        )

        if (
            cost.get("type")
            == "BOUNDED_ESTIMATE"
        ):
            print(
                " ",
                f"${cost['usd_min']:.6f}",
                "–",
                f"${cost['usd_max']:.6f}",
            )

        elif (
            cost.get("type")
            == "ACTUAL_POINT_ESTIMATE"
        ):
            print(
                " ",
                f"${cost['usd']:.6f}",
            )

    print()

    print(
        "Report:",
        OUTPUT,
    )


if __name__ == "__main__":
    main()
