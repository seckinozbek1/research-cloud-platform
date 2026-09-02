from pathlib import Path
import argparse

import geopandas as gpd
import numpy as np
import pandas as pd
from tqdm import tqdm


PROJECT_ROOT = Path(__file__).resolve().parents[2]

DEMAND_PATH = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "waste_gis"
    / "bin_daily_generated_waste.csv"
)

MAPPING_PATH = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "waste_gis"
    / "attribution"
    / "bin_collection_point_street_map.csv"
)

FLEET_PATH = (
    PROJECT_ROOT
    / "data"
    / "gis"
    / "karsiyaka_existing_fleet.geojson"
)

SIM_DIR = (
    PROJECT_ROOT
    / "data"
    / "curated"
    / "waste_gis"
    / "simulation"
)

OUTPUT_DIR = (
    SIM_DIR
    / "event_replay"
)

POLICY_EVENTS = {
    "stateful": (
        SIM_DIR
        / "stateful_route_events.csv"
    ),
    "utility": (
        SIM_DIR
        / "utility_route_events.csv"
    ),
    "utility_feasible": (
        SIM_DIR
        / "utility_feasible_route_events.csv"
    ),
}

EPS = 1e-9


def clock_from_shift_minute(value):
    """
    Route logs measure minutes from 08:00.
    Convert to HH:MM:SS.
    """
    timestamp = (
        pd.Timestamp("2000-01-01 08:00:00")
        + pd.to_timedelta(
            float(value),
            unit="m",
        )
    )
    return timestamp.strftime("%H:%M:%S")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--policy",
        choices=POLICY_EVENTS,
        required=True,
    )

    parser.add_argument(
        "--arrival-profile",
        choices=["uniform", "midnight"],
        default="uniform",
    )

    args = parser.parse_args()
    policy = args.policy
    arrival_profile = args.arrival_profile

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ----------------------------------------------------------
    # Inputs
    # ----------------------------------------------------------

    demand = pd.read_csv(
        DEMAND_PATH,
        parse_dates=["date"],
    )

    mapping = pd.read_csv(
        MAPPING_PATH,
        dtype={
            "bin_id": str,
            "collection_point_id": str,
            "road_node_id": str,
        },
    )

    fleet = gpd.read_file(
        FLEET_PATH
    )

    events = pd.read_csv(
        POLICY_EVENTS[policy]
    )

    pickups = events[
        events["event_type"] == "pickup"
    ].copy()

    pickups["date"] = pd.to_datetime(
        pickups["date"]
    )

    pickups = pickups.sort_values(
        [
            "date",
            "truck_id",
            "minute_from_0800",
        ]
    )

    pickups["route_sequence"] = (
        pickups
        .groupby(
            ["date", "truck_id"]
        )
        .cumcount()
        + 1
    )

    fleet_cols = [
        "truck_id",
        "truck_type",
        "hub_id",
        "payload_capacity_kg",
    ]

    pickups = pickups.merge(
        fleet[fleet_cols],
        on="truck_id",
        how="left",
    )

    # ----------------------------------------------------------
    # Canonical physical-bin table
    # ----------------------------------------------------------

    bins = (
        mapping[
            [
                "bin_id",
                "collection_point_id",
                "bin_type",
                "capacity_kg",
                "street_name",
                "road_node_id",
            ]
        ]
        .drop_duplicates("bin_id")
        .sort_values("bin_id")
        .reset_index(drop=True)
    )

    bin_ids = bins["bin_id"].tolist()

    bin_index = {
        bin_id: i
        for i, bin_id in enumerate(
            bin_ids
        )
    }

    capacity = bins[
        "capacity_kg"
    ].to_numpy(
        dtype=np.float64
    )

    n_bins = len(bins)

    # Routing stays at collection-point level.
    cp_to_indices = {}

    for cp, group in bins.groupby(
        "collection_point_id"
    ):
        cp_to_indices[cp] = [
            bin_index[x]
            for x in group["bin_id"]
        ]

    # ----------------------------------------------------------
    # Demand matrix:
    # date x physical bin
    # ----------------------------------------------------------

    daily_generation = (
        demand.pivot(
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

    dates = daily_generation.index

    # Intra-day waste-arrival model.
    #
    # uniform:
    #     1/24 of daily waste arrives at each hourly midpoint.
    #
    # midnight:
    #     validation mode matching the original simulator's
    #     daily-arrival assumption.
    hourly_weights = (
        np.ones(
            24,
            dtype=np.float64,
        )
        / 24.0
    )

    # ----------------------------------------------------------
    # Persistent physical state
    # ----------------------------------------------------------

    bin_waste = np.zeros(
        n_bins,
        dtype=np.float64,
    )

    street_waste = np.zeros(
        n_bins,
        dtype=np.float64,
    )

    cumulative_kg_hours = np.zeros(
        n_bins,
        dtype=np.float64,
    )

    cumulative_overflow_hours = np.zeros(
        n_bins,
        dtype=np.float64,
    )

    peak_street_by_bin = np.zeros(
        n_bins,
        dtype=np.float64,
    )

    daily_rows = []
    bin_outcomes = []
    pickup_rows = []
    bin_service_rows = []

    total_actual_collected = 0.0

    # ----------------------------------------------------------
    # Timeline replay
    # ----------------------------------------------------------

    for date in tqdm(
        dates,
        desc=f"Replay {policy}",
        unit="day",
    ):
        date_day = pd.Timestamp(
            date
        ).normalize()

        generation = (
            daily_generation.loc[
                date
            ].to_numpy(
                dtype=np.float64
            )
        )

        day_pickups = pickups[
            pickups["date"].dt.normalize()
            == date_day
        ].copy()

        # Event tuples:
        # minute, priority, event_type, payload
        #
        # Waste occurs at midpoint of each hour:
        # 00:30, 01:30, ..., 23:30.
        timeline = []

        if arrival_profile == "uniform":
            for hour in range(24):
                timeline.append(
                    (
                        hour * 60.0 + 30.0,
                        0,
                        "waste",
                        hour,
                    )
                )
        else:
            timeline.append(
                (
                    0.0,
                    0,
                    "waste",
                    -1,
                )
            )

        for idx, row in day_pickups.iterrows():
            absolute_minute = (
                8.0 * 60.0
                + float(
                    row[
                        "minute_from_0800"
                    ]
                )
            )

            timeline.append(
                (
                    absolute_minute,
                    1,
                    "pickup",
                    idx,
                )
            )

        # Snapshot exactly at midnight.
        timeline.append(
            (
                1440.0,
                2,
                "day_end",
                None,
            )
        )

        timeline.sort(
            key=lambda x: (
                x[0],
                x[1],
            )
        )

        last_minute = 0.0

        daily_kg_hours = np.zeros(
            n_bins,
            dtype=np.float64,
        )

        daily_overflow_hours = np.zeros(
            n_bins,
            dtype=np.float64,
        )

        generated_today = 0.0
        collected_today = 0.0

        daily_peak_street_total = (
            float(
                street_waste.sum()
            )
        )

        pickup_count = 0

        # ------------------------------------------------------
        # Process global chronological events
        # ------------------------------------------------------

        for (
            minute,
            _priority,
            event_type,
            payload,
        ) in timeline:

            elapsed_hours = (
                minute - last_minute
            ) / 60.0

            if elapsed_hours < -EPS:
                raise RuntimeError(
                    "Timeline moved backwards."
                )

            if elapsed_hours > 0:
                exposure = (
                    street_waste
                    * elapsed_hours
                )

                daily_kg_hours += (
                    exposure
                )

                cumulative_kg_hours += (
                    exposure
                )

                overflow_increment = (
                    street_waste > EPS
                ).astype(
                    np.float64
                ) * elapsed_hours

                daily_overflow_hours += (
                    overflow_increment
                )

                cumulative_overflow_hours += (
                    overflow_increment
                )

            last_minute = minute

            # --------------------------------------------------
            # Hourly waste arrival
            # --------------------------------------------------

            if event_type == "waste":
                hour = payload

                if hour == -1:
                    arriving = generation
                else:
                    arriving = (
                        generation
                        * hourly_weights[
                            hour
                        ]
                    )

                generated_today += float(
                    arriving.sum()
                )

                free_capacity = np.maximum(
                    capacity
                    - bin_waste,
                    0.0,
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
            # Truck pickup event
            # --------------------------------------------------

            elif event_type == "pickup":
                row = pickups.loc[
                    payload
                ]

                cp = row[
                    "collection_point_id"
                ]

                if (
                    cp not in cp_to_indices
                ):
                    continue

                indices = (
                    cp_to_indices[
                        cp
                    ]
                )

                scheduled_kg = float(
                    row[
                        "collected_kg"
                    ]
                )

                remaining = (
                    scheduled_kg
                )

                pre_street = float(
                    street_waste[
                        indices
                    ].sum()
                )

                pre_bin = float(
                    bin_waste[
                        indices
                    ].sum()
                )

                actual_street = 0.0
                actual_bin = 0.0

                # ----------------------------------------------
                # STREET FIRST
                # ----------------------------------------------

                street_order = sorted(
                    indices,
                    key=lambda i:
                    street_waste[i],
                    reverse=True,
                )

                for i in street_order:
                    if remaining <= EPS:
                        break

                    before_street = (
                        street_waste[i]
                    )

                    before_bin = (
                        bin_waste[i]
                    )

                    take = min(
                        before_street,
                        remaining,
                    )

                    if take <= EPS:
                        continue

                    street_waste[i] -= take
                    remaining -= take
                    actual_street += take

                    bin_service_rows.append(
                        {
                            "date":
                                date_day.date().isoformat(),

                            "pickup_time":
                                clock_from_shift_minute(
                                    row[
                                        "minute_from_0800"
                                    ]
                                ),

                            "truck_id":
                                row["truck_id"],

                            "truck_type":
                                row.get(
                                    "truck_type"
                                ),

                            "hub_id":
                                row.get(
                                    "hub_id"
                                ),

                            "route_sequence":
                                int(
                                    row[
                                        "route_sequence"
                                    ]
                                ),

                            "collection_point_id":
                                cp,

                            "bin_id":
                                bins.iloc[i][
                                    "bin_id"
                                ],

                            "street_name":
                                bins.iloc[i][
                                    "street_name"
                                ],

                            "collected_street_kg":
                                take,

                            "collected_bin_kg":
                                0.0,

                            "street_before_kg":
                                before_street,

                            "street_after_kg":
                                street_waste[i],

                            "bin_before_kg":
                                before_bin,

                            "bin_after_kg":
                                bin_waste[i],
                        }
                    )

                # ----------------------------------------------
                # THEN BIN CONTENT
                # ----------------------------------------------

                bin_order = sorted(
                    indices,
                    key=lambda i:
                    bin_waste[i],
                    reverse=True,
                )

                for i in bin_order:
                    if remaining <= EPS:
                        break

                    before_street = (
                        street_waste[i]
                    )

                    before_bin = (
                        bin_waste[i]
                    )

                    take = min(
                        before_bin,
                        remaining,
                    )

                    if take <= EPS:
                        continue

                    bin_waste[i] -= take
                    remaining -= take
                    actual_bin += take

                    bin_service_rows.append(
                        {
                            "date":
                                date_day.date().isoformat(),

                            "pickup_time":
                                clock_from_shift_minute(
                                    row[
                                        "minute_from_0800"
                                    ]
                                ),

                            "truck_id":
                                row["truck_id"],

                            "truck_type":
                                row.get(
                                    "truck_type"
                                ),

                            "hub_id":
                                row.get(
                                    "hub_id"
                                ),

                            "route_sequence":
                                int(
                                    row[
                                        "route_sequence"
                                    ]
                                ),

                            "collection_point_id":
                                cp,

                            "bin_id":
                                bins.iloc[i][
                                    "bin_id"
                                ],

                            "street_name":
                                bins.iloc[i][
                                    "street_name"
                                ],

                            "collected_street_kg":
                                0.0,

                            "collected_bin_kg":
                                take,

                            "street_before_kg":
                                before_street,

                            "street_after_kg":
                                street_waste[i],

                            "bin_before_kg":
                                before_bin,

                            "bin_after_kg":
                                bin_waste[i],
                        }
                    )

                actual_collected = (
                    actual_street
                    + actual_bin
                )

                collected_today += (
                    actual_collected
                )

                total_actual_collected += (
                    actual_collected
                )

                pickup_count += 1

                post_street = float(
                    street_waste[
                        indices
                    ].sum()
                )

                post_bin = float(
                    bin_waste[
                        indices
                    ].sum()
                )

                if post_street > EPS:
                    service_status = (
                        "street_remaining"
                    )

                elif post_bin > EPS:
                    service_status = (
                        "partial_bin_service"
                    )

                else:
                    service_status = (
                        "cleared"
                    )

                pickup_rows.append(
                    {
                        "date":
                            date_day.date().isoformat(),

                        "truck_id":
                            row["truck_id"],

                        "truck_type":
                            row.get(
                                "truck_type"
                            ),

                        "hub_id":
                            row.get(
                                "hub_id"
                            ),

                        "collection_point_id":
                            cp,

                        "route_sequence":
                            int(
                                row[
                                    "route_sequence"
                                ]
                            ),

                        "pickup_time":
                            clock_from_shift_minute(
                                row[
                                    "minute_from_0800"
                                ]
                            ),

                        "scheduled_collected_kg":
                            scheduled_kg,

                        "replayed_collected_kg":
                            actual_collected,

                        "replayed_street_collected_kg":
                            actual_street,

                        "replayed_bin_collected_kg":
                            actual_bin,

                        "unmet_scheduled_kg":
                            max(
                                0.0,
                                scheduled_kg
                                - actual_collected,
                            ),

                        "street_before_kg":
                            pre_street,

                        "street_after_kg":
                            post_street,

                        "bin_before_kg":
                            pre_bin,

                        "bin_after_kg":
                            post_bin,

                        "service_status":
                            service_status,

                        "logged_payload_kg":
                            row.get(
                                "payload_kg"
                            ),

                        "payload_capacity_kg":
                            row.get(
                                "payload_capacity_kg"
                            ),
                    }
                )

            # --------------------------------------------------
            # Day-end outputs
            # --------------------------------------------------

            elif event_type == "day_end":

                point_street = {}

                for cp, indices in (
                    cp_to_indices.items()
                ):
                    point_street[cp] = float(
                        street_waste[
                            indices
                        ].sum()
                    )

                street_total = float(
                    street_waste.sum()
                )

                bin_total = float(
                    bin_waste.sum()
                )

                overflow_bins = int(
                    (
                        street_waste > EPS
                    ).sum()
                )

                overflow_points = int(
                    sum(
                        value > EPS
                        for value
                        in point_street.values()
                    )
                )

                daily_rows.append(
                    {
                        "date":
                            date_day.date().isoformat(),

                        "policy":
                            policy,

                        "arrival_profile":
                            arrival_profile,

                        "generated_waste_kg":
                            generated_today,

                        "replayed_collected_waste_kg":
                            collected_today,

                        "end_bin_waste_kg":
                            bin_total,

                        "end_street_waste_kg":
                            street_total,

                        "end_total_backlog_kg":
                            bin_total
                            + street_total,

                        "street_waste_kg_hours":
                            float(
                                daily_kg_hours.sum()
                            ),

                        "overflow_bin_hours":
                            float(
                                daily_overflow_hours.sum()
                            ),

                        "overflow_bins_end":
                            overflow_bins,

                        "overflow_points_end":
                            overflow_points,

                        "peak_street_waste_kg":
                            daily_peak_street_total,

                        "pickup_events":
                            pickup_count,
                    }
                )

                for i, bin_id in enumerate(
                    bin_ids
                ):
                    bin_outcomes.append(
                        {
                            "date":
                                date_day.date().isoformat(),

                            "policy":
                                policy,

                            "bin_id":
                                bin_id,

                            "collection_point_id":
                                bins.iloc[i][
                                    "collection_point_id"
                                ],

                            "street_name":
                                bins.iloc[i][
                                    "street_name"
                                ],

                            "capacity_kg":
                                capacity[i],

                            "bin_waste_kg":
                                bin_waste[i],

                            "street_waste_kg":
                                street_waste[i],

                            "daily_street_waste_kg_hours":
                                daily_kg_hours[i],

                            "daily_overflow_hours":
                                daily_overflow_hours[i],

                            "cumulative_street_waste_kg_hours":
                                cumulative_kg_hours[i],

                            "cumulative_overflow_hours":
                                cumulative_overflow_hours[i],

                            "peak_street_waste_kg":
                                peak_street_by_bin[i],
                        }
                    )

            peak_street_by_bin = np.maximum(
                peak_street_by_bin,
                street_waste,
            )

            daily_peak_street_total = max(
                daily_peak_street_total,
                float(
                    street_waste.sum()
                ),
            )

    # ----------------------------------------------------------
    # Save outputs
    # ----------------------------------------------------------

    daily_df = pd.DataFrame(
        daily_rows
    )

    bins_df = pd.DataFrame(
        bin_outcomes
    )

    pickups_df = pd.DataFrame(
        pickup_rows
    )

    bin_service_df = pd.DataFrame(
        bin_service_rows
    )

    daily_path = (
        OUTPUT_DIR
        / f"{policy}_{arrival_profile}_daily_summary.csv"
    )

    bin_path = (
        OUTPUT_DIR
        / f"{policy}_{arrival_profile}_bin_outcomes.csv"
    )

    pickup_path = (
        OUTPUT_DIR
        / f"{policy}_{arrival_profile}_pickup_attribution.csv"
    )

    service_path = (
        OUTPUT_DIR
        / f"{policy}_{arrival_profile}_bin_service_events.csv"
    )

    daily_df.to_csv(
        daily_path,
        index=False,
    )

    bins_df.to_csv(
        bin_path,
        index=False,
    )

    pickups_df.to_csv(
        pickup_path,
        index=False,
    )

    bin_service_df.to_csv(
        service_path,
        index=False,
    )

    # ----------------------------------------------------------
    # Console report
    # ----------------------------------------------------------

    print()
    print(
        f"Event replay complete: {policy}"
    )

    print(
        "Generated waste       :",
        f"{daily_df['generated_waste_kg'].sum()/1000:,.1f} tonnes",
    )

    print(
        "Replayed collected    :",
        f"{daily_df['replayed_collected_waste_kg'].sum()/1000:,.1f} tonnes",
    )

    print(
        "Final backlog         :",
        f"{daily_df.iloc[-1]['end_total_backlog_kg']/1000:,.1f} tonnes",
    )

    print(
        "Final street waste    :",
        f"{daily_df.iloc[-1]['end_street_waste_kg']/1000:,.1f} tonnes",
    )

    print(
        "Street-waste kg-hours :",
        f"{daily_df['street_waste_kg_hours'].sum():,.0f}",
    )

    print(
        "Overflow bin-hours    :",
        f"{daily_df['overflow_bin_hours'].sum():,.1f}",
    )

    print(
        "Peak street waste     :",
        f"{daily_df['peak_street_waste_kg'].max()/1000:,.1f} tonnes",
    )

    print()
    print("Daily output          :", daily_path)
    print("Bin outcomes          :", bin_path)
    print("Pickup attribution    :", pickup_path)
    print("Bin service events    :", service_path)


if __name__ == "__main__":
    main()
