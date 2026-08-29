from pathlib import Path

import osmnx as ox


# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

PLACE_QUERY = "Karşıyaka, İzmir, Türkiye"
NETWORK_TYPE = "drive"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = PROJECT_ROOT / "data" / "gis"

BOUNDARY_PATH = OUTPUT_DIR / "karsiyaka_boundary.geojson"
ROADS_PATH = OUTPUT_DIR / "karsiyaka_roads.geojson"
GRAPH_PATH = OUTPUT_DIR / "karsiyaka_street_network.graphml"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Resolve Karşıyaka's administrative boundary from OpenStreetMap.
    print(f"Fetching boundary for: {PLACE_QUERY}")
    boundary = ox.geocode_to_gdf(PLACE_QUERY)

    if len(boundary) != 1:
        raise RuntimeError(
            f"Expected exactly one boundary feature, received {len(boundary)}."
        )

    geometry = boundary.iloc[0].geometry

    if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
        raise RuntimeError(
            f"Expected Polygon or MultiPolygon, received {geometry.geom_type}."
        )

    boundary.to_file(BOUNDARY_PATH, driver="GeoJSON")
    print(f"Saved boundary: {BOUNDARY_PATH}")

    # 2. Download the drivable street network inside the boundary.
    print("Fetching drivable street network...")
    graph = ox.graph.graph_from_polygon(
        geometry,
        network_type=NETWORK_TYPE,
        simplify=True,
    )

    # Preserve the graph topology for future network analysis.
    ox.io.save_graphml(graph, filepath=GRAPH_PATH)
    print(f"Saved street graph: {GRAPH_PATH}")

    # 3. Convert graph edges into GIS line geometries.
    _, edges = ox.convert.graph_to_gdfs(graph)

    edges.to_file(ROADS_PATH, driver="GeoJSON")
    print(f"Saved road geometries: {ROADS_PATH}")

    print()
    print("Spatial base created successfully.")
    print(f"Boundary features : {len(boundary):,}")
    print(f"Graph nodes       : {len(graph.nodes):,}")
    print(f"Graph edges       : {len(graph.edges):,}")
    print(f"Road geometries   : {len(edges):,}")
    print(f"CRS               : {edges.crs}")


if __name__ == "__main__":
    main()
