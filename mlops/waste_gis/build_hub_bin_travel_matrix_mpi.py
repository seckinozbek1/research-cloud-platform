from pathlib import Path
import sys

from mpi4py import MPI
import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd


COMM = MPI.COMM_WORLD
RANK = COMM.Get_rank()
SIZE = COMM.Get_size()

PROJECT_ROOT = Path(__file__).resolve().parents[2]

GRAPH_PATH = PROJECT_ROOT / "data/gis/karsiyaka_street_network.graphml"
TRAFFIC_PATH = PROJECT_ROOT / "data/gis/traffic_scenarios/edge_vehicle_traffic_states.csv"
BINS_PATH = PROJECT_ROOT / "data/gis/karsiyaka_existing_bins.geojson"
HUBS_PATH = PROJECT_ROOT / "data/gis/karsiyaka_existing_hubs.geojson"

OUTPUT_DIR = PROJECT_ROOT / "data/gis/traffic_scenarios/mpi_partial"
FINAL_OUTPUT = PROJECT_ROOT / "data/gis/traffic_scenarios/hub_bin_travel_matrix_mpi.csv"

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


def compute_combination(task_id, combo, graph, traffic, bins, hubs):
    truck_type, scenario, suffix = combo

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

            rows.append({
                "hub_id": hub["hub_id"],
                "bin_id": bin_row["bin_id"],
                "truck_type": truck_type,
                "scenario": scenario,
                "hub_to_bin_minutes": (
                    outbound_s / 60 if np.isfinite(outbound_s) else np.inf
                ),
                "bin_to_hub_minutes": (
                    return_s / 60 if np.isfinite(return_s) else np.inf
                ),
                "round_trip_minutes": (
                    (outbound_s + return_s) / 60
                    if np.isfinite(outbound_s) and np.isfinite(return_s)
                    else np.inf
                ),
            })

    frame = pd.DataFrame(rows)

    output = OUTPUT_DIR / f"rank_{RANK}_task_{task_id:02d}.csv"
    frame.to_csv(output, index=False)

    print(
        f"rank={RANK} task={task_id} "
        f"truck={truck_type} scenario={scenario} "
        f"rows={len(frame)}",
        flush=True,
    )


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    graph = ox.io.load_graphml(GRAPH_PATH)
    traffic = pd.read_csv(TRAFFIC_PATH)
    bins = gpd.read_file(BINS_PATH)
    hubs = gpd.read_file(HUBS_PATH)

    assigned = [
        (task_id, combo)
        for task_id, combo in enumerate(COMBINATIONS)
        if task_id % SIZE == RANK
    ]

    print(
        f"rank={RANK}/{SIZE} assigned_tasks="
        f"{[task_id for task_id, _ in assigned]}",
        flush=True,
    )

    for task_id, combo in assigned:
        compute_combination(
            task_id,
            combo,
            graph,
            traffic,
            bins,
            hubs,
        )

    COMM.Barrier()

    if RANK == 0:
        parts = sorted(OUTPUT_DIR.glob("rank_*_task_*.csv"))

        merged = pd.concat(
            [pd.read_csv(path) for path in parts],
            ignore_index=True,
        )

        merged.to_csv(FINAL_OUTPUT, index=False)

        print(
            f"rank=0 merged_parts={len(parts)} "
            f"rows={len(merged)} output={FINAL_OUTPUT}",
            flush=True,
        )


if __name__ == "__main__":
    main()
