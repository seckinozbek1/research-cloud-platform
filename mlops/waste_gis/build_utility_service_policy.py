from pathlib import Path

import geopandas as gpd
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CATCHMENTS_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_bin_catchments.geojson"
)

BINS_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_existing_bins.geojson"
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

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "waste_gis"
    / "scheduler"
    / "utility_service_policy.csv"
)


def main():
    catchments = gpd.read_file(CATCHMENTS_PATH)
    bins = gpd.read_file(BINS_PATH)
    points = gpd.read_file(POINTS_PATH)
    point_demand = pd.read_csv(POINT_DEMAND_PATH)

    # bin -> collection point
    mapping = (
        bins[
            ["bin_id", "road_node_id"]
        ]
        .merge(
            points[
                ["collection_point_id", "road_node_id"]
            ],
            on="road_node_id",
            how="left",
            validate="many_to_one",
        )
    )

    catchments = catchments.merge(
        mapping[
            ["bin_id", "collection_point_id"]
        ],
        on="bin_id",
        how="left",
        validate="many_to_one",
    )

    active = catchments[
        (catchments["population_2025"] > 0)
        | (catchments["activity_score"] > 0)
    ].copy()

    activity = (
        active
        .groupby(
            "collection_point_id",
            as_index=False,
        )
        .agg(
            healthcare_count=("healthcare_count", "sum"),
            supermarket_count=("supermarket_count", "sum"),
            major_retail_count=("major_retail_count", "sum"),
            market_count=("market_count", "sum"),
            food_service_count=("food_service_count", "sum"),
            education_count=("education_count", "sum"),
            activity_score=("activity_score", "sum"),
        )
    )

    policy = (
        points[
            ["collection_point_id"]
        ]
        .merge(
            point_demand[
                [
                    "collection_point_id",
                    "expected_daily_waste_kg",
                    "total_capacity_kg",
                ]
            ],
            on="collection_point_id",
            how="left",
            validate="one_to_one",
        )
        .merge(
            activity,
            on="collection_point_id",
            how="left",
            validate="one_to_one",
        )
    )

    activity_columns = [
        "healthcare_count",
        "supermarket_count",
        "major_retail_count",
        "market_count",
        "food_service_count",
        "education_count",
        "activity_score",
    ]

    policy[activity_columns] = (
        policy[activity_columns]
        .fillna(0)
    )

    high_demand_threshold = (
        policy["expected_daily_waste_kg"]
        .quantile(0.90)
    )

    # 24-hour utility class:
    # healthcare, supermarkets/markets, major retail,
    # dense food-service clusters, or top-decile waste demand.
    policy["is_priority_utility"] = (
        (policy["healthcare_count"] > 0)
        | (policy["supermarket_count"] > 0)
        | (policy["major_retail_count"] > 0)
        | (policy["market_count"] > 0)
        | (policy["food_service_count"] >= 3)
        | (
            policy["expected_daily_waste_kg"]
            >= high_demand_threshold
        )
    )

    policy["service_class"] = "standard_48h"

    policy.loc[
        policy["is_priority_utility"],
        "service_class",
    ] = "priority_24h"

    policy["max_service_interval_days"] = 2

    policy.loc[
        policy["is_priority_utility"],
        "max_service_interval_days",
    ] = 1

    # Any point approaching physical overflow becomes same-day mandatory,
    # regardless of nominal service class.
    policy["same_day_fill_trigger"] = 0.85

    policy.to_csv(
        OUTPUT_PATH,
        index=False,
    )

    print("Utility service policy created.")
    print(f"Collection points       : {len(policy):,}")
    print(
        f"Priority 24h points     : "
        f"{policy['is_priority_utility'].sum():,}"
    )
    print(
        f"Standard 48h points     : "
        f"{(~policy['is_priority_utility']).sum():,}"
    )
    print(
        f"High-demand threshold   : "
        f"{high_demand_threshold:,.1f} kg/day"
    )

    print()
    print("Priority triggers:")
    print(
        f"  healthcare points     : "
        f"{(policy['healthcare_count'] > 0).sum():,}"
    )
    print(
        f"  supermarket points    : "
        f"{(policy['supermarket_count'] > 0).sum():,}"
    )
    print(
        f"  major retail points   : "
        f"{(policy['major_retail_count'] > 0).sum():,}"
    )
    print(
        f"  market points         : "
        f"{(policy['market_count'] > 0).sum():,}"
    )
    print(
        f"  food-service clusters : "
        f"{(policy['food_service_count'] >= 3).sum():,}"
    )

    print()
    print(f"Output                  : {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
