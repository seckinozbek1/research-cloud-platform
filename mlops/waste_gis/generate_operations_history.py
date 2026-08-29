from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

SERVICE_ZONES_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_service_zones.geojson"
)

OUTPUT_DIR = PROJECT_ROOT / "data" / "curated" / "waste_gis"
OUTPUT_PATH = OUTPUT_DIR / "waste_operations.csv"

RANDOM_SEED = 42
N_DAYS = 180
START_DATE = "2026-01-01"


def main() -> None:
    rng = np.random.default_rng(RANDOM_SEED)

    zones = gpd.read_file(SERVICE_ZONES_PATH)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dates = pd.date_range(
        start=START_DATE,
        periods=N_DAYS,
        freq="D",
    )

    rows = []

    for _, zone in zones.iterrows():
        population = float(zone["population_2025"])
        pop_density = float(zone["population_density_2025"])
        road_density = float(zone["road_density_km_per_km2"])

        # Static operational capacity for the zone.
        # This is synthetic municipal infrastructure, not real GIS data.
        container_capacity_kg = (
            population
            * rng.uniform(1.1, 1.5)
        )

        previous_waste_kg = population * 0.9

        # Small persistent zone-level effect.
        zone_multiplier = rng.normal(1.0, 0.05)

        for day_number, date in enumerate(dates):
            weekend = int(date.dayofweek >= 5)

            days_since_last_pickup = int(
                rng.choice(
                    [1, 2, 3],
                    p=[0.70, 0.25, 0.05],
                )
            )

            # Synthetic seasonal temperature pattern.
            seasonal_temperature = (
                18
                + 8
                * np.sin(
                    2
                    * np.pi
                    * day_number
                    / 365
                    - np.pi / 2
                )
            )

            temperature_c = seasonal_temperature + rng.normal(0, 2.5)

            # Most days have no or little rain.
            if rng.random() < 0.25:
                rain_mm = rng.gamma(shape=1.5, scale=4.0)
            else:
                rain_mm = 0.0

            base_waste = (
                population
                * 0.90
                * days_since_last_pickup
            )

            weekend_effect = 1.06 if weekend else 1.0

            temperature_effect = (
                1.0
                + max(temperature_c - 25, 0)
                * 0.004
            )

            rain_effect = (
                1.0
                - min(rain_mm, 30)
                * 0.002
            )

            # Dense commercial/urban areas generate slightly more
            # municipal waste per resident.
            density_effect = (
                1.0
                + min(pop_density / 30_000, 1.0)
                * 0.08
            )

            expected_waste = (
                base_waste
                * weekend_effect
                * temperature_effect
                * rain_effect
                * density_effect
                * zone_multiplier
            )

            # Random operational variation.
            noise = rng.normal(
                0,
                max(expected_waste * 0.08, 50),
            )

            waste_kg = max(
                expected_waste + noise,
                0,
            )

            rows.append(
                {
                    "zone_id": zone["zone_id"],
                    "collection_date": date.date().isoformat(),
                    "population_2025": population,
                    "population_density_2025": pop_density,
                    "road_density_km_per_km2": road_density,
                    "container_capacity_kg": container_capacity_kg,
                    "days_since_last_pickup": days_since_last_pickup,
                    "weekend": weekend,
                    "temperature_c": temperature_c,
                    "rain_mm": rain_mm,
                    "previous_waste_kg": previous_waste_kg,
                    "waste_kg": waste_kg,
                }
            )

            previous_waste_kg = waste_kg

    df = pd.DataFrame(rows)

    df.to_csv(
        OUTPUT_PATH,
        index=False,
    )

    print("Synthetic operations history created.")
    print(f"Random seed        : {RANDOM_SEED}")
    print(f"Service zones      : {len(zones):,}")
    print(f"Days per zone      : {N_DAYS:,}")
    print(f"Observations       : {len(df):,}")
    print(
        f"Date range         : "
        f"{df['collection_date'].min()} → "
        f"{df['collection_date'].max()}"
    )
    print(
        f"Waste range        : "
        f"{df['waste_kg'].min():,.0f}–"
        f"{df['waste_kg'].max():,.0f} kg"
    )
    print(
        f"Mean waste         : "
        f"{df['waste_kg'].mean():,.0f} kg"
    )
    print(f"Output             : {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
