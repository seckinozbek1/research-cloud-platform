from __future__ import annotations

from pathlib import Path
import argparse
import json
import math
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]

OUT = (
    ROOT
    / "hybrid"
    / "local_server_vs_cloud.json"
)


def load_json(path):
    return json.loads(
        Path(path).read_text()
    )


def monthly_local_server_cost(econ):
    """
    Required inputs are external facts.
    Nothing is invented here.
    """

    purchase = econ.get(
        "hardware_purchase_price"
    )

    life_months = econ.get(
        "useful_life_months"
    )

    power_watts = econ.get(
        "average_power_watts"
    )

    electricity = econ.get(
        "electricity_price_per_kwh"
    )

    maintenance = econ.get(
        "monthly_maintenance_cost"
    )

    missing = []

    for name, value in [
        (
            "hardware_purchase_price",
            purchase,
        ),
        (
            "useful_life_months",
            life_months,
        ),
        (
            "average_power_watts",
            power_watts,
        ),
        (
            "electricity_price_per_kwh",
            electricity,
        ),
        (
            "monthly_maintenance_cost",
            maintenance,
        ),
    ]:
        if value is None:
            missing.append(name)

    if missing:
        return {
            "status": "UNKNOWN",
            "missing": missing,
        }

    amortization = (
        purchase
        / life_months
    )

    monthly_energy_kwh = (
        power_watts
        / 1000
        * 24
        * 30.4375
    )

    energy_cost = (
        monthly_energy_kwh
        * electricity
    )

    total = (
        amortization
        + energy_cost
        + maintenance
    )

    return {
        "status": "RESOLVED",
        "monthly_cost": total,
        "components": {
            "amortization":
                amortization,
            "energy":
                energy_cost,
            "maintenance":
                maintenance,
        },
    }


def cloud_monthly_cost(cloud):
    """
    Cloud rate must already be live-resolved by the pricing
    adapter or supplied from actual billing data.
    """

    hourly_min = cloud.get(
        "hourly_usd_min"
    )

    hourly_max = cloud.get(
        "hourly_usd_max"
    )

    utilization_hours = cloud.get(
        "monthly_usage_hours"
    )

    if utilization_hours is None:
        return {
            "status": "UNKNOWN",
            "reason":
                "monthly_usage_hours_missing",
        }

    if (
        hourly_min is None
        or hourly_max is None
    ):
        return {
            "status": "UNKNOWN",
            "reason":
                "cloud_hourly_price_unresolved",
        }

    return {
        "status": "RESOLVED",
        "monthly_cost_min":
            hourly_min
            * utilization_hours,
        "monthly_cost_max":
            hourly_max
            * utilization_hours,
    }


def break_even_hours(
    local_monthly,
    cloud_hourly_min,
    cloud_hourly_max,
):
    if (
        local_monthly is None
        or cloud_hourly_min is None
        or cloud_hourly_max is None
        or cloud_hourly_min <= 0
        or cloud_hourly_max <= 0
    ):
        return None

    return {
        "hours_min":
            local_monthly
            / cloud_hourly_max,

        "hours_max":
            local_monthly
            / cloud_hourly_min,
    }


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--local-economics",
        required=True,
        help=(
            "JSON containing current hardware/electricity/"
            "maintenance facts."
        ),
    )

    parser.add_argument(
        "--cloud-economics",
        required=True,
        help=(
            "JSON containing live-resolved cloud price band "
            "and monthly usage hours."
        ),
    )

    args = parser.parse_args()

    local_input = load_json(
        args.local_economics
    )

    cloud_input = load_json(
        args.cloud_economics
    )

    local = monthly_local_server_cost(
        local_input
    )

    cloud = cloud_monthly_cost(
        cloud_input
    )

    decision = "UNKNOWN"
    reason = None
    break_even = None

    if (
        local["status"] == "RESOLVED"
        and cloud["status"] == "RESOLVED"
    ):
        local_cost = local[
            "monthly_cost"
        ]

        cloud_low = cloud[
            "monthly_cost_min"
        ]

        cloud_high = cloud[
            "monthly_cost_max"
        ]

        if local_cost < cloud_low:
            decision = (
                "DEDICATED_LOCAL_LINUX_SERVER"
            )

        elif local_cost > cloud_high:
            decision = "CLOUD"

        else:
            decision = (
                "ECONOMICALLY_AMBIGUOUS"
            )

        break_even = break_even_hours(
            local_cost,
            cloud_input.get(
                "hourly_usd_min"
            ),
            cloud_input.get(
                "hourly_usd_max"
            ),
        )

    else:
        reason = {
            "local":
                local,
            "cloud":
                cloud,
        }

    result = {
        "local_server":
            local,

        "cloud":
            cloud,

        "break_even_monthly_usage_hours":
            break_even,

        "decision":
            decision,

        "reason":
            reason,
    }

    OUT.write_text(
        json.dumps(
            result,
            indent=2,
        )
    )

    print(
        "=== LOCAL SERVER VS CLOUD ==="
    )

    print(
        "Local:",
        local["status"],
    )

    print(
        "Cloud:",
        cloud["status"],
    )

    if (
        local["status"]
        == "RESOLVED"
    ):
        print(
            "Local monthly:",
            f"{local['monthly_cost']:.4f}",
        )

    if (
        cloud["status"]
        == "RESOLVED"
    ):
        print(
            "Cloud monthly:",
            f"{cloud['monthly_cost_min']:.4f}",
            "–",
            f"{cloud['monthly_cost_max']:.4f}",
        )

    if break_even:
        print(
            "Break-even usage:",
            f"{break_even['hours_min']:.2f}",
            "–",
            f"{break_even['hours_max']:.2f}",
            "hours/month",
        )

    print(
        "DECISION:",
        decision,
    )

    print(
        "Report:",
        OUT,
    )


if __name__ == "__main__":
    main()
