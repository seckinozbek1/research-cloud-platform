from pathlib import Path
from functools import lru_cache
from itertools import count
import argparse
import heapq

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
from tqdm import tqdm


PROJECT_ROOT = Path(__file__).resolve().parents[2]

EPS = 1e-9

# Minutes from 08:00.
#
# 08:15-10:00
# 10:15-12:00
# 12:45-14:30
# 14:45-15:30
#
# = 360 usable operating minutes, matching the operations-state
# contract.
WORK_WINDOWS = [
    (15.0, 120.0),
    (135.0, 240.0),
    (285.0, 390.0),
    (405.0, 450.0),
]

PREP_END_MIN = 15.0
RETURN_DEADLINE_MIN = 450.0

SHIFT_ORIGIN_ABS_MIN = 8.0 * 60.0
RETURN_DEADLINE_ABS_MIN = (
    SHIFT_ORIGIN_ABS_MIN
    + RETURN_DEADLINE_MIN
)


def locate(filename):
    matches = list(
        PROJECT_ROOT.rglob(filename)
    )

    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one {filename}; "
            f"found {len(matches)}: {matches}"
        )

    return matches[0]


GRAPH_PATH = locate(
    "karsiyaka_street_network.graphml"
)

TRAFFIC_PATH = locate(
    "edge_vehicle_traffic_states.csv"
)

POINTS_PATH = locate(
    "karsiyaka_collection_points.geojson"
)

BIN_DEMAND_PATH = locate(
    "bin_daily_generated_waste.csv"
)

POINT_DEMAND_PATH = locate(
    "collection_point_daily_waste.csv"
)

MAPPING_PATH = locate(
    "bin_collection_point_street_map.csv"
)

FLEET_PATH = locate(
    "karsiyaka_existing_fleet.geojson"
)

OPS_STATE_PATH = locate(
    "daily_truck_crew_state.csv"
)

SERVICE_POLICY_PATH = locate(
    "utility_service_policy.csv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "waste_gis"
    / "simulation"
    / "event_driven"
)


def build_graph(
    base_graph,
    traffic,
    truck_type,
    scenario,
):
    column = (
        f"{truck_type}_{scenario}_s"
    )

    lookup = {
        (
            str(r.u),
            str(r.v),
            str(r.key),
        ): getattr(r, column)
        for r in traffic.itertuples()
    }

    graph = base_graph.copy()
    removals = []

    for u, v, key, data in graph.edges(
        keys=True,
        data=True,
    ):
        value = lookup.get(
            (
                str(u),
                str(v),
                str(key),
            )
        )

        if (
            value is None
            or not np.isfinite(value)
        ):
            removals.append(
                (u, v, key)
            )
        else:
            data["travel_time_s"] = (
                float(value)
            )

    graph.remove_edges_from(
        removals
    )

    return graph


def scenario_for_day(
    date,
    day_demand,
):
    rain_mm = float(
        day_demand[
            "rain_mm"
        ].iloc[0]
    )

    if (
        rain_mm >= 5.0
        or date.day % 9 == 0
    ):
        return "disrupted"

    if date.weekday() < 5:
        return "rush"

    return "normal"


def next_work_time(current):
    for start, end in WORK_WINDOWS:
        if start <= current < end:
            return current

        if current < start:
            return start

    return None


def available_until(current):
    for start, end in WORK_WINDOWS:
        if start <= current < end:
            return end

    return current


def clock_text(abs_minute):
    t = (
        pd.Timestamp(
            "2000-01-01"
        )
        + pd.to_timedelta(
            float(abs_minute),
            unit="m",
        )
    )

    return t.strftime(
        "%H:%M:%S"
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--policy",
        choices=[
            "nominal",
            "utility",
        ],
        required=True,
    )

    args = parser.parse_args()
    policy_name = args.policy

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ----------------------------------------------------------
    # Inputs
    # ----------------------------------------------------------

    base_graph = ox.io.load_graphml(
        GRAPH_PATH
    )

    traffic = pd.read_csv(
        TRAFFIC_PATH
    )

    points = gpd.read_file(
        POINTS_PATH
    )

    bins = pd.read_csv(
        MAPPING_PATH,
        dtype={
            "bin_id": str,
            "collection_point_id": str,
            "road_node_id": str,
        },
    )

    bins = (
        bins.drop_duplicates(
            "bin_id"
        )
        .sort_values("bin_id")
        .reset_index(drop=True)
    )

    bin_demand = pd.read_csv(
        BIN_DEMAND_PATH,
        parse_dates=["date"],
    )

    point_demand = pd.read_csv(
        POINT_DEMAND_PATH,
        parse_dates=["date"],
    )

    fleet = gpd.read_file(
        FLEET_PATH
    )

    ops = pd.read_csv(
        OPS_STATE_PATH,
        parse_dates=["date"],
    )

    utility_policy = pd.read_csv(
        SERVICE_POLICY_PATH
    )

    # ----------------------------------------------------------
    # Physical-bin model
    # ----------------------------------------------------------

    bin_ids = (
        bins["bin_id"]
        .astype(str)
        .tolist()
    )

    n_bins = len(bin_ids)

    bin_index = {
        bin_id: i
        for i, bin_id
        in enumerate(bin_ids)
    }

    bin_capacity = bins[
        "capacity_kg"
    ].to_numpy(
        dtype=np.float64
    )

    bin_id_array = bins[
        "bin_id"
    ].astype(str).to_numpy()

    bin_street_array = (
        bins["street_name"]
        .fillna("")
        .astype(str)
        .to_numpy()
    )

    cp_ids = sorted(
        points[
            "collection_point_id"
        ].astype(str).unique()
    )

    n_points = len(cp_ids)

    cp_index = {
        cp: i
        for i, cp
        in enumerate(cp_ids)
    }

    bin_cp_idx = np.array(
        [
            cp_index[cp]
            for cp in bins[
                "collection_point_id"
            ].astype(str)
        ],
        dtype=np.int64,
    )

    cp_to_bin_indices = {
        cp: np.where(
            bin_cp_idx == cp_index[cp]
        )[0]
        for cp in cp_ids
    }

    point_node = {
        str(r.collection_point_id):
            int(r.road_node_id)
        for r in points.itertuples()
    }

    point_capacity = {
        str(r.collection_point_id):
            float(r.total_capacity_kg)
        for r in points.itertuples()
    }

    point_service = {
        str(r.collection_point_id):
            float(
                r.total_service_seconds
            ) / 60.0
        for r in points.itertuples()
    }

    point_frequency = {
        str(r.collection_point_id):
            max(
                1.0,
                float(
                    r.mean_pickups_per_week
                ),
            )
        for r in points.itertuples()
    }

    # Validate physical-bin capacity decomposition.
    physical_capacity = (
        bins.groupby(
            "collection_point_id"
        )["capacity_kg"]
        .sum()
    )

    for cp in cp_ids:
        if not np.isclose(
            physical_capacity.get(
                cp,
                0.0,
            ),
            point_capacity[cp],
        ):
            raise RuntimeError(
                "Physical-bin capacity "
                f"does not match point {cp}."
            )

    # ----------------------------------------------------------
    # Utility service policy
    # ----------------------------------------------------------

    max_service_days = {
        str(r.collection_point_id):
            int(
                r.max_service_interval_days
            )
        for r in utility_policy.itertuples()
    }

    same_day_trigger = {
        str(r.collection_point_id):
            float(
                r.same_day_fill_trigger
            )
        for r in utility_policy.itertuples()
    }

    service_class = {
        str(r.collection_point_id):
            str(r.service_class)
        for r in utility_policy.itertuples()
    }

    # ----------------------------------------------------------
    # Demand matrix
    # ----------------------------------------------------------

    daily_generation = (
        bin_demand.pivot(
            index="date",
            columns="bin_id",
            values="generated_waste_kg",
        )
        .reindex(
            columns=bin_ids,
            fill_value=0.0,
        )
        .fillna(0.0)
        .sort_index()
    )

    dates = (
        daily_generation.index
    )

    # ----------------------------------------------------------
    # Fleet
    # ----------------------------------------------------------

    fleet["road_node_id"] = (
        fleet["road_node_id"]
        .astype(str)
    )

    fleet_lookup = {
        str(r.truck_id): r
        for r in fleet.itertuples()
    }

    hub_node = {}

    for r in fleet.itertuples():
        hub_node[
            str(r.hub_id)
        ] = int(
            r.road_node_id
        )

    # ----------------------------------------------------------
    # Road travel cache
    # ----------------------------------------------------------

    graph_cache = {}

    @lru_cache(
        maxsize=10000
    )
    def source_travel_times(
        truck_type,
        scenario,
        origin,
    ):
        key = (
            truck_type,
            scenario,
        )

        if key not in graph_cache:
            graph_cache[key] = (
                build_graph(
                    base_graph,
                    traffic,
                    truck_type,
                    scenario,
                )
            )

        graph = graph_cache[key]

        try:
            return (
                nx.single_source_dijkstra_path_length(
                    graph,
                    origin,
                    weight="travel_time_s",
                )
            )
        except nx.NodeNotFound:
            return {}

    def travel_minutes(
        truck_type,
        scenario,
        origin,
        destination,
    ):
        distances = (
            source_travel_times(
                truck_type,
                scenario,
                int(origin),
            )
        )

        seconds = distances.get(
            int(destination),
            np.inf,
        )

        if not np.isfinite(seconds):
            return np.inf

        return (
            float(seconds)
            / 60.0
        )

    # ----------------------------------------------------------
    # Persistent waste state
    # ----------------------------------------------------------

    bin_waste = np.zeros(
        n_bins,
        dtype=np.float64,
    )

    street_waste = np.zeros(
        n_bins,
        dtype=np.float64,
    )

    days_since_pickup = {
        cp: 0
        for cp in cp_ids
    }

    # ----------------------------------------------------------
    # Outputs
    # ----------------------------------------------------------

    daily_rows = []
    point_rows = []
    bin_rows = []

    truck_events = []
    pickup_rows = []
    bin_service_rows = []

    total_generated = 0.0
    total_collected = 0.0

    # ----------------------------------------------------------
    # Helpers over live state
    # ----------------------------------------------------------

    def point_state(cp):
        idx = cp_to_bin_indices[cp]

        bin_kg = float(
            bin_waste[idx].sum()
        )

        street_kg = float(
            street_waste[idx].sum()
        )

        total_kg = (
            bin_kg
            + street_kg
        )

        load_ratio = (
            total_kg
            / point_capacity[cp]
        )

        return (
            bin_kg,
            street_kg,
            total_kg,
            load_ratio,
        )

    def due_priority(cp):
        (
            _bin_kg,
            street_kg,
            _total_kg,
            load_ratio,
        ) = point_state(cp)

        if policy_name == "nominal":
            interval_days = max(
                1,
                round(
                    7.0
                    / point_frequency[cp]
                ),
            )

            due = (
                days_since_pickup[cp]
                >= interval_days
                or load_ratio >= 0.85
                or street_kg > EPS
            )

            priority = (
                load_ratio,
            )

            reason = (
                "overflow"
                if street_kg > EPS
                else (
                    "fill_trigger"
                    if load_ratio >= 0.85
                    else "nominal_interval"
                )
            )

            return (
                due,
                priority,
                reason,
            )

        deadline_violation = max(
            0,
            days_since_pickup[cp]
            - max_service_days[cp]
            + 1,
        )

        due = (
            days_since_pickup[cp]
            >= max_service_days[cp]
            or load_ratio
            >= same_day_trigger[cp]
            or street_kg > EPS
        )

        priority = (
            deadline_violation,
            days_since_pickup[cp],
            load_ratio,
        )

        reason = (
            "overflow"
            if street_kg > EPS
            else (
                "service_deadline"
                if (
                    days_since_pickup[cp]
                    >= max_service_days[cp]
                )
                else "fill_trigger"
            )
        )

        return (
            due,
            priority,
            reason,
        )

    def collect_point(
        cp,
        capacity_available,
        metadata,
    ):
        remaining = float(
            capacity_available
        )

        idx = cp_to_bin_indices[cp]

        collected_street = 0.0
        collected_bin = 0.0

        # Street waste first.
        for i in sorted(
            idx,
            key=lambda x:
                street_waste[x],
            reverse=True,
        ):
            if remaining <= EPS:
                break

            take = min(
                street_waste[i],
                remaining,
            )

            if take <= EPS:
                continue

            before = (
                street_waste[i]
            )

            street_waste[i] -= take
            remaining -= take
            collected_street += take

            bin_service_rows.append(
                {
                    **metadata,
                    "bin_id":
                        bin_id_array[i],
                    "street_name":
                        bin_street_array[i],
                    "source":
                        "street",
                    "collected_kg":
                        take,
                    "before_kg":
                        before,
                    "after_kg":
                        street_waste[i],
                }
            )

        # Then bin contents.
        for i in sorted(
            idx,
            key=lambda x:
                bin_waste[x],
            reverse=True,
        ):
            if remaining <= EPS:
                break

            take = min(
                bin_waste[i],
                remaining,
            )

            if take <= EPS:
                continue

            before = (
                bin_waste[i]
            )

            bin_waste[i] -= take
            remaining -= take
            collected_bin += take

            bin_service_rows.append(
                {
                    **metadata,
                    "bin_id":
                        bin_id_array[i],
                    "street_name":
                        bin_street_array[i],
                    "source":
                        "bin",
                    "collected_kg":
                        take,
                    "before_kg":
                        before,
                    "after_kg":
                        bin_waste[i],
                }
            )

        return (
            collected_street,
            collected_bin,
        )

    # ----------------------------------------------------------
    # Simulation
    # ----------------------------------------------------------

    for date in tqdm(
        dates,
        desc=(
            f"Event-driven {policy_name}"
        ),
        unit="day",
    ):
        date = pd.Timestamp(
            date
        ).normalize()

        day_point_demand = (
            point_demand[
                point_demand[
                    "date"
                ].dt.normalize()
                == date
            ]
        )

        if day_point_demand.empty:
            raise RuntimeError(
                f"No point demand for {date}."
            )

        scenario = scenario_for_day(
            date,
            day_point_demand,
        )

        day_generation = (
            daily_generation.loc[
                date
            ].to_numpy(
                dtype=np.float64,
            )
        )

        # A new calendar day has begun.
        for cp in cp_ids:
            days_since_pickup[cp] += 1

        daily_bin_kg_hours = np.zeros(
            n_bins,
            dtype=np.float64,
        )

        daily_bin_overflow_hours = (
            np.zeros(
                n_bins,
                dtype=np.float64,
            )
        )

        daily_point_overflow_hours = (
            np.zeros(
                n_points,
                dtype=np.float64,
            )
        )

        daily_peak_street_bin = (
            street_waste.copy()
        )

        daily_peak_total_street = (
            float(
                street_waste.sum()
            )
        )

        point_pickups_today = {
            cp: 0
            for cp in cp_ids
        }

        generated_today = 0.0
        collected_today = 0.0
        unloads_today = 0
        breakdowns_today = 0
        unavailable_today = 0

        # Collection-point reservation:
        # cp -> truck_id
        reservations = {}

        # ------------------------------------------------------
        # Truck state for today
        # ------------------------------------------------------

        day_ops = ops[
            ops[
                "date"
            ].dt.normalize()
            == date
        ]

        trucks = {}

        for truck_id, fleet_row in (
            fleet_lookup.items()
        ):
            state_rows = day_ops[
                day_ops["truck_id"]
                .astype(str)
                == truck_id
            ]

            if state_rows.empty:
                continue

            state = state_rows.iloc[0]

            truck = {
                "truck_id":
                    truck_id,

                "truck_type":
                    str(
                        fleet_row.truck_type
                    ),

                "hub_id":
                    str(
                        fleet_row.hub_id
                    ),

                "hub_node":
                    int(
                        fleet_row.road_node_id
                    ),

                "node":
                    int(
                        fleet_row.road_node_id
                    ),

                "payload_capacity_kg":
                    float(
                        fleet_row.payload_capacity_kg
                    ),

                "unload_time_minutes":
                    float(
                        fleet_row.unload_time_minutes
                    ),

                "payload_kg":
                    0.0,

                "operating_used":
                    0.0,

                "route_sequence":
                    0,

                "active":
                    bool(
                        state[
                            "route_operable_at_start"
                        ]
                    ),

                "breakdown":
                    bool(
                        state["breakdown"]
                    ),

                "breakdown_after_minutes":
                    (
                        float(
                            state[
                                "breakdown_after_minutes"
                            ]
                        )
                        if pd.notna(
                            state[
                                "breakdown_after_minutes"
                            ]
                        )
                        else np.inf
                    ),
            }

            trucks[truck_id] = truck

        # ------------------------------------------------------
        # Global event queue
        # ------------------------------------------------------

        heap = []
        event_counter = count()

        def push(
            minute,
            event_priority,
            event_type,
            payload,
        ):
            heapq.heappush(
                heap,
                (
                    float(minute),
                    int(event_priority),
                    next(event_counter),
                    event_type,
                    payload,
                ),
            )

        # Uniform arrival baseline:
        # 1/24 of each bin's daily waste at hourly midpoint.
        for hour in range(24):
            push(
                30.0 + 60.0 * hour,
                0,
                "waste",
                hour,
            )

        # Initial truck decisions.
        for truck_id, truck in (
            trucks.items()
        ):
            state = day_ops[
                day_ops["truck_id"]
                .astype(str)
                == truck_id
            ].iloc[0]

            if not truck["active"]:
                unavailable_today += 1

                truck_events.append(
                    {
                        "date":
                            date.date().isoformat(),

                        "truck_id":
                            truck_id,

                        "event_type":
                            "unavailable",

                        "time":
                            "08:00:00",

                        "scenario":
                            scenario,

                        "reason":
                            "crew_or_vehicle_unavailable",
                    }
                )

                continue

            start_rel = (
                PREP_END_MIN
                + float(
                    state[
                        "crew_late_minutes"
                    ]
                )
                + float(
                    state[
                        "fault_delay_minutes"
                    ]
                )
            )

            push(
                SHIFT_ORIGIN_ABS_MIN
                + start_rel,
                2,
                "decision",
                {
                    "truck_id":
                        truck_id,
                },
            )

        # Explicit end of day.
        push(
            1440.0,
            9,
            "day_end",
            None,
        )

        last_time = 0.0

        def next_waste_after(now):
            for hour in range(24):
                t = (
                    30.0
                    + 60.0 * hour
                )

                if t > now + EPS:
                    return (
                        t + 0.001
                    )

            return None

        def select_candidate(
            truck,
            now_rel,
        ):
            ranked = []

            due_count = 0

            for cp in cp_ids:
                (
                    due,
                    priority,
                    reason,
                ) = due_priority(cp)

                if not due:
                    continue

                due_count += 1

                if cp in reservations:
                    continue

                ranked.append(
                    (
                        priority,
                        cp,
                        reason,
                    )
                )

            ranked.sort(
                key=lambda x: x[0],
                reverse=True,
            )

            # Same computational architecture as the
            # existing utility scheduler:
            # exact-road-route only the most urgent 15.
            candidates = ranked[:15]

            window_end = (
                available_until(
                    now_rel
                )
            )

            feasible = []

            for (
                priority,
                cp,
                reason,
            ) in candidates:
                travel = travel_minutes(
                    truck["truck_type"],
                    scenario,
                    truck["node"],
                    point_node[cp],
                )

                if not np.isfinite(travel):
                    continue

                return_time = travel_minutes(
                    truck["truck_type"],
                    scenario,
                    point_node[cp],
                    truck["hub_node"],
                )

                if not np.isfinite(
                    return_time
                ):
                    continue

                service = (
                    point_service[cp]
                )

                finish_service = (
                    now_rel
                    + travel
                    + service
                )

                if (
                    finish_service
                    > window_end
                ):
                    continue

                if (
                    finish_service
                    + return_time
                    > RETURN_DEADLINE_MIN
                ):
                    continue

                feasible.append(
                    (
                        travel,
                        cp,
                        reason,
                        priority,
                        service,
                        return_time,
                    )
                )

            if not feasible:
                return (
                    None,
                    due_count,
                )

            # Among the urgent feasible set,
            # use marginal road travel as tie-break.
            selected = min(
                feasible,
                key=lambda x: x[0],
            )

            return (
                selected,
                due_count,
            )

        # ------------------------------------------------------
        # Global chronological execution
        # ------------------------------------------------------

        while heap:
            (
                now,
                _event_priority,
                _event_seq,
                event_type,
                payload,
            ) = heapq.heappop(heap)

            elapsed_hours = (
                now - last_time
            ) / 60.0

            if elapsed_hours < -EPS:
                raise RuntimeError(
                    "Global event clock moved backwards."
                )

            if elapsed_hours > 0:
                exposure = (
                    street_waste
                    * elapsed_hours
                )

                daily_bin_kg_hours += (
                    exposure
                )

                daily_bin_overflow_hours += (
                    (
                        street_waste > EPS
                    ).astype(np.float64)
                    * elapsed_hours
                )

                point_street_now = (
                    np.bincount(
                        bin_cp_idx,
                        weights=street_waste,
                        minlength=n_points,
                    )
                )

                daily_point_overflow_hours += (
                    (
                        point_street_now
                        > EPS
                    ).astype(np.float64)
                    * elapsed_hours
                )

            last_time = now

            # --------------------------------------------------
            # Waste arrival
            # --------------------------------------------------

            if event_type == "waste":
                arriving = (
                    day_generation
                    / 24.0
                )

                generated_today += float(
                    arriving.sum()
                )

                total_generated += float(
                    arriving.sum()
                )

                free_capacity = (
                    np.maximum(
                        bin_capacity
                        - bin_waste,
                        0.0,
                    )
                )

                into_bin = np.minimum(
                    arriving,
                    free_capacity,
                )

                into_street = (
                    arriving
                    - into_bin
                )

                bin_waste += into_bin
                street_waste += into_street

            # --------------------------------------------------
            # Scheduler decision
            # --------------------------------------------------

            elif event_type == "decision":
                truck_id = (
                    payload["truck_id"]
                )

                truck = trucks[
                    truck_id
                ]

                if not truck["active"]:
                    continue

                now_rel = (
                    now
                    - SHIFT_ORIGIN_ABS_MIN
                )

                adjusted = (
                    next_work_time(
                        now_rel
                    )
                )

                if (
                    adjusted is None
                    or adjusted
                    >= RETURN_DEADLINE_MIN
                ):
                    truck["active"] = False

                    truck_events.append(
                        {
                            "date":
                                date.date().isoformat(),

                            "truck_id":
                                truck_id,

                            "event_type":
                                "route_end",

                            "time":
                                clock_text(now),

                            "scenario":
                                scenario,

                            "payload_kg":
                                truck[
                                    "payload_kg"
                                ],
                        }
                    )

                    continue

                if adjusted > now_rel + EPS:
                    push(
                        SHIFT_ORIGIN_ABS_MIN
                        + adjusted,
                        2,
                        "decision",
                        {
                            "truck_id":
                                truck_id,
                        },
                    )

                    continue

                if (
                    truck["breakdown"]
                    and truck[
                        "operating_used"
                    ]
                    >= truck[
                        "breakdown_after_minutes"
                    ]
                ):
                    truck["active"] = False
                    breakdowns_today += 1

                    truck_events.append(
                        {
                            "date":
                                date.date().isoformat(),

                            "truck_id":
                                truck_id,

                            "event_type":
                                "breakdown",

                            "time":
                                clock_text(now),

                            "scenario":
                                scenario,

                            "operating_used":
                                truck[
                                    "operating_used"
                                ],
                        }
                    )

                    continue

                (
                    selection,
                    due_count,
                ) = select_candidate(
                    truck,
                    now_rel,
                )

                if selection is None:
                    if due_count > 0:
                        target_rel = min(
                            now_rel + 10.0,
                            available_until(
                                now_rel
                            ),
                        )

                        target = (
                            SHIFT_ORIGIN_ABS_MIN
                            + target_rel
                        )
                    else:
                        target = (
                            next_waste_after(
                                now
                            )
                        )

                    if (
                        target is None
                        or target
                        >= RETURN_DEADLINE_ABS_MIN
                    ):
                        truck["active"] = False
                        continue

                    if target <= now + EPS:
                        target = now + 0.01

                    push(
                        target,
                        2,
                        "decision",
                        {
                            "truck_id":
                                truck_id,
                        },
                    )

                    continue

                (
                    travel,
                    cp,
                    reason,
                    priority,
                    service_minutes,
                    _return_minutes,
                ) = selection

                (
                    _cp_bin,
                    _cp_street,
                    cp_total,
                    _cp_ratio,
                ) = point_state(cp)

                remaining_payload = (
                    truck[
                        "payload_capacity_kg"
                    ]
                    - truck["payload_kg"]
                )

                # Existing operational rule:
                # if the selected point cannot be cleared with the
                # remaining payload, unload before attempting it.
                if (
                    truck["payload_kg"] > EPS
                    and cp_total
                    > remaining_payload
                ):
                    back_to_hub = travel_minutes(
                        truck["truck_type"],
                        scenario,
                        truck["node"],
                        truck["hub_node"],
                    )

                    if not np.isfinite(
                        back_to_hub
                    ):
                        truck["active"] = False
                        continue

                    unload_leg = (
                        back_to_hub
                        + truck[
                            "unload_time_minutes"
                        ]
                    )

                    window_end = (
                        available_until(
                            now_rel
                        )
                    )

                    if (
                        now_rel
                        + unload_leg
                        > window_end
                    ):
                        push(
                            SHIFT_ORIGIN_ABS_MIN
                            + window_end,
                            2,
                            "decision",
                            {
                                "truck_id":
                                    truck_id,
                            },
                        )

                        continue

                    push(
                        now + unload_leg,
                        1,
                        "unload_complete",
                        {
                            "truck_id":
                                truck_id,

                            "travel_minutes":
                                back_to_hub,

                            "unload_minutes":
                                truck[
                                    "unload_time_minutes"
                                ],
                        },
                    )

                    continue

                # Reserve this point while the truck travels.
                reservations[cp] = truck_id

                truck_events.append(
                    {
                        "date":
                            date.date().isoformat(),

                        "truck_id":
                            truck_id,

                        "event_type":
                            "dispatch",

                        "time":
                            clock_text(now),

                        "scenario":
                            scenario,

                        "collection_point_id":
                            cp,

                        "reason":
                            reason,

                        "priority":
                            str(priority),

                        "travel_minutes":
                            travel,

                        "payload_kg":
                            truck[
                                "payload_kg"
                            ],
                    }
                )

                push(
                    now
                    + travel
                    + service_minutes,
                    1,
                    "pickup_complete",
                    {
                        "truck_id":
                            truck_id,

                        "collection_point_id":
                            cp,

                        "travel_minutes":
                            travel,

                        "service_minutes":
                            service_minutes,

                        "reason":
                            reason,
                    },
                )

            # --------------------------------------------------
            # Hub unload
            # --------------------------------------------------

            elif event_type == "unload_complete":
                truck_id = (
                    payload["truck_id"]
                )

                truck = trucks[
                    truck_id
                ]

                unloaded = (
                    truck["payload_kg"]
                )

                truck["node"] = (
                    truck["hub_node"]
                )

                truck[
                    "operating_used"
                ] += (
                    payload[
                        "travel_minutes"
                    ]
                    + payload[
                        "unload_minutes"
                    ]
                )

                truck["payload_kg"] = (
                    0.0
                )

                unloads_today += 1

                truck_events.append(
                    {
                        "date":
                            date.date().isoformat(),

                        "truck_id":
                            truck_id,

                        "event_type":
                            "unload",

                        "time":
                            clock_text(now),

                        "scenario":
                            scenario,

                        "unloaded_kg":
                            unloaded,
                    }
                )

                push(
                    now,
                    2,
                    "decision",
                    {
                        "truck_id":
                            truck_id,
                    },
                )

            # --------------------------------------------------
            # Collection-point service completes
            # --------------------------------------------------

            elif event_type == "pickup_complete":
                truck_id = (
                    payload["truck_id"]
                )

                cp = payload[
                    "collection_point_id"
                ]

                truck = trucks[
                    truck_id
                ]

                if (
                    reservations.get(cp)
                    == truck_id
                ):
                    reservations.pop(
                        cp,
                        None,
                    )

                truck["node"] = (
                    point_node[cp]
                )

                truck[
                    "operating_used"
                ] += (
                    payload[
                        "travel_minutes"
                    ]
                    + payload[
                        "service_minutes"
                    ]
                )

                (
                    before_bin,
                    before_street,
                    _before_total,
                    _before_ratio,
                ) = point_state(cp)

                remaining_payload = (
                    truck[
                        "payload_capacity_kg"
                    ]
                    - truck["payload_kg"]
                )

                truck[
                    "route_sequence"
                ] += 1

                metadata = {
                    "date":
                        date.date().isoformat(),

                    "time":
                        clock_text(now),

                    "truck_id":
                        truck_id,

                    "truck_type":
                        truck[
                            "truck_type"
                        ],

                    "hub_id":
                        truck[
                            "hub_id"
                        ],

                    "scenario":
                        scenario,

                    "collection_point_id":
                        cp,

                    "route_sequence":
                        truck[
                            "route_sequence"
                        ],
                }

                (
                    collected_street,
                    collected_bin,
                ) = collect_point(
                    cp,
                    remaining_payload,
                    metadata,
                )

                collected = (
                    collected_street
                    + collected_bin
                )

                truck["payload_kg"] += (
                    collected
                )

                collected_today += (
                    collected
                )

                total_collected += (
                    collected
                )

                point_pickups_today[
                    cp
                ] += 1

                (
                    after_bin,
                    after_street,
                    after_total,
                    after_ratio,
                ) = point_state(cp)

                if after_total <= EPS:
                    days_since_pickup[
                        cp
                    ] = 0

                    service_status = (
                        "cleared"
                    )

                elif after_street > EPS:
                    service_status = (
                        "street_remaining"
                    )

                else:
                    service_status = (
                        "partial_bin_service"
                    )

                pickup_rows.append(
                    {
                        **metadata,

                        "reason":
                            payload[
                                "reason"
                            ],

                        "before_bin_kg":
                            before_bin,

                        "before_street_kg":
                            before_street,

                        "collected_street_kg":
                            collected_street,

                        "collected_bin_kg":
                            collected_bin,

                        "collected_total_kg":
                            collected,

                        "after_bin_kg":
                            after_bin,

                        "after_street_kg":
                            after_street,

                        "after_total_kg":
                            after_total,

                        "after_load_ratio":
                            after_ratio,

                        "truck_payload_kg":
                            truck[
                                "payload_kg"
                            ],

                        "truck_remaining_payload_kg":
                            truck[
                                "payload_capacity_kg"
                            ]
                            - truck[
                                "payload_kg"
                            ],

                        "service_status":
                            service_status,
                    }
                )

                truck_events.append(
                    {
                        **metadata,

                        "event_type":
                            "pickup",

                        "collected_kg":
                            collected,

                        "street_collected_kg":
                            collected_street,

                        "bin_collected_kg":
                            collected_bin,

                        "remaining_street_kg":
                            after_street,

                        "remaining_total_kg":
                            after_total,

                        "payload_kg":
                            truck[
                                "payload_kg"
                            ],

                        "service_status":
                            service_status,
                    }
                )

                if (
                    truck["breakdown"]
                    and truck[
                        "operating_used"
                    ]
                    >= truck[
                        "breakdown_after_minutes"
                    ]
                ):
                    truck["active"] = False
                    breakdowns_today += 1

                    truck_events.append(
                        {
                            "date":
                                date.date().isoformat(),

                            "truck_id":
                                truck_id,

                            "event_type":
                                "breakdown",

                            "time":
                                clock_text(now),

                            "scenario":
                                scenario,

                            "operating_used":
                                truck[
                                    "operating_used"
                                ],
                        }
                    )

                    continue

                push(
                    now,
                    2,
                    "decision",
                    {
                        "truck_id":
                            truck_id,
                    },
                )

            elif event_type == "day_end":
                pass

            else:
                raise RuntimeError(
                    f"Unknown event: "
                    f"{event_type}"
                )

            daily_peak_street_bin = (
                np.maximum(
                    daily_peak_street_bin,
                    street_waste,
                )
            )

            daily_peak_total_street = (
                max(
                    daily_peak_total_street,
                    float(
                        street_waste.sum()
                    ),
                )
            )

        # ------------------------------------------------------
        # Day-end diagnostics
        # ------------------------------------------------------

        cp_bin = np.bincount(
            bin_cp_idx,
            weights=bin_waste,
            minlength=n_points,
        )

        cp_street = np.bincount(
            bin_cp_idx,
            weights=street_waste,
            minlength=n_points,
        )

        cp_kg_hours = np.bincount(
            bin_cp_idx,
            weights=daily_bin_kg_hours,
            minlength=n_points,
        )

        end_bin = float(
            bin_waste.sum()
        )

        end_street = float(
            street_waste.sum()
        )

        daily_rows.append(
            {
                "date":
                    date.date().isoformat(),

                "policy":
                    policy_name,

                "scenario":
                    scenario,

                "generated_waste_kg":
                    generated_today,

                "collected_waste_kg":
                    collected_today,

                "end_bin_waste_kg":
                    end_bin,

                "end_street_waste_kg":
                    end_street,

                "end_total_backlog_kg":
                    end_bin
                    + end_street,

                "street_waste_kg_hours":
                    float(
                        daily_bin_kg_hours.sum()
                    ),

                "overflow_bin_hours":
                    float(
                        daily_bin_overflow_hours.sum()
                    ),

                "overflow_point_hours":
                    float(
                        daily_point_overflow_hours.sum()
                    ),

                "overflow_bins_end":
                    int(
                        (
                            street_waste > EPS
                        ).sum()
                    ),

                "overflow_points_end":
                    int(
                        (
                            cp_street > EPS
                        ).sum()
                    ),

                "peak_street_waste_kg":
                    daily_peak_total_street,

                "pickup_events":
                    int(
                        sum(
                            point_pickups_today.values()
                        )
                    ),

                "unload_events":
                    unloads_today,

                "breakdowns":
                    breakdowns_today,

                "unavailable_trucks":
                    unavailable_today,
            }
        )

        for cp in cp_ids:
            j = cp_index[cp]

            if cp_street[j] > EPS:
                status = "overflow"
            elif cp_bin[j] > EPS:
                status = "bin_backlog"
            else:
                status = "clear"

            street_names = sorted(
                set(
                    bins.loc[
                        bins[
                            "collection_point_id"
                        ].astype(str)
                        == cp,
                        "street_name",
                    ]
                    .dropna()
                    .astype(str)
                )
            )

            point_rows.append(
                {
                    "date":
                        date.date().isoformat(),

                    "policy":
                        policy_name,

                    "collection_point_id":
                        cp,

                    "street_name":
                        " | ".join(
                            street_names
                        ),

                    "service_class":
                        service_class.get(
                            cp,
                            "",
                        ),

                    "capacity_kg":
                        point_capacity[cp],

                    "bin_waste_kg":
                        cp_bin[j],

                    "street_waste_kg":
                        cp_street[j],

                    "total_waste_kg":
                        cp_bin[j]
                        + cp_street[j],

                    "system_load_ratio":
                        (
                            cp_bin[j]
                            + cp_street[j]
                        )
                        / point_capacity[cp],

                    "street_waste_kg_hours":
                        cp_kg_hours[j],

                    "overflow_hours":
                        daily_point_overflow_hours[
                            j
                        ],

                    "pickups_today":
                        point_pickups_today[
                            cp
                        ],

                    "days_since_pickup":
                        days_since_pickup[
                            cp
                        ],

                    "status":
                        status,
                }
            )

        for i, bin_id in enumerate(
            bin_ids
        ):
            bin_rows.append(
                {
                    "date":
                        date.date().isoformat(),

                    "policy":
                        policy_name,

                    "bin_id":
                        bin_id,

                    "collection_point_id":
                        bins.iloc[i][
                            "collection_point_id"
                        ],

                    "street_name":
                        bin_street_array[i],

                    "capacity_kg":
                        bin_capacity[i],

                    "bin_waste_kg":
                        bin_waste[i],

                    "street_waste_kg":
                        street_waste[i],

                    "street_waste_kg_hours":
                        daily_bin_kg_hours[i],

                    "overflow_hours":
                        daily_bin_overflow_hours[
                            i
                        ],

                    "peak_street_waste_kg":
                        daily_peak_street_bin[
                            i
                        ],
                }
            )

    # ----------------------------------------------------------
    # Save
    # ----------------------------------------------------------

    daily_df = pd.DataFrame(
        daily_rows
    )

    point_df = pd.DataFrame(
        point_rows
    )

    bin_df = pd.DataFrame(
        bin_rows
    )

    truck_df = pd.DataFrame(
        truck_events
    )

    pickup_df = pd.DataFrame(
        pickup_rows
    )

    bin_service_df = pd.DataFrame(
        bin_service_rows
    )

    prefix = (
        f"closed_loop_{policy_name}"
    )

    daily_path = (
        OUTPUT_DIR
        / f"{prefix}_daily_summary.csv"
    )

    point_path = (
        OUTPUT_DIR
        / f"{prefix}_point_outcomes.csv"
    )

    bin_path = (
        OUTPUT_DIR
        / f"{prefix}_bin_outcomes.csv"
    )

    truck_path = (
        OUTPUT_DIR
        / f"{prefix}_truck_events.csv"
    )

    pickup_path = (
        OUTPUT_DIR
        / f"{prefix}_pickup_attribution.csv"
    )

    service_path = (
        OUTPUT_DIR
        / f"{prefix}_bin_service_events.csv"
    )

    daily_df.to_csv(
        daily_path,
        index=False,
    )

    point_df.to_csv(
        point_path,
        index=False,
    )

    bin_df.to_csv(
        bin_path,
        index=False,
    )

    truck_df.to_csv(
        truck_path,
        index=False,
    )

    pickup_df.to_csv(
        pickup_path,
        index=False,
    )

    bin_service_df.to_csv(
        service_path,
        index=False,
    )

    final_backlog = (
        float(
            bin_waste.sum()
            + street_waste.sum()
        )
    )

    mass_balance_error = (
        total_generated
        - total_collected
        - final_backlog
    )

    print()
    print(
        "Closed-loop simulation complete:",
        policy_name,
    )

    print(
        "Generated waste       :",
        f"{total_generated/1000:,.1f} tonnes",
    )

    print(
        "Collected waste       :",
        f"{total_collected/1000:,.1f} tonnes",
    )

    print(
        "Final backlog         :",
        f"{final_backlog/1000:,.1f} tonnes",
    )

    print(
        "Final street waste    :",
        f"{street_waste.sum()/1000:,.1f} tonnes",
    )

    print(
        "Street-waste kg-hours :",
        f"{daily_df['street_waste_kg_hours'].sum():,.0f}",
    )

    print(
        "Overflow point-hours  :",
        f"{daily_df['overflow_point_hours'].sum():,.1f}",
    )

    print(
        "Peak street waste     :",
        f"{daily_df['peak_street_waste_kg'].max()/1000:,.1f} tonnes",
    )

    print(
        "Pickup events         :",
        f"{int(daily_df['pickup_events'].sum()):,}",
    )

    print(
        "Mass-balance error kg :",
        f"{mass_balance_error:.9f}",
    )

    print()
    print("Daily summary         :", daily_path)
    print("Point outcomes        :", point_path)
    print("Bin outcomes          :", bin_path)
    print("Truck events          :", truck_path)
    print("Pickup attribution    :", pickup_path)
    print("Bin service events    :", service_path)


if __name__ == "__main__":
    main()
