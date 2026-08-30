from pathlib import Path
from functools import lru_cache
import ast

import geopandas as gpd
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
from tqdm import tqdm


PROJECT_ROOT = Path(__file__).resolve().parents[2]

GRAPH_PATH = (
    PROJECT_ROOT
    / "data"
    / "gis"
    / "karsiyaka_street_network.graphml"
)

TRAFFIC_PATH = (
    PROJECT_ROOT
    / "data"
    / "gis"
    / "traffic_scenarios"
    / "edge_vehicle_traffic_states.csv"
)

POINTS_PATH = (
    PROJECT_ROOT
    / "data"
    / "gis"
    / "karsiyaka_collection_points.geojson"
)

POINT_DEMAND_PATH = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "waste_gis"
    / "scheduler"
    / "collection_point_daily_waste.csv"
)

FLEET_PATH = (
    PROJECT_ROOT
    / "data"
    / "gis"
    / "karsiyaka_existing_fleet.geojson"
)

HUBS_PATH = (
    PROJECT_ROOT
    / "data"
    / "gis"
    / "karsiyaka_existing_hubs.geojson"
)

OPS_STATE_PATH = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "waste_gis"
    / "operations_state"
    / "daily_truck_crew_state.csv"
)

OUTPUT_DIR = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "waste_gis"
    / "simulation"
)

DAILY_OUTPUT = OUTPUT_DIR / "baseline_daily_summary.csv"
EVENT_OUTPUT = OUTPUT_DIR / "baseline_route_events.csv"
POINT_OUTPUT = OUTPUT_DIR / "baseline_point_outcomes.csv"


# --------------------------------------------------------------
# Human work schedule.
# Minutes are absolute from 08:00.
# --------------------------------------------------------------

WORK_WINDOWS = [
    (15, 135),    # 08:15–10:15
    (150, 240),   # 10:30–12:00
    (285, 390),   # 12:45–14:30
    (405, 450),   # 14:45–15:30
]

SHIFT_END_MIN = 480

PREP_END_MIN = 15
RETURN_DEADLINE_MIN = 450

# Fill ratio that creates an urgent pickup even if nominal
# pickup frequency says the point is not yet due.
URGENT_FILL_RATIO = 0.85


def scalar(value):
    """Extract a stable scalar from OSM list-like attributes."""
    if isinstance(value, list):
        return value[0] if value else None

    if isinstance(value, str):
        text = value.strip()

        if text.startswith("[") and text.endswith("]"):
            try:
                parsed = ast.literal_eval(text)
                if isinstance(parsed, list) and parsed:
                    return parsed[0]
            except (ValueError, SyntaxError):
                pass

    return value


def build_graph(base_graph, traffic, truck_type, scenario):
    column = f"{truck_type}_{scenario}_s"

    lookup = {
        (str(r.u), str(r.v), str(r.key)): getattr(r, column)
        for r in traffic.itertuples()
    }

    graph = base_graph.copy()

    removals = []

    for u, v, key, data in graph.edges(
        keys=True,
        data=True,
    ):
        value = lookup.get(
            (str(u), str(v), str(key))
        )

        if value is None or not np.isfinite(value):
            removals.append((u, v, key))
        else:
            data["travel_time_s"] = float(value)

    graph.remove_edges_from(removals)

    return graph


def scenario_for_day(date, day_demand):
    """
    Simple first-pass context rule.

    Rainy days or deterministic periodic disruption days use the
    disrupted graph. Weekday collection otherwise uses rush because
    much of the municipal shift overlaps urban traffic periods.
    Weekends use normal.
    """
    rain_mm = float(day_demand["rain_mm"].iloc[0])

    if rain_mm >= 5.0 or date.day % 9 == 0:
        return "disrupted"

    if date.weekday() < 5:
        return "rush"

    return "normal"


def next_work_time(current):
    """Move clock forward through mandatory break/lunch periods."""
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


def event(
    events,
    date,
    truck_id,
    event_type,
    minute,
    **kwargs,
):
    row = {
        "date": date.isoformat(),
        "truck_id": truck_id,
        "event_type": event_type,
        "minute_from_0800": round(float(minute), 2),
    }

    row.update(kwargs)
    events.append(row)


def main():
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    base_graph = ox.io.load_graphml(GRAPH_PATH)

    traffic = pd.read_csv(TRAFFIC_PATH)
    points = gpd.read_file(POINTS_PATH)
    demand = pd.read_csv(POINT_DEMAND_PATH)
    fleet = gpd.read_file(FLEET_PATH)
    hubs = gpd.read_file(HUBS_PATH)
    ops = pd.read_csv(OPS_STATE_PATH)

    demand["date"] = pd.to_datetime(demand["date"])
    ops["date"] = pd.to_datetime(ops["date"])

    point_node = {
        r.collection_point_id: int(r.road_node_id)
        for r in points.itertuples()
    }

    point_capacity = {
        r.collection_point_id: float(r.total_capacity_kg)
        for r in points.itertuples()
    }

    point_service = {
        r.collection_point_id: float(r.total_service_seconds) / 60.0
        for r in points.itertuples()
    }

    point_frequency = {
        r.collection_point_id: max(
            1.0,
            float(r.mean_pickups_per_week),
        )
        for r in points.itertuples()
    }

    hub_node = {
        r.hub_id: int(r.road_node_id)
        for r in hubs.itertuples()
    }

    # Waste currently sitting at each collection point.
    fill_kg = {
        cp: 0.0
        for cp in point_node
    }

    # Days since last collection.
    days_since_pickup = {
        cp: 0
        for cp in point_node
    }

    route_events = []
    point_outcomes = []
    daily_summaries = []

    graph_cache = {}

    @lru_cache(maxsize=10000)
    def source_travel_times(
        truck_type,
        scenario,
        origin,
    ):
        """
        Run Dijkstra ONCE per origin/truck/scenario and cache the
        resulting distance map.

        This avoids running a new shortest-path search for every
        candidate destination.
        """
        key = (truck_type, scenario)

        if key not in graph_cache:
            graph_cache[key] = build_graph(
                base_graph,
                traffic,
                truck_type,
                scenario,
            )

        graph = graph_cache[key]

        try:
            distances = nx.single_source_dijkstra_path_length(
                graph,
                origin,
                weight="travel_time_s",
            )
        except nx.NodeNotFound:
            return {}

        return distances


    def travel_minutes(
        truck_type,
        scenario,
        origin,
        destination,
    ):
        distances = source_travel_times(
            truck_type,
            scenario,
            origin,
        )

        seconds = distances.get(
            destination,
            np.inf,
        )

        return (
            float(seconds) / 60.0
            if np.isfinite(seconds)
            else np.inf
        )

    dates = sorted(demand["date"].dt.date.unique())

    for date_value in tqdm(
        dates,
        desc="Simulating days",
        unit="day",
    ):
        date = pd.Timestamp(date_value)

        day_demand = demand[
            demand["date"].dt.date == date_value
        ].copy()

        scenario = scenario_for_day(
            date,
            day_demand,
        )

        # ----------------------------------------------------------
        # Waste generation enters the system at start of day.
        # ----------------------------------------------------------

        generated_today = 0.0

        for row in day_demand.itertuples():
            cp = row.collection_point_id

            generated = float(
                row.generated_waste_kg
            )

            fill_kg[cp] += generated
            generated_today += generated

            days_since_pickup[cp] += 1

        # ----------------------------------------------------------
        # Current-system pickup policy:
        #
        # nominal frequency +
        # urgent collection when approaching capacity.
        # ----------------------------------------------------------

        due_points = set()

        for cp in point_node:
            interval_days = max(
                1,
                round(
                    7.0
                    / point_frequency[cp]
                ),
            )

            fill_ratio = (
                fill_kg[cp]
                / point_capacity[cp]
            )

            if (
                days_since_pickup[cp] >= interval_days
                or fill_ratio >= URGENT_FILL_RATIO
            ):
                due_points.add(cp)

        collected_today = 0.0
        service_count = 0
        unload_count = 0
        breakdown_count = 0

        truck_day = ops[
            ops["date"].dt.date == date_value
        ]

        # ----------------------------------------------------------
        # Each available crew + truck gets a route.
        # ----------------------------------------------------------

        for truck in fleet.itertuples():
            state_rows = truck_day[
                truck_day["truck_id"]
                == truck.truck_id
            ]

            if state_rows.empty:
                continue

            state = state_rows.iloc[0]

            if not bool(
                state["route_operable_at_start"]
            ):
                event(
                    route_events,
                    date_value,
                    truck.truck_id,
                    "unavailable",
                    0,
                    reason=(
                        "crew_or_vehicle_unavailable"
                    ),
                )
                continue

            current_node = hub_node[
                truck.hub_id
            ]

            current_minute = float(
                PREP_END_MIN
                + state["crew_late_minutes"]
                + state["fault_delay_minutes"]
            )

            payload_kg = 0.0
            operating_used = 0.0

            if bool(state["crew_late"]):
                event(
                    route_events,
                    date_value,
                    truck.truck_id,
                    "late_start",
                    current_minute,
                    delay_minutes=float(
                        state["crew_late_minutes"]
                    ),
                )

            if bool(state["minor_fault"]):
                event(
                    route_events,
                    date_value,
                    truck.truck_id,
                    "minor_fault_delay",
                    current_minute,
                    delay_minutes=float(
                        state["fault_delay_minutes"]
                    ),
                )

            broke_down = False

            while due_points:
                adjusted_minute = next_work_time(
                    current_minute
                )

                if adjusted_minute is None:
                    break

                current_minute = adjusted_minute

                if current_minute >= RETURN_DEADLINE_MIN:
                    break

                # ----------------------------------------------
                # Breakdown occurs after a certain amount of
                # actual operating time.
                # ----------------------------------------------

                if bool(state["breakdown"]):
                    threshold = float(
                        state[
                            "breakdown_after_minutes"
                        ]
                    )

                    if operating_used >= threshold:
                        event(
                            route_events,
                            date_value,
                            truck.truck_id,
                            "breakdown",
                            current_minute,
                        )

                        breakdown_count += 1
                        broke_down = True
                        break

                # ----------------------------------------------
                # Choose next point:
                # highest fill pressure among a local candidate
                # set, then nearest by road travel time.
                # ----------------------------------------------

                priorities = sorted(
                    due_points,
                    key=lambda cp: (
                        fill_kg[cp]
                        / point_capacity[cp]
                    ),
                    reverse=True,
                )

                candidate_points = priorities[:15]

                options = []

                for cp in candidate_points:
                    t = travel_minutes(
                        truck.truck_type,
                        scenario,
                        current_node,
                        point_node[cp],
                    )

                    if np.isfinite(t):
                        options.append(
                            (t, cp)
                        )

                if not options:
                    break

                travel_to_point, cp = min(
                    options,
                    key=lambda x: x[0],
                )

                waste_available = fill_kg[cp]

                remaining_payload = (
                    float(
                        truck.payload_capacity_kg
                    )
                    - payload_kg
                )

                # ----------------------------------------------
                # Need to unload before servicing this point.
                # ----------------------------------------------

                if (
                    payload_kg > 0
                    and waste_available
                    > remaining_payload
                ):
                    back_to_hub = travel_minutes(
                        truck.truck_type,
                        scenario,
                        current_node,
                        hub_node[truck.hub_id],
                    )

                    if not np.isfinite(back_to_hub):
                        break

                    leg = (
                        back_to_hub
                        + float(
                            truck.unload_time_minutes
                        )
                    )

                    window_end = available_until(
                        current_minute
                    )

                    if current_minute + leg > window_end:
                        current_minute = window_end
                        continue

                    current_minute += leg
                    operating_used += leg

                    event(
                        route_events,
                        date_value,
                        truck.truck_id,
                        "unload",
                        current_minute,
                        payload_kg=round(
                            payload_kg,
                            2,
                        ),
                    )

                    unload_count += 1
                    payload_kg = 0.0
                    current_node = hub_node[
                        truck.hub_id
                    ]
                    continue

                service_minutes = (
                    point_service[cp]
                )

                leg_minutes = (
                    travel_to_point
                    + service_minutes
                )

                # ----------------------------------------------
                # Do not start work that crosses a mandatory
                # break/lunch boundary.
                # ----------------------------------------------

                window_end = available_until(
                    current_minute
                )

                if (
                    current_minute
                    + leg_minutes
                    > window_end
                ):
                    current_minute = window_end
                    continue

                # ----------------------------------------------
                # Must still be able to return before closeout.
                # ----------------------------------------------

                return_minutes = travel_minutes(
                    truck.truck_type,
                    scenario,
                    point_node[cp],
                    hub_node[truck.hub_id],
                )

                if not np.isfinite(return_minutes):
                    due_points.discard(cp)
                    continue

                if (
                    current_minute
                    + leg_minutes
                    + return_minutes
                    > RETURN_DEADLINE_MIN
                ):
                    break

                current_minute += (
                    travel_to_point
                )

                operating_used += (
                    travel_to_point
                )

                current_node = point_node[cp]

                collectable = min(
                    fill_kg[cp],
                    float(
                        truck.payload_capacity_kg
                    )
                    - payload_kg,
                )

                current_minute += (
                    service_minutes
                )

                operating_used += (
                    service_minutes
                )

                payload_kg += collectable
                fill_kg[cp] -= collectable

                collected_today += collectable
                service_count += 1

                event(
                    route_events,
                    date_value,
                    truck.truck_id,
                    "pickup",
                    current_minute,
                    collection_point_id=cp,
                    collected_kg=round(
                        collectable,
                        2,
                    ),
                    remaining_fill_kg=round(
                        fill_kg[cp],
                        2,
                    ),
                    payload_kg=round(
                        payload_kg,
                        2,
                    ),
                )

                # Point is considered serviced only when the
                # current accumulated waste was fully removed.
                if fill_kg[cp] <= 1e-6:
                    fill_kg[cp] = 0.0
                    days_since_pickup[cp] = 0
                    due_points.discard(cp)

                # Breakdown may happen immediately after service.
                if bool(state["breakdown"]):
                    threshold = float(
                        state[
                            "breakdown_after_minutes"
                        ]
                    )

                    if operating_used >= threshold:
                        event(
                            route_events,
                            date_value,
                            truck.truck_id,
                            "breakdown",
                            current_minute,
                        )

                        breakdown_count += 1
                        broke_down = True
                        break

            # --------------------------------------------------
            # Return to hub when route ends, unless broken down.
            # --------------------------------------------------

            if not broke_down:
                return_minutes = travel_minutes(
                    truck.truck_type,
                    scenario,
                    current_node,
                    hub_node[truck.hub_id],
                )

                if np.isfinite(return_minutes):
                    current_minute += (
                        return_minutes
                    )

                    operating_used += (
                        return_minutes
                    )

                    event(
                        route_events,
                        date_value,
                        truck.truck_id,
                        "return_to_hub",
                        current_minute,
                    )

        # ----------------------------------------------------------
        # End-of-day outcomes.
        # ----------------------------------------------------------

        overflow_kg = 0.0
        overflow_points = 0

        for cp in point_node:
            overflow = max(
                0.0,
                fill_kg[cp]
                - point_capacity[cp],
            )

            if overflow > 0:
                overflow_points += 1
                overflow_kg += overflow

            point_outcomes.append(
                {
                    "date": date_value.isoformat(),
                    "collection_point_id": cp,
                    "fill_kg": round(
                        fill_kg[cp],
                        3,
                    ),
                    "capacity_kg": (
                        point_capacity[cp]
                    ),
                    "fill_ratio": (
                        fill_kg[cp]
                        / point_capacity[cp]
                    ),
                    "overflow_kg": overflow,
                    "days_since_pickup": (
                        days_since_pickup[cp]
                    ),
                }
            )

        daily_summaries.append(
            {
                "date": date_value.isoformat(),
                "scenario": scenario,
                "generated_waste_kg": generated_today,
                "collected_waste_kg": collected_today,
                "uncollected_waste_kg": sum(
                    fill_kg.values()
                ),
                "overflow_kg": overflow_kg,
                "overflow_points": overflow_points,
                "points_due_end_of_day": len(
                    due_points
                ),
                "pickup_events": service_count,
                "unload_events": unload_count,
                "breakdowns_encountered": (
                    breakdown_count
                ),
            }
        )

    daily_df = pd.DataFrame(
        daily_summaries
    )

    events_df = pd.DataFrame(
        route_events
    )

    points_df = pd.DataFrame(
        point_outcomes
    )

    daily_df.to_csv(
        DAILY_OUTPUT,
        index=False,
    )

    events_df.to_csv(
        EVENT_OUTPUT,
        index=False,
    )

    points_df.to_csv(
        POINT_OUTPUT,
        index=False,
    )

    print()
    print("Baseline operations simulation complete.")
    print(f"Days                  : {len(daily_df):,}")
    print(
        f"Generated waste       : "
        f"{daily_df['generated_waste_kg'].sum()/1000:,.1f} tonnes"
    )
    print(
        f"Collected waste       : "
        f"{daily_df['collected_waste_kg'].sum()/1000:,.1f} tonnes"
    )
    print(
        f"Final backlog         : "
        f"{daily_df.iloc[-1]['uncollected_waste_kg']/1000:,.1f} tonnes"
    )
    print(
        f"Final overflow        : "
        f"{daily_df.iloc[-1]['overflow_kg']/1000:,.1f} tonnes"
    )
    print(
        f"Peak overflow points  : "
        f"{daily_df['overflow_points'].max():,}"
    )
    print(
        f"Pickup events         : "
        f"{daily_df['pickup_events'].sum():,}"
    )
    print(
        f"Unload events         : "
        f"{daily_df['unload_events'].sum():,}"
    )
    print(
        f"Breakdowns encountered: "
        f"{daily_df['breakdowns_encountered'].sum():,}"
    )
    print()
    print(f"Daily summary         : {DAILY_OUTPUT}")
    print(f"Route events          : {EVENT_OUTPUT}")
    print(f"Point outcomes        : {POINT_OUTPUT}")


if __name__ == "__main__":
    main()
