from pathlib import Path
import ast
import math
import re

import numpy as np
import osmnx as ox
import pandas as pd
from tqdm import tqdm


PROJECT_ROOT = Path(__file__).resolve().parents[2]

GRAPH_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_street_network.graphml"
)

OUTPUT_DIR = (
    PROJECT_ROOT / "data" / "gis" / "traffic_scenarios"
)

RANDOM_SEED = 42


ROAD_DEFAULT_SPEED_KPH = {
    "motorway": 80,
    "motorway_link": 50,
    "trunk": 70,
    "trunk_link": 50,
    "primary": 50,
    "primary_link": 40,
    "secondary": 45,
    "secondary_link": 35,
    "tertiary": 40,
    "tertiary_link": 30,
    "residential": 30,
    "living_street": 20,
    "unclassified": 30,
}


TRUCK_SPEED_CAP_KPH = {
    "small_truck": 42.0,
    "large_truck": 34.0,
}


# Vehicle-specific practical speed reduction by road class.
ROAD_OPERATION_FACTOR = {
    "small_truck": {
        "motorway": 0.95,
        "trunk": 0.90,
        "primary": 0.85,
        "secondary": 0.82,
        "tertiary": 0.78,
        "residential": 0.70,
        "living_street": 0.55,
        "unclassified": 0.70,
    },
    "large_truck": {
        "motorway": 0.90,
        "trunk": 0.85,
        "primary": 0.78,
        "secondary": 0.74,
        "tertiary": 0.68,
        "residential": 0.58,
        "living_street": 0.42,
        "unclassified": 0.58,
    },
}


RUSH_TIME_FACTOR = {
    "motorway": 1.30,
    "trunk": 1.45,
    "primary": 1.60,
    "secondary": 1.50,
    "tertiary": 1.35,
    "residential": 1.20,
    "living_street": 1.10,
    "unclassified": 1.20,
}


def first_value(value):
    if value is None:
        return None

    if isinstance(value, (list, tuple)):
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


def parse_highway(value):
    value = first_value(value)
    return str(value) if value is not None else "unclassified"


def parse_osm_speed(value, highway):
    value = first_value(value)
    speed = None

    if value is not None:
        text = str(value).lower()
        match = re.search(r"(\d+(?:\.\d+)?)", text)

        if match:
            speed = float(match.group(1))

            if "mph" in text:
                speed *= 1.60934

    if speed is None or not math.isfinite(speed):
        speed = ROAD_DEFAULT_SPEED_KPH.get(highway, 30)

    # Road metadata sanity bound only.
    return float(np.clip(speed, 10, 90))


def normalized_road_class(highway):
    if highway in {
        "motorway_link",
        "trunk_link",
        "primary_link",
        "secondary_link",
        "tertiary_link",
    }:
        return highway.replace("_link", "")

    return highway


def vehicle_speed_kph(osm_speed, highway, truck_type):
    road_class = normalized_road_class(highway)

    factor = ROAD_OPERATION_FACTOR[truck_type].get(
        road_class,
        ROAD_OPERATION_FACTOR[truck_type]["unclassified"],
    )

    practical_speed = osm_speed * factor

    return max(
        8.0,
        min(
            practical_speed,
            TRUCK_SPEED_CAP_KPH[truck_type],
        ),
    )


def roadwork_probability(highway):
    road_class = normalized_road_class(highway)

    if road_class in {"trunk", "primary", "secondary"}:
        return 0.030

    if road_class == "tertiary":
        return 0.018

    if road_class in {"residential", "living_street"}:
        return 0.006

    return 0.010


def main():
    rng = np.random.default_rng(RANDOM_SEED)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    graph = ox.io.load_graphml(GRAPH_PATH)

    _, edges = ox.graph_to_gdfs(graph)

    rows = []

    for (u, v, key), edge in tqdm(
        edges.iterrows(),
        total=len(edges),
        desc="Traffic model",
        unit="edge",
    ):
        highway = parse_highway(edge.get("highway"))
        road_class = normalized_road_class(highway)

        osm_speed = parse_osm_speed(
            edge.get("maxspeed"),
            highway,
        )

        length_m = float(edge["length"])

        has_roadworks = (
            rng.random() < roadwork_probability(highway)
        )

        roadwork_factor = (
            float(rng.uniform(1.35, 2.10))
            if has_roadworks
            else 1.0
        )

        temporary_closure = (
            rng.random() <
            (
                0.0005
                if road_class in {"trunk", "primary"}
                else 0.0015
            )
        )

        event_affected = rng.random() < 0.015

        event_factor = (
            float(rng.uniform(1.20, 1.55))
            if event_affected
            else 1.0
        )

        rain_factor = 1.12

        rush_factor = RUSH_TIME_FACTOR.get(
            road_class,
            1.20,
        )

        row = {
            "u": str(u),
            "v": str(v),
            "key": str(key),
            "highway": highway,
            "length_m": length_m,
            "osm_speed_context_kph": osm_speed,
            "has_roadworks": has_roadworks,
            "roadwork_factor": roadwork_factor,
            "temporary_closure": temporary_closure,
            "event_affected": event_affected,
            "event_factor": event_factor,
            "rain_factor": rain_factor,
        }

        for truck_type in [
            "small_truck",
            "large_truck",
        ]:
            speed_kph = vehicle_speed_kph(
                osm_speed,
                highway,
                truck_type,
            )

            base_seconds = (
                length_m
                / (speed_kph * 1000 / 3600)
            )

            normal_seconds = base_seconds

            rush_seconds = (
                base_seconds
                * rush_factor
            )

            disrupted_seconds = (
                base_seconds
                * rush_factor
                * roadwork_factor
                * event_factor
                * rain_factor
            )

            if temporary_closure:
                disrupted_seconds = np.inf

            row[f"{truck_type}_speed_kph"] = speed_kph
            row[f"{truck_type}_normal_s"] = normal_seconds
            row[f"{truck_type}_rush_s"] = rush_seconds
            row[f"{truck_type}_disrupted_s"] = disrupted_seconds

        rows.append(row)

    states = pd.DataFrame(rows)

    output_csv = (
        OUTPUT_DIR / "edge_vehicle_traffic_states.csv"
    )

    states.to_csv(
        output_csv,
        index=False,
    )

    print()
    print("Vehicle-specific traffic state created.")
    print(f"Edges                 : {len(states):,}")
    print(
        f"Roadwork edges        : "
        f"{states['has_roadworks'].sum():,}"
    )
    print(
        f"Temporary closures    : "
        f"{states['temporary_closure'].sum():,}"
    )
    print(
        f"Event-affected edges  : "
        f"{states['event_affected'].sum():,}"
    )

    for truck_type in [
        "small_truck",
        "large_truck",
    ]:
        print()
        print(truck_type)
        print(
            f"  median speed normal : "
            f"{states[f'{truck_type}_speed_kph'].median():.1f} km/h"
        )
        print(
            f"  max operational speed: "
            f"{states[f'{truck_type}_speed_kph'].max():.1f} km/h"
        )

        finite = np.isfinite(
            states[f"{truck_type}_disrupted_s"]
        )

        ratio = (
            states.loc[
                finite,
                f"{truck_type}_disrupted_s",
            ]
            /
            states.loc[
                finite,
                f"{truck_type}_normal_s",
            ]
        )

        print(
            f"  median disruption   : "
            f"{ratio.median():.2f}x"
        )

    print()
    print(f"Output                : {output_csv}")


if __name__ == "__main__":
    main()
