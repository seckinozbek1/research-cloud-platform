from pathlib import Path

import geopandas as gpd
from rasterstats import zonal_stats
from tqdm import tqdm


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CELLS_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_collection_zones.geojson"
)

WORLDPOP_PATH = (
    PROJECT_ROOT
    / "data"
    / "gis"
    / "worldpop"
    / "tur_pop_2025_CN_100m_R2025A_v1.tif"
)

OUTPUT_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_zone_population.geojson"
)

CHUNK_SIZE = 250
POPULATION_SOURCE = "worldpop_R2025A_2025_100m"


def main() -> None:
    cells = gpd.read_file(CELLS_PATH)

    population = []

    chunks = [
        cells.iloc[i:i + CHUNK_SIZE]
        for i in range(0, len(cells), CHUNK_SIZE)
    ]

    for chunk in tqdm(
        chunks,
        desc="WorldPop cells",
        unit="chunk",
    ):
        stats = zonal_stats(
            chunk.geometry,
            WORLDPOP_PATH,
            stats=["sum"],
            nodata=-99999.0,
            all_touched=False,
        )

        for result in stats:
            value = result.get("sum")

            if value is None:
                population.append(0.0)
            else:
                population.append(max(float(value), 0.0))

    cells["population_2025"] = population

    cells["population_density_2025"] = (
        cells["population_2025"]
        / cells["area_km2"]
    )

    cells["population_source"] = POPULATION_SOURCE

    cells.to_file(
        OUTPUT_PATH,
        driver="GeoJSON",
    )

    print()
    print("Local WorldPop enrichment completed.")
    print(f"Cells                : {len(cells):,}")
    print(
        f"Population total     : "
        f"{cells['population_2025'].sum():,.0f}"
    )
    print(
        f"Populated cells      : "
        f"{(cells['population_2025'] > 0).sum():,}"
    )
    print(
        f"Zero-population cells: "
        f"{(cells['population_2025'] == 0).sum():,}"
    )
    print(
        f"Population range     : "
        f"{cells['population_2025'].min():,.1f}–"
        f"{cells['population_2025'].max():,.1f}"
    )
    print(f"Output               : {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
