from pathlib import Path

import geopandas as gpd
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

BINS_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_existing_bins.geojson"
)

CATCHMENTS_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_bin_catchments.geojson"
)

POINTS_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_collection_points.geojson"
)

POINT_DEMAND_PATH = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "waste_gis"
    / "collection_point_demand.csv"
)


def main():
    bins = gpd.read_file(BINS_PATH)
    catchments = gpd.read_file(CATCHMENTS_PATH)

    # Same snapped road node = same physical collection point.
    grouped = (
        bins
        .groupby("road_node_id", as_index=False)
        .agg(
            small_bin_count=(
                "bin_type",
                lambda x: (x == "small_bin").sum(),
            ),
            medium_bin_count=(
                "bin_type",
                lambda x: (x == "medium_bin").sum(),
            ),
            large_bin_count=(
                "bin_type",
                lambda x: (x == "large_bin").sum(),
            ),
            total_bins=("bin_id", "count"),
            total_capacity_kg=("capacity_kg", "sum"),
            total_service_seconds=(
                "pickup_service_seconds",
                "sum",
            ),
            mean_pickups_per_week=(
                "current_pickups_per_week",
                "mean",
            ),
        )
    )

    # Recover one geometry per road node.
    geometry_lookup = (
        bins
        .drop_duplicates("road_node_id")
        .set_index("road_node_id")["geometry"]
    )

    grouped["geometry"] = (
        grouped["road_node_id"]
        .map(geometry_lookup)
    )

    grouped["collection_point_id"] = [
        f"KSK-CP{i:04d}"
        for i in range(1, len(grouped) + 1)
    ]

    points = gpd.GeoDataFrame(
        grouped,
        geometry="geometry",
        crs=bins.crs,
    )

    # Map each original bin to its collection point.
    bin_to_point = (
        bins[
            ["bin_id", "road_node_id"]
        ]
        .merge(
            points[
                ["road_node_id", "collection_point_id"]
            ],
            on="road_node_id",
            how="left",
        )
    )

    # Catchments are currently assigned to bins.
    # Convert those assignments to collection points.
    catchments = catchments.merge(
        bin_to_point[
            ["bin_id", "collection_point_id"]
        ],
        on="bin_id",
        how="left",
    )

    active = catchments[
        (catchments["population_2025"] > 0)
        | (catchments["activity_score"] > 0)
    ].copy()

    point_demand = (
        active
        .groupby(
            "collection_point_id",
            as_index=False,
        )
        .agg(
            demand_cells=("zone_id", "count"),
            population_served=("population_2025", "sum"),
            activity_score_served=("activity_score", "sum"),
            expected_daily_waste_kg=(
                "expected_daily_waste_kg",
                "sum",
            ),
            mean_access_distance_m=(
                "access_distance_m",
                "mean",
            ),
            max_access_distance_m=(
                "access_distance_m",
                "max",
            ),
        )
    )

    point_demand = (
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
        ]
        .merge(
            point_demand,
            on="collection_point_id",
            how="left",
        )
    )

    fill_cols = [
        "demand_cells",
        "population_served",
        "activity_score_served",
        "expected_daily_waste_kg",
        "mean_access_distance_m",
        "max_access_distance_m",
    ]

    point_demand[fill_cols] = (
        point_demand[fill_cols]
        .fillna(0)
    )

    points.to_file(
        POINTS_PATH,
        driver="GeoJSON",
    )

    POINT_DEMAND_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    point_demand.to_csv(
        POINT_DEMAND_PATH,
        index=False,
    )

    print("Collection-point layer created.")
    print(f"Original bins              : {len(bins):,}")
    print(f"Unique collection points   : {len(points):,}")
    print(
        f"Multi-bin points           : "
        f"{(points['total_bins'] > 1).sum():,}"
    )
    print(
        f"Max bins at one point      : "
        f"{points['total_bins'].max():,}"
    )
    print(
        f"Points serving active cells: "
        f"{(point_demand['demand_cells'] > 0).sum():,}"
    )
    print(
        f"Points with zero demand    : "
        f"{(point_demand['demand_cells'] == 0).sum():,}"
    )
    print()
    print(
        f"Active-cell mean access    : "
        f"{active['access_distance_m'].mean():.1f} m"
    )
    print(
        f"Active-cell median access  : "
        f"{active['access_distance_m'].median():.1f} m"
    )
    print(
        f"Active-cell p95 access     : "
        f"{active['access_distance_m'].quantile(.95):.1f} m"
    )
    print()
    print(f"Points output              : {POINTS_PATH}")
    print(f"Demand output              : {POINT_DEMAND_PATH}")


if __name__ == "__main__":
    main()
