from pathlib import Path

import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

SIM_DIR = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "waste_gis"
    / "simulation"
)

DAILY_PATH = SIM_DIR / "baseline_daily_summary.csv"
EVENTS_PATH = SIM_DIR / "baseline_route_events.csv"
POINTS_PATH = SIM_DIR / "baseline_point_outcomes.csv"

POINT_DEMAND_PATH = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "waste_gis"
    / "collection_point_demand.csv"
)

OUTPUT_DIR = SIM_DIR / "diagnostics"

DAILY_DIAG_PATH = OUTPUT_DIR / "daily_diagnostics.csv"
POINT_DIAG_PATH = OUTPUT_DIR / "point_diagnostics.csv"
TRUCK_DIAG_PATH = OUTPUT_DIR / "truck_diagnostics.csv"
HOTSPOT_PATH = OUTPUT_DIR / "overflow_hotspots.csv"


def safe_pct(num, den):
    return 100.0 * num / den if den else np.nan


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    daily = pd.read_csv(DAILY_PATH)
    events = pd.read_csv(EVENTS_PATH)
    points = pd.read_csv(POINTS_PATH)
    point_demand = pd.read_csv(POINT_DEMAND_PATH)

    daily["date"] = pd.to_datetime(daily["date"])
    events["date"] = pd.to_datetime(events["date"])
    points["date"] = pd.to_datetime(points["date"])

    # --------------------------------------------------------------
    # Daily diagnostics
    # --------------------------------------------------------------

    daily_diag = daily.copy()

    daily_diag["collection_rate_pct"] = (
        100.0
        * daily_diag["collected_waste_kg"]
        / daily_diag["generated_waste_kg"]
    )

    daily_diag["backlog_change_kg"] = (
        daily_diag["uncollected_waste_kg"].diff()
    )

    daily_diag["overflow_share_of_backlog_pct"] = (
        100.0
        * daily_diag["overflow_kg"]
        / daily_diag["uncollected_waste_kg"].replace(0, np.nan)
    )

    daily_diag.to_csv(
        DAILY_DIAG_PATH,
        index=False,
    )

    # --------------------------------------------------------------
    # Point-level diagnostics
    # --------------------------------------------------------------

    point_summary = (
        points
        .groupby("collection_point_id", as_index=False)
        .agg(
            overflow_days=("overflow_kg", lambda s: int((s > 0).sum())),
            total_overflow_kg=("overflow_kg", "sum"),
            peak_overflow_kg=("overflow_kg", "max"),
            mean_fill_ratio=("fill_ratio", "mean"),
            peak_fill_ratio=("fill_ratio", "max"),
            max_days_since_pickup=("days_since_pickup", "max"),
            final_fill_kg=("fill_kg", "last"),
            final_overflow_kg=("overflow_kg", "last"),
        )
    )

    point_summary = point_summary.merge(
        point_demand[
            [
                "collection_point_id",
                "total_bins",
                "small_bin_count",
                "medium_bin_count",
                "large_bin_count",
                "total_capacity_kg",
                "expected_daily_waste_kg",
                "mean_access_distance_m",
                "max_access_distance_m",
            ]
        ],
        on="collection_point_id",
        how="left",
        validate="one_to_one",
    )

    point_summary["baseline_daily_load_ratio"] = (
        point_summary["expected_daily_waste_kg"]
        / point_summary["total_capacity_kg"]
    )

    point_summary["persistent_overflow"] = (
        point_summary["overflow_days"] >= 10
    )

    point_summary.to_csv(
        POINT_DIAG_PATH,
        index=False,
    )

    # --------------------------------------------------------------
    # Truck/event diagnostics
    # --------------------------------------------------------------

    event_counts = (
        events
        .pivot_table(
            index="truck_id",
            columns="event_type",
            values="date",
            aggfunc="count",
            fill_value=0,
        )
        .reset_index()
    )

    for col in [
        "pickup",
        "unload",
        "breakdown",
        "minor_fault_delay",
        "late_start",
        "unavailable",
        "return_to_hub",
    ]:
        if col not in event_counts.columns:
            event_counts[col] = 0

    pickup_events = events[
        events["event_type"] == "pickup"
    ].copy()

    if "collected_kg" in pickup_events.columns:
        collected_by_truck = (
            pickup_events
            .groupby("truck_id", as_index=False)
            ["collected_kg"]
            .sum()
            .rename(
                columns={
                    "collected_kg": "collected_kg_total"
                }
            )
        )
    else:
        collected_by_truck = pd.DataFrame(
            columns=["truck_id", "collected_kg_total"]
        )

    truck_diag = event_counts.merge(
        collected_by_truck,
        on="truck_id",
        how="left",
    )

    truck_diag["collected_kg_total"] = (
        truck_diag["collected_kg_total"].fillna(0)
    )

    truck_diag.to_csv(
        TRUCK_DIAG_PATH,
        index=False,
    )

    # --------------------------------------------------------------
    # Hotspot ranking
    # --------------------------------------------------------------

    hotspots = point_summary.sort_values(
        [
            "total_overflow_kg",
            "overflow_days",
            "peak_fill_ratio",
        ],
        ascending=False,
    ).copy()

    total_overflow = hotspots["total_overflow_kg"].sum()

    hotspots["overflow_share_pct"] = (
        100.0
        * hotspots["total_overflow_kg"]
        / total_overflow
        if total_overflow > 0
        else 0.0
    )

    hotspots["cumulative_overflow_share_pct"] = (
        hotspots["overflow_share_pct"].cumsum()
    )

    hotspots.to_csv(
        HOTSPOT_PATH,
        index=False,
    )

    # --------------------------------------------------------------
    # Console report
    # --------------------------------------------------------------

    generated_total = daily["generated_waste_kg"].sum()
    collected_total = daily["collected_waste_kg"].sum()

    print("Baseline diagnostic report")
    print("=" * 62)

    print()
    print("SYSTEM PERFORMANCE")
    print(
        f"Collection rate          : "
        f"{safe_pct(collected_total, generated_total):.2f}%"
    )
    print(
        f"Final backlog            : "
        f"{daily.iloc[-1]['uncollected_waste_kg']/1000:,.1f} t"
    )
    print(
        f"Final overflow           : "
        f"{daily.iloc[-1]['overflow_kg']/1000:,.1f} t"
    )
    print(
        f"Peak overflow points     : "
        f"{daily['overflow_points'].max():,}"
    )

    worst_day = daily_diag.loc[
        daily_diag["collection_rate_pct"].idxmin()
    ]

    print(
        f"Worst collection day     : "
        f"{worst_day['date'].date()} "
        f"({worst_day['collection_rate_pct']:.1f}%, "
        f"{worst_day['scenario']})"
    )

    print()
    print("OVERFLOW CONCENTRATION")

    positive = hotspots[
        hotspots["total_overflow_kg"] > 0
    ]

    for n in [10, 25, 50, 100]:
        top = positive.head(n)

        share = (
            100.0
            * top["total_overflow_kg"].sum()
            / total_overflow
            if total_overflow > 0
            else 0.0
        )

        print(
            f"Top {n:3d} points          : "
            f"{share:5.1f}% of cumulative overflow"
        )

    print(
        f"Persistent overflow pts  : "
        f"{point_summary['persistent_overflow'].sum():,}"
    )

    print()
    print("CAPACITY PRESSURE")

    for threshold in [1, 2, 3]:
        print(
            f"Load ratio > {threshold}x       : "
            f"{(point_summary['baseline_daily_load_ratio'] > threshold).sum():,}"
        )

    overloaded = point_summary[
        point_summary["baseline_daily_load_ratio"] > 2
    ]

    if not overloaded.empty:
        print(
            f">2x points with overflow : "
            f"{(overloaded['overflow_days'] > 0).sum():,}"
            f"/{len(overloaded):,}"
        )

    print()
    print("DISRUPTION DAYS")

    scenario_summary = (
        daily_diag
        .groupby("scenario")
        .agg(
            days=("date", "count"),
            mean_collection_rate_pct=("collection_rate_pct", "mean"),
            mean_overflow_t=("overflow_kg", lambda x: x.mean() / 1000),
            mean_backlog_t=(
                "uncollected_waste_kg",
                lambda x: x.mean() / 1000,
            ),
        )
        .round(2)
    )

    print(scenario_summary.to_string())

    print()
    print("TRUCK OPERATIONS")
    print(
        f"Pickup events           : "
        f"{int(truck_diag['pickup'].sum()):,}"
    )
    print(
        f"Unload events           : "
        f"{int(truck_diag['unload'].sum()):,}"
    )
    print(
        f"Breakdowns              : "
        f"{int(truck_diag['breakdown'].sum()):,}"
    )
    print(
        f"Minor faults            : "
        f"{int(truck_diag['minor_fault_delay'].sum()):,}"
    )
    print(
        f"Unavailable truck-days  : "
        f"{int(truck_diag['unavailable'].sum()):,}"
    )

    print()
    print("TOP 10 OVERFLOW HOTSPOTS")

    cols = [
        "collection_point_id",
        "total_bins",
        "total_capacity_kg",
        "expected_daily_waste_kg",
        "baseline_daily_load_ratio",
        "overflow_days",
        "total_overflow_kg",
        "peak_fill_ratio",
        "mean_access_distance_m",
    ]

    print(
        hotspots.head(10)[cols]
        .round(2)
        .to_string(index=False)
    )

    print()
    print("Outputs:")
    print(f"  {DAILY_DIAG_PATH}")
    print(f"  {POINT_DIAG_PATH}")
    print(f"  {TRUCK_DIAG_PATH}")
    print(f"  {HOTSPOT_PATH}")


if __name__ == "__main__":
    main()
