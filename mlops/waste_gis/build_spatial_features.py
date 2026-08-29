from pathlib import Path

import geopandas as gpd
import osmnx as ox


PROJECT_ROOT = Path(__file__).resolve().parents[2]

ZONES_PATH = PROJECT_ROOT / "data" / "gis" / "karsiyaka_collection_zones.geojson"
GRAPH_PATH = PROJECT_ROOT / "data" / "gis" / "karsiyaka_street_network.graphml"

OUTPUT_PATH = PROJECT_ROOT / "data" / "gis" / "karsiyaka_zone_features.geojson"


def main() -> None:
    zones = gpd.read_file(ZONES_PATH)

    metric_crs = zones.estimate_utm_crs()
    zones_m = zones.to_crs(metric_crs)

    # Load the saved OSMnx street graph.
    graph = ox.io.load_graphml(GRAPH_PATH)

    # Convert directed street graph into an undirected representation
    # so two-way streets are not naively counted twice.
    undirected = ox.convert.to_undirected(graph)

    _, roads = ox.convert.graph_to_gdfs(undirected)
    roads_m = roads.to_crs(metric_crs)

    feature_rows = []

    for _, zone in zones_m.iterrows():
        zone_geom = zone.geometry

        candidate_roads = roads_m[roads_m.intersects(zone_geom)].copy()

        if candidate_roads.empty:
            road_length_m = 0.0
        else:
            clipped = candidate_roads.geometry.intersection(zone_geom)
            road_length_m = clipped.length.sum()

        area_km2 = zone_geom.area / 1_000_000
        road_length_km = road_length_m / 1000

        road_density = (
            road_length_km / area_km2
            if area_km2 > 0
            else 0.0
        )

        feature_rows.append(
            {
                "zone_id": zone["zone_id"],
                "area_km2": area_km2,
                "road_length_m": road_length_m,
                "road_density_km_per_km2": road_density,
                "geometry": zone_geom,
            }
        )

    features = gpd.GeoDataFrame(
        feature_rows,
        geometry="geometry",
        crs=metric_crs,
    )

    features = features.to_crs("EPSG:4326")
    features.to_file(OUTPUT_PATH, driver="GeoJSON")

    print("Spatial features created successfully.")
    print(f"Zones                 : {len(features):,}")
    print(
        "Road length range     : "
        f"{features['road_length_m'].min():.0f}–"
        f"{features['road_length_m'].max():.0f} m"
    )
    print(
        "Road density range    : "
        f"{features['road_density_km_per_km2'].min():.2f}–"
        f"{features['road_density_km_per_km2'].max():.2f} km/km²"
    )
    print(
        "Mean road density     : "
        f"{features['road_density_km_per_km2'].mean():.2f} km/km²"
    )
    print(f"Output                : {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
