from pathlib import Path
import sys

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]

GRAPH_PATH = PROJECT_ROOT / "data/gis/karsiyaka_street_network.graphml"
TRAFFIC_PATH = PROJECT_ROOT / "data/gis/traffic_scenarios/edge_vehicle_traffic_states.csv"
BINS_PATH = PROJECT_ROOT / "data/gis/karsiyaka_existing_bins.geojson"
HUBS_PATH = PROJECT_ROOT / "data/gis/karsiyaka_existing_hubs.geojson"

OUTPUT_DIR = PROJECT_ROOT / "data/gis/traffic_scenarios/hpc_partial"


COMBINATIONS = [
    ("small_truck", "normal", "normal_s"),
    ("small_truck", "rush", "rush_s"),
    ("small_truck", "disrupted", "disrupted_s"),
    ("large_truck", "normal", "normal_s"),
    ("large_truck", "rush", "rush_s"),
    ("large_truck", "disrupted", "disrupted_s"),
]


def build_weighted_graph(base_graph, traffic, truck_type, suffix):
    graph = base_graph.copy()

    column = f"{truck_type}_{suffix}"

    lookup = {
        (str(row.u), str(row.v), str(row.key)): getattr(row, column)
        for row in traffic.itertuples()
    }

    remove_edges = []

    for u, v, key, data in graph.edges(keys=True, data=True):
        value = lookup.get((str(u), str(v), str(key)))

        if value is None or not np.isfinite(value):
            remove_edges.append((u, v, key))
        else:
            data["travel_time_s"] = float(value)

    graph.remove_edges_from(remove_edges)

    return graph


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python worker.py <task_id>")

    task_id = int(sys.argv[1])

    if not 0 <= task_id < len(COMBINATIONS):
        raise SystemExit(f"Invalid task_id: {task_id}")

    truck_type, scenario, suffix = COMBINATIONS[task_id]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    graph = ox.io.load_graphml(GRAPH_PATH)
    traffic = pd.read_csv(TRAFFIC_PATH)
    bins = gpd.read_file(BINS_PATH)
    hubs = gpd.read_file(HUBS_PATH)

    weighted_graph = build_weighted_graph(
        graph,
        traffic,
        truck_type,
        suffix,
    )

    rows = []

    for _, hub in hubs.iterrows():
        hub_node = int(hub["road_node_id"])

        outward = nx.single_source_dijkstra_path_length(
            weighted_graph,
            hub_node,
            weight="travel_time_s",
        )

        inward = nx.single_source_dijkstra_path_length(
            weighted_graph.reverse(copy=False),
            hub_node,
            weight="travel_time_s",
        )

        for _, bin_row in bins.iterrows():
            bin_node = int(bin_row["road_node_id"])

            outbound_s = outward.get(bin_node, np.inf)
            return_s = inward.get(bin_node, np.inf)

            rows.append(
                {
                    "hub_id": hub["hub_id"],
                    "bin_id": bin_row["bin_id"],
                    "truck_type": truck_type,
                    "scenario": scenario,
                    "hub_to_bin_minutes": (
                        outbound_s / 60
                        if np.isfinite(outbound_s)
                        else np.inf
                    ),
                    "bin_to_hub_minutes": (
                        return_s / 60
                        if np.isfinite(return_s)
                        else np.inf
                    ),
                    "round_trip_minutes": (
                        (outbound_s + return_s) / 60
                        if np.isfinite(outbound_s)
                        and np.isfinite(return_s)
                        else np.inf
                    ),
                }
            )

    output = OUTPUT_DIR / f"matrix_{task_id:02d}.csv"

    pd.DataFrame(rows).to_csv(output, index=False)

    print(f"Task     : {task_id}")
    print(f"Truck    : {truck_type}")
    print(f"Scenario : {scenario}")
    print(f"Rows     : {len(rows):,}")
    print(f"Output   : {output}")


if __name__ == "__main__":
    main()
