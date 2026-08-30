from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from tqdm import tqdm


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CELLS_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_activity_features.geojson"
)

BINS_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_existing_bins.geojson"
)

CATCHMENTS_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_bin_catchments.geojson"
)

DEMAND_PATH = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "waste_gis"
    / "bin_daily_generated_waste.csv"
)

RANDOM_SEED = 42
START_DATE = "2026-07-01"
DAYS = 30


def main():
    rng = np.random.default_rng(RANDOM_SEED)

    cells = gpd.read_file(CELLS_PATH)
    bins = gpd.read_file(BINS_PATH)

    metric_crs = cells.estimate_utm_crs()

    cells_m = cells.to_crs(metric_crs).copy()
    bins_m = bins.to_crs(metric_crs).copy()

    # Cell centroids represent local demand origins.
    demand_points = cells_m.copy()
    demand_points["geometry"] = demand_points.geometry.centroid

    bin_points = bins_m[
        [
            "bin_id",
            "bin_type",
            "capacity_kg",
            "geometry",
        ]
    ].copy()

    # Assign every 100 m demand cell to its nearest existing bin.
    assigned = gpd.sjoin_nearest(
        demand_points,
        bin_points,
        how="left",
        distance_col="access_distance_m",
    )

    # If multiple bins sit at exactly the same distance, keep one
    # deterministic assignment per demand cell.
    assigned = (
        assigned
        .sort_values(
            ["zone_id", "access_distance_m", "bin_id"]
        )
        .drop_duplicates(
            subset=["zone_id"],
            keep="first",
        )
        .copy()
    )

    # --------------------------------------------------------------
    # Exogenous daily waste-generation potential.
    #
    # This represents waste CREATED in the catchment.
    # Pickup frequency and bin capacity are deliberately NOT inputs.
    # --------------------------------------------------------------

    assigned["residential_daily_kg"] = (
        assigned["population_2025"] * 0.90
    )

    assigned["activity_daily_kg"] = (
        assigned["healthcare_count"] * 80.0
        + assigned["major_retail_count"] * 130.0
        + assigned["supermarket_count"] * 65.0
        + assigned["food_service_count"] * 24.0
        + assigned["market_count"] * 70.0
        + assigned["hotel_count"] * 35.0
        + assigned["education_count"] * 18.0
        + assigned["commercial_count"] * 45.0
        + assigned["industrial_count"] * 55.0
        + assigned["recreation_count"] * 8.0
    )

    assigned["expected_daily_waste_kg"] = (
        assigned["residential_daily_kg"]
        + assigned["activity_daily_kg"]
    )

    # Preserve the demand-cell → current-bin relationship.
    catchments = cells_m.merge(
        assigned[
            [
                "zone_id",
                "bin_id",
                "access_distance_m",
                "residential_daily_kg",
                "activity_daily_kg",
                "expected_daily_waste_kg",
            ]
        ],
        on="zone_id",
        how="left",
    )

    catchments.to_crs("EPSG:4326").to_file(
        CATCHMENTS_PATH,
        driver="GeoJSON",
    )

    # Aggregate expected waste generation into existing bins.
    bin_base = (
        assigned
        .groupby("bin_id", as_index=False)
        .agg(
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
            demand_cells=("zone_id", "count"),
        )
    )

    # Include bins that receive no nearest-cell assignment.
    bin_base = (
        bins[
            ["bin_id", "bin_type", "capacity_kg"]
        ]
        .merge(
            bin_base,
            on="bin_id",
            how="left",
        )
    )

    numeric_fill = [
        "population_served",
        "activity_score_served",
        "expected_daily_waste_kg",
        "mean_access_distance_m",
        "max_access_distance_m",
        "demand_cells",
    ]

    bin_base[numeric_fill] = (
        bin_base[numeric_fill].fillna(0)
    )

    # --------------------------------------------------------------
    # 30-day generated-waste history.
    # --------------------------------------------------------------

    dates = pd.date_range(
        START_DATE,
        periods=DAYS,
        freq="D",
    )

    rows = []

    total = len(dates) * len(bin_base)

    with tqdm(
        total=total,
        desc="Generating bin demand",
        unit="bin-day",
    ) as progress:

        for date in dates:
            weekend = int(
                date.weekday() >= 5
            )

            # Contextual day-level effects.
            temperature_c = float(
                rng.normal(29.0, 3.5)
            )

            rain_mm = float(
                max(
                    0.0,
                    rng.gamma(1.2, 2.0)
                    if rng.random() < 0.20
                    else 0.0,
                )
            )

            for row in bin_base.itertuples():
                expected = float(
                    row.expected_daily_waste_kg
                )

                # Weekend/activity and weather variation.
                multiplier = 1.0

                if weekend:
                    multiplier *= 1.05

                if temperature_c > 32:
                    multiplier *= 1.03

                if rain_mm > 5:
                    multiplier *= 0.97

                # Local stochastic variation.
                noise = rng.normal(
                    loc=1.0,
                    scale=0.10,
                )

                generated = max(
                    0.0,
                    expected
                    * multiplier
                    * noise,
                )

                rows.append(
                    {
                        "date": date.date().isoformat(),
                        "bin_id": row.bin_id,
                        "bin_type": row.bin_type,
                        "capacity_kg": row.capacity_kg,
                        "population_served": row.population_served,
                        "activity_score_served": (
                            row.activity_score_served
                        ),
                        "mean_access_distance_m": (
                            row.mean_access_distance_m
                        ),
                        "max_access_distance_m": (
                            row.max_access_distance_m
                        ),
                        "weekend": weekend,
                        "temperature_c": round(
                            temperature_c,
                            2,
                        ),
                        "rain_mm": round(
                            rain_mm,
                            2,
                        ),
                        "expected_daily_waste_kg": (
                            expected
                        ),
                        "generated_waste_kg": (
                            generated
                        ),
                    }
                )

                progress.update(1)

    demand = pd.DataFrame(rows)

    DEMAND_PATH.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    demand.to_csv(
        DEMAND_PATH,
        index=False,
    )

    print()
    print("Bin-level demand baseline created.")
    print(f"Demand cells          : {len(assigned):,}")
    print(f"Existing bins         : {len(bin_base):,}")
    print(
        f"Bins serving >=1 cell : "
        f"{(bin_base['demand_cells'] > 0).sum():,}"
    )
    print(
        f"Bins serving 0 cells  : "
        f"{(bin_base['demand_cells'] == 0).sum():,}"
    )
    print(
        f"Mean access distance  : "
        f"{assigned['access_distance_m'].mean():.1f} m"
    )
    print(
        f"95th pct access dist  : "
        f"{assigned['access_distance_m'].quantile(.95):.1f} m"
    )
    print(
        f"Max access distance   : "
        f"{assigned['access_distance_m'].max():.1f} m"
    )
    print(
        f"Expected daily waste  : "
        f"{bin_base['expected_daily_waste_kg'].sum():,.0f} kg/day"
    )
    print(
        f"Generated observations: "
        f"{len(demand):,}"
    )
    print(f"Catchments output     : {CATCHMENTS_PATH}")
    print(f"Demand output         : {DEMAND_PATH}")


if __name__ == "__main__":
    main()
