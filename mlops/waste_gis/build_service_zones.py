from pathlib import Path

import geopandas as gpd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

INPUT_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_zone_population.geojson"
)

OUTPUT_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_service_zones.geojson"
)

MIN_POPULATION = 500


def main() -> None:
    zones = gpd.read_file(INPUT_PATH)

    service_zones = zones[
        zones["population_2025"] >= MIN_POPULATION
    ].copy()

    service_zones["is_service_zone"] = True

    service_zones.to_file(
        OUTPUT_PATH,
        driver="GeoJSON",
    )

    print("Service zones created successfully.")
    print(f"Candidate zones    : {len(zones)}")
    print(f"Population rule    : >= {MIN_POPULATION}")
    print(f"Service zones      : {len(service_zones)}")
    print(
        "Covered population: "
        f"{service_zones['population_2025'].sum():,.0f}"
    )
    print(
        "Population share   : "
        f"{100 * service_zones['population_2025'].sum() / zones['population_2025'].sum():.2f}%"
    )
    print(f"Output             : {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
