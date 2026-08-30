from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

BINS_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_existing_bins.geojson"
)

POINTS_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_collection_points.geojson"
)

BIN_DAILY_PATH = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "waste_gis"
    / "bin_daily_generated_waste.csv"
)

HUB_BIN_MATRIX_PATH = (
    PROJECT_ROOT
    / "data"
    / "gis"
    / "traffic_scenarios"
    / "hub_bin_travel_matrix.csv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "waste_gis"
    / "scheduler"
)

POINT_DAILY_PATH = OUTPUT_DIR / "collection_point_daily_waste.csv"

HUB_POINT_MATRIX_PATH = OUTPUT_DIR / "hub_collection_point_travel_matrix.csv"


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    bins = gpd.read_file(BINS_PATH)
    points = gpd.read_file(POINTS_PATH)

    daily = pd.read_csv(BIN_DAILY_PATH)
    travel = pd.read_csv(HUB_BIN_MATRIX_PATH)

    # --------------------------------------------------------------
    # Bin -> collection-point mapping
    # --------------------------------------------------------------

    mapping = bins[
        ["bin_id", "road_node_id"]
    ].merge(
        points[
            [
                "collection_point_id",
                "road_node_id",
                "total_bins",
                "total_capacity_kg",
                "total_service_seconds",
                "mean_pickups_per_week",
            ]
        ],
        on="road_node_id",
        how="left",
        validate="many_to_one",
    )

    if mapping["collection_point_id"].isna().any():
        raise RuntimeError(
            "Some bins could not be mapped to collection points."
        )

    # --------------------------------------------------------------
    # Daily generated waste at collection-point level
    # --------------------------------------------------------------

    daily_point = daily.merge(
        mapping[
            ["bin_id", "collection_point_id"]
        ],
        on="bin_id",
        how="left",
        validate="many_to_one",
    )

    daily_point = (
        daily_point
        .groupby(
            ["date", "collection_point_id"],
            as_index=False,
        )
        .agg(
            generated_waste_kg=("generated_waste_kg", "sum"),
            temperature_c=("temperature_c", "first"),
            rain_mm=("rain_mm", "first"),
            weekend=("weekend", "first"),
        )
    )

    daily_point = daily_point.merge(
        points[
            [
                "collection_point_id",
                "road_node_id",
                "small_bin_count",
                "medium_bin_count",
                "large_bin_count",
                "total_bins",
                "total_capacity_kg",
                "total_service_seconds",
                "mean_pickups_per_week",
            ]
        ],
        on="collection_point_id",
        how="left",
        validate="many_to_one",
    )

    daily_point.to_csv(
        POINT_DAILY_PATH,
        index=False,
    )

    # --------------------------------------------------------------
    # Hub -> collection-point travel matrix
    #
    # Bins at one collection point share a road node, so one
    # representative bin is sufficient.
    # --------------------------------------------------------------

    representative_bins = (
        mapping
        .sort_values("bin_id")
        .drop_duplicates("collection_point_id")
        [
            ["collection_point_id", "bin_id"]
        ]
    )

    point_travel = travel.merge(
        representative_bins,
        on="bin_id",
        how="inner",
        validate="many_to_one",
    )

    point_travel = point_travel[
        [
            "hub_id",
            "collection_point_id",
            "truck_type",
            "scenario",
            "hub_to_bin_minutes",
            "bin_to_hub_minutes",
            "round_trip_minutes",
        ]
    ].rename(
        columns={
            "hub_to_bin_minutes": "hub_to_point_minutes",
            "bin_to_hub_minutes": "point_to_hub_minutes",
        }
    )

    point_travel.to_csv(
        HUB_POINT_MATRIX_PATH,
        index=False,
    )

    expected_daily_rows = (
        daily_point["date"].nunique()
        * len(points)
    )

    expected_matrix_rows = (
        len(points)
        * 3  # hubs
        * 2  # truck types
        * 3  # scenarios
    )

    print("Scheduler inputs prepared.")
    print(f"Collection points      : {len(points):,}")
    print(
        f"Operational dates      : "
        f"{daily_point['date'].nunique():,}"
    )
    print(
        f"Point-day rows         : "
        f"{len(daily_point):,} "
        f"(expected {expected_daily_rows:,})"
    )
    print(
        f"Hub-point matrix rows  : "
        f"{len(point_travel):,} "
        f"(expected {expected_matrix_rows:,})"
    )

    finite = np.isfinite(
        point_travel["round_trip_minutes"]
    )

    print(
        f"Reachable matrix rows  : "
        f"{finite.sum():,}/{len(point_travel):,}"
    )

    print(
        f"Mean generated waste   : "
        f"{daily_point.groupby('date')['generated_waste_kg'].sum().mean():,.0f} "
        f"kg/day"
    )

    print()
    print(f"Daily point demand     : {POINT_DAILY_PATH}")
    print(f"Hub-point matrix       : {HUB_POINT_MATRIX_PATH}")


if __name__ == "__main__":
    main()
