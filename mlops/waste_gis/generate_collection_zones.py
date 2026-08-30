from pathlib import Path

import geopandas as gpd
from shapely.geometry import box


PROJECT_ROOT = Path(__file__).resolve().parents[2]

BOUNDARY_PATH = PROJECT_ROOT / "data" / "gis" / "karsiyaka_boundary.geojson"
OUTPUT_PATH = PROJECT_ROOT / "data" / "gis" / "karsiyaka_collection_zones.geojson"

GRID_SIZE_M = 100
MIN_COVERAGE_RATIO = 0.25


def main() -> None:
    boundary = gpd.read_file(BOUNDARY_PATH)

    metric_crs = boundary.estimate_utm_crs()
    boundary_m = boundary.to_crs(metric_crs)

    district_geom = boundary_m.geometry.union_all()

    minx, miny, maxx, maxy = district_geom.bounds

    cells = []

    x = minx
    while x < maxx:
        y = miny
        while y < maxy:
            cells.append(box(x, y, x + GRID_SIZE_M, y + GRID_SIZE_M))
            y += GRID_SIZE_M
        x += GRID_SIZE_M

    grid = gpd.GeoDataFrame(
        geometry=cells,
        crs=metric_crs,
    )

    grid = grid[grid.intersects(district_geom)].copy()

    grid["geometry"] = grid.geometry.intersection(district_geom)

    full_cell_area = GRID_SIZE_M * GRID_SIZE_M

    grid["area_m2"] = grid.geometry.area
    grid["coverage_ratio"] = grid["area_m2"] / full_cell_area

    zones = grid[
        grid["coverage_ratio"] >= MIN_COVERAGE_RATIO
    ].copy()

    zones = zones.reset_index(drop=True)

    zones["zone_id"] = [
        f"KSK-C{number:05d}"
        for number in range(1, len(zones) + 1)
    ]

    zones["area_km2"] = zones["area_m2"] / 1_000_000

    zones = zones[
        [
            "zone_id",
            "area_m2",
            "area_km2",
            "coverage_ratio",
            "geometry",
        ]
    ]

    zones.to_crs("EPSG:4326").to_file(
        OUTPUT_PATH,
        driver="GeoJSON",
    )

    print("100 m demand grid created successfully.")
    print(f"Metric CRS          : {metric_crs}")
    print(f"Grid size           : {GRID_SIZE_M} m")
    print(f"Minimum coverage    : {MIN_COVERAGE_RATIO:.0%}")
    print(f"Cells retained      : {len(zones):,}")
    print(f"Covered area        : {zones['area_km2'].sum():.2f} km²")
    print(f"Output              : {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
