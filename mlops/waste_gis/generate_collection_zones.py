from pathlib import Path

import geopandas as gpd
from shapely.geometry import box


PROJECT_ROOT = Path(__file__).resolve().parents[2]

BOUNDARY_PATH = PROJECT_ROOT / "data" / "gis" / "karsiyaka_boundary.geojson"
OUTPUT_PATH = PROJECT_ROOT / "data" / "gis" / "karsiyaka_collection_zones.geojson"

GRID_SIZE_M = 1000
MIN_ZONE_AREA_M2 = 100_000


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

    # Keep only cells intersecting Karşıyaka.
    zones = grid[grid.intersects(district_geom)].copy()

    # Clip each grid cell to the true district boundary.
    zones["geometry"] = zones.geometry.intersection(district_geom)

    zones["area_m2"] = zones.geometry.area

    # Remove tiny boundary slivers that would not make meaningful
    # operational collection zones.
    zones = zones[zones["area_m2"] >= MIN_ZONE_AREA_M2].copy()

    zones = zones.reset_index(drop=True)

    zones["zone_id"] = [
        f"KSK-Z{number:03d}"
        for number in range(1, len(zones) + 1)
    ]

    zones["area_km2"] = zones["area_m2"] / 1_000_000

    zones = zones[
        [
            "zone_id",
            "area_m2",
            "area_km2",
            "geometry",
        ]
    ]

    # Store interoperable GIS artifact in WGS84.
    zones_wgs84 = zones.to_crs("EPSG:4326")
    zones_wgs84.to_file(OUTPUT_PATH, driver="GeoJSON")

    print("Collection zones created successfully.")
    print(f"Metric CRS        : {metric_crs}")
    print(f"Grid size         : {GRID_SIZE_M} m")
    print(f"Minimum zone area : {MIN_ZONE_AREA_M2:,} m²")
    print(f"Zones retained    : {len(zones):,}")
    print(f"Total zone area   : {zones['area_km2'].sum():.2f} km²")
    print(f"Output            : {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
