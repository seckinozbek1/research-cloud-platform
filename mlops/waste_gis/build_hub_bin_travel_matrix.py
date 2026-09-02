from pathlib import Path

import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
import geopandas as gpd
from tqdm import tqdm


PROJECT_ROOT = Path(__file__).resolve().parents[2]

GRAPH_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_street_network.graphml"
)

TRAFFIC_PATH = (
    PROJECT_ROOT
    / "data"
    / "gis"
    / "traffic_scenarios"
    / "edge_vehicle_traffic_states.csv"
)

BINS_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_existing_bins.geojson"
)

HUBS_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_existing_hubs.geojson"
)

OUTPUT_PATH = (
    PROJECT_ROOT
    / "data"
    / "gis"
    / "traffic_scenarios"
    / "hub_bin_travel_matrix.csv"
)


TRUCK_TYPES = [
    "small_truck",
    "large_truck",
]

SCENARIOS = {
    "normal": "normal_s",
    "rush": "rush_s",
    "disrupted": "disrupted_s",
}


def build_weighted_graph(
    base_graph,
    traffic,
    truck_type,
    scenario_suffix,
):
    graph = base_graph.copy()

    weight_column = (
        f"{truck_type}_{scenario_suffix}"
    )

    lookup = {
        (
            str(row.u),
            str(row.v),
            str(row.key),
        ): getattr(row, weight_column)
        for row in traffic.itertuples()
    }

    remove_edges = []

    for u, v, key, data in graph.edges(
        keys=True,
        data=True,
    ):
        value = lookup.get(
            (str(u), str(v), str(key))
        )

        if value is None or not np.isfinite(value):
            remove_edges.append(
                (u, v, key)
            )
        else:
            data["travel_time_s"] = float(value)

    graph.remove_edges_from(remove_edges)

    return graph


def main():
    graph = ox.io.load_graphml(GRAPH_PATH)

    traffic = pd.read_csv(TRAFFIC_PATH)

    bins = gpd.read_file(BINS_PATH)
    hubs = gpd.read_file(HUBS_PATH)

    rows = []

    combinations = [
        (truck_type, scenario, suffix)
        for truck_type in TRUCK_TYPES
        for scenario, suffix in SCENARIOS.items()
    ]

    for truck_type, scenario, suffix in tqdm(
        combinations,
        desc="Truck/scenario matrices",
        unit="matrix",
    ):
        weighted_graph = build_weighted_graph(
            graph,
            traffic,
            truck_type,
            suffix,
        )

        for _, hub in hubs.iterrows():
            hub_node = int(
                hub["road_node_id"]
            )

            outward = nx.single_source_dijkstra_path_length(
                weighted_graph,
                hub_node,
                weight="travel_time_s",
            )

            reverse_graph = weighted_graph.reverse(
                copy=False
            )

            inward = nx.single_source_dijkstra_path_length(
                reverse_graph,
                hub_node,
                weight="travel_time_s",
            )

            for _, bin_row in bins.iterrows():
                bin_node = int(
                    bin_row["road_node_id"]
                )

                outbound_s = outward.get(
                    bin_node,
                    np.inf,
                )

                return_s = inward.get(
                    bin_node,
                    np.inf,
                )

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
                            if (
                                np.isfinite(outbound_s)
                                and np.isfinite(return_s)
                            )
                            else np.inf
                        ),
                    }
                )

    matrix = pd.DataFrame(rows)

    matrix.to_csv(
        OUTPUT_PATH,
        index=False,
    )

    finite = np.isfinite(
        matrix["round_trip_minutes"]
    )

    print()
    print("Hub-bin travel matrix created.")
    print(f"Rows                  : {len(matrix):,}")
    print(
        f"Reachable combinations: "
        f"{finite.sum():,}/{len(matrix):,}"
    )
    print(
        f"Unreachable           : "
        f"{(~finite).sum():,}"
    )

    print()

    summary = (
        matrix[finite]
        .groupby(
            ["truck_type", "scenario"]
        )["round_trip_minutes"]
        .agg(
            ["median", "mean", "max"]
        )
        .round(2)
    )

    print(summary.to_string())

    print()
    print(f"Output                : {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
