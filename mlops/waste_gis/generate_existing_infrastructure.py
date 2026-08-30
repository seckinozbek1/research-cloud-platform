from pathlib import Path

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
from sklearn.cluster import KMeans


PROJECT_ROOT = Path(__file__).resolve().parents[2]

CELLS_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_activity_features.geojson"
)

GRAPH_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_street_network.graphml"
)

BINS_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_existing_bins.geojson"
)

HUBS_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_existing_hubs.geojson"
)

FLEET_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_existing_fleet.geojson"
)

RANDOM_SEED = 42

TOTAL_BINS = 1200

# First create a broad spatial baseline, then use the remaining
# physical bins as extra capacity at higher-demand locations.
BASE_UNIQUE_LOCATIONS = 850

TOTAL_HUBS = 3
TRUCKS_PER_HUB = 4


BIN_TYPES = {
    "small_bin": {
        "capacity_kg": 250.0,
        "pickup_service_seconds_min": 45,
        "pickup_service_seconds_max": 75,
    },
    "medium_bin": {
        "capacity_kg": 450.0,
        "pickup_service_seconds_min": 60,
        "pickup_service_seconds_max": 100,
    },
    "large_bin": {
        "capacity_kg": 900.0,
        "pickup_service_seconds_min": 90,
        "pickup_service_seconds_max": 150,
    },
}


TRUCK_TYPES = {
    "small_truck": {
        "payload_capacity_kg": 6000.0,
        "operational_speed_cap_kph": 42.0,
        "unload_time_minutes": 12.0,
        "departure_overhead_minutes": 5.0,
        "return_overhead_minutes": 5.0,
    },
    "large_truck": {
        "payload_capacity_kg": 12000.0,
        "operational_speed_cap_kph": 34.0,
        "unload_time_minutes": 18.0,
        "departure_overhead_minutes": 7.0,
        "return_overhead_minutes": 7.0,
    },
}


def main() -> None:
    rng = np.random.default_rng(RANDOM_SEED)

    cells = gpd.read_file(CELLS_PATH)

    metric_crs = cells.estimate_utm_crs()
    cells_m = cells.to_crs(metric_crs)

    graph = ox.io.load_graphml(GRAPH_PATH)
    graph_m = ox.project_graph(graph, to_crs=metric_crs)

    largest_scc = max(
        nx.strongly_connected_components(graph_m),
        key=len,
    )

    routable_graph_m = graph_m.subgraph(
        largest_scc
    ).copy()

    nodes_m, _ = ox.graph_to_gdfs(routable_graph_m)

    print(
        f"Routable main SCC     : "
        f"{routable_graph_m.number_of_nodes():,}/"
        f"{graph_m.number_of_nodes():,} nodes"
    )

    # ------------------------------------------------------------------
    # Existing bin system
    # ------------------------------------------------------------------

    cells_m["baseline_demand_score"] = (
        cells_m["population_2025"]
        + 35.0 * cells_m["activity_score"]
    )

    eligible = cells_m[
        cells_m["baseline_demand_score"] > 0
    ].copy()

    demand = eligible["baseline_demand_score"].to_numpy(dtype=float)
    eligible_indices = eligible.index.to_numpy()

    # Broad spatial coverage:
    # sqrt weighting still favours demand but prevents the baseline
    # network from collapsing excessively into the densest cells.
    spread_weights = np.sqrt(demand + 1.0)
    spread_weights = spread_weights / spread_weights.sum()

    base_locations = min(
        BASE_UNIQUE_LOCATIONS,
        len(eligible),
        TOTAL_BINS,
    )

    base_idx = rng.choice(
        eligible_indices,
        size=base_locations,
        replace=False,
        p=spread_weights,
    )

    # Remaining physical bins represent extra capacity at busier
    # existing collection locations.
    remaining_bins = TOTAL_BINS - base_locations

    demand_weights = demand / demand.sum()

    if remaining_bins > 0:
        extra_idx = rng.choice(
            eligible_indices,
            size=remaining_bins,
            replace=True,
            p=demand_weights,
        )

        selected_idx = np.concatenate(
            [base_idx, extra_idx]
        )
    else:
        selected_idx = base_idx

    selected_cells = eligible.loc[selected_idx].copy()

    centroid_x = selected_cells.geometry.centroid.x.to_numpy()
    centroid_y = selected_cells.geometry.centroid.y.to_numpy()

    nearest_nodes = ox.distance.nearest_nodes(
        routable_graph_m,
        X=centroid_x,
        Y=centroid_y,
    )

    bin_type_names = np.array(
        ["small_bin", "medium_bin", "large_bin"]
    )

    bin_type_probs = np.array([0.25, 0.60, 0.15])

    bin_rows = []

    for number, (cell_index, node_id) in enumerate(
        zip(selected_idx, nearest_nodes),
        start=1,
    ):
        cell = cells_m.loc[cell_index]
        node = nodes_m.loc[node_id]

        bin_type = str(
            rng.choice(
                bin_type_names,
                p=bin_type_probs,
            )
        )

        config = BIN_TYPES[bin_type]

        pickup_service_seconds = int(
            rng.integers(
                config["pickup_service_seconds_min"],
                config["pickup_service_seconds_max"] + 1,
            )
        )

        bin_rows.append(
            {
                "bin_id": f"KSK-B{number:04d}",
                "source_cell_id": cell["zone_id"],
                "bin_type": bin_type,
                "capacity_kg": config["capacity_kg"],
                "pickup_service_seconds": pickup_service_seconds,
                "current_pickups_per_week": int(
                    rng.choice(
                        [2, 3, 4, 5, 6, 7],
                        p=[0.05, 0.15, 0.25, 0.25, 0.15, 0.15],
                    )
                ),
                "baseline_demand_score": float(
                    cell["baseline_demand_score"]
                ),
                "road_node_id": str(node_id),
                "geometry": node.geometry,
            }
        )

    bins = gpd.GeoDataFrame(
        bin_rows,
        geometry="geometry",
        crs=metric_crs,
    )

    # ------------------------------------------------------------------
    # Existing hubs
    # ------------------------------------------------------------------

    urban = eligible[
        eligible["population_2025"] > 0
    ].copy()

    centroids = urban.geometry.centroid

    coords = np.column_stack(
        [
            centroids.x.to_numpy(),
            centroids.y.to_numpy(),
        ]
    )

    hub_weights = urban["baseline_demand_score"].to_numpy(dtype=float)

    kmeans = KMeans(
        n_clusters=TOTAL_HUBS,
        random_state=RANDOM_SEED,
        n_init=10,
    )

    kmeans.fit(
        coords,
        sample_weight=hub_weights,
    )

    hub_x = kmeans.cluster_centers_[:, 0]
    hub_y = kmeans.cluster_centers_[:, 1]

    hub_nodes = ox.distance.nearest_nodes(
        routable_graph_m,
        X=hub_x,
        Y=hub_y,
    )

    hub_rows = []

    for number, node_id in enumerate(hub_nodes, start=1):
        node = nodes_m.loc[node_id]

        hub_rows.append(
            {
                "hub_id": f"KSK-H{number:02d}",
                "road_node_id": str(node_id),
                "truck_count": TRUCKS_PER_HUB,
                "crew_count": TRUCKS_PER_HUB,
                "shift_hours": 8.0,
                "geometry": node.geometry,
            }
        )

    hubs = gpd.GeoDataFrame(
        hub_rows,
        geometry="geometry",
        crs=metric_crs,
    )

    # ------------------------------------------------------------------
    # Explicit truck fleet
    # ------------------------------------------------------------------

    fleet_rows = []

    truck_number = 1

    for _, hub in hubs.iterrows():
        # 2 small + 2 large trucks per hub.
        hub_truck_types = [
            "small_truck",
            "small_truck",
            "large_truck",
            "large_truck",
        ]

        for truck_type in hub_truck_types:
            config = TRUCK_TYPES[truck_type]

            fleet_rows.append(
                {
                    "truck_id": f"KSK-T{truck_number:03d}",
                    "truck_type": truck_type,
                    "hub_id": hub["hub_id"],
                    "payload_capacity_kg": config[
                        "payload_capacity_kg"
                    ],
                    "operational_speed_cap_kph": config[
                        "operational_speed_cap_kph"
                    ],
                    "unload_time_minutes": config[
                        "unload_time_minutes"
                    ],
                    "departure_overhead_minutes": config[
                        "departure_overhead_minutes"
                    ],
                    "return_overhead_minutes": config[
                        "return_overhead_minutes"
                    ],
                    "shift_hours": float(hub["shift_hours"]),
                    "road_node_id": hub["road_node_id"],
                    "geometry": hub.geometry,
                }
            )

            truck_number += 1

    fleet = gpd.GeoDataFrame(
        fleet_rows,
        geometry="geometry",
        crs=metric_crs,
    )

    bins.to_crs("EPSG:4326").to_file(
        BINS_PATH,
        driver="GeoJSON",
    )

    hubs.to_crs("EPSG:4326").to_file(
        HUBS_PATH,
        driver="GeoJSON",
    )

    fleet.to_crs("EPSG:4326").to_file(
        FLEET_PATH,
        driver="GeoJSON",
    )

    print("Existing synthetic infrastructure created.")
    print(f"Fixed bin stock       : {len(bins):,}")
    print(f"Fixed hubs            : {len(hubs):,}")
    print(f"Explicit fleet        : {len(fleet):,}")

    print()
    print("Bin composition:")
    print(
        bins["bin_type"]
        .value_counts()
        .sort_index()
        .to_string()
    )

    print()
    print("Truck composition:")
    print(
        fleet["truck_type"]
        .value_counts()
        .sort_index()
        .to_string()
    )

    print()
    print(
        f"Total bin capacity    : "
        f"{bins['capacity_kg'].sum():,.0f} kg"
    )

    print(
        f"Total truck payload   : "
        f"{fleet['payload_capacity_kg'].sum():,.0f} kg"
    )

    print(
        f"Mean bin service time : "
        f"{bins['pickup_service_seconds'].mean():.1f} sec"
    )

    print(
        f"Mean pickups/week     : "
        f"{bins['current_pickups_per_week'].mean():.2f}"
    )

    print(f"Bins output           : {BINS_PATH}")
    print(f"Hubs output           : {HUBS_PATH}")
    print(f"Fleet output          : {FLEET_PATH}")


if __name__ == "__main__":
    main()
