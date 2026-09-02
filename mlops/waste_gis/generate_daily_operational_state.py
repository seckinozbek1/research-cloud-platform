from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from tqdm import tqdm


PROJECT_ROOT = Path(__file__).resolve().parents[2]

FLEET_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_existing_fleet.geojson"
)

OUTPUT_DIR = (
    PROJECT_ROOT / "data" / "curated" / "waste_gis" / "operations_state"
)

RANDOM_SEED = 42

START_DATE = "2026-07-01"
DAYS = 30


# Human-work constraints.
SHIFT_START = "08:00"
SHIFT_END = "16:00"

SHIFT_MINUTES = 8 * 60

PREP_MINUTES = 15
LUNCH_MINUTES = 45
SHORT_BREAK_MINUTES = 30
CLOSEOUT_MINUTES = 30

NET_OPERATING_MINUTES = (
    SHIFT_MINUTES
    - PREP_MINUTES
    - LUNCH_MINUTES
    - SHORT_BREAK_MINUTES
    - CLOSEOUT_MINUTES
)


def truck_profile(truck_type):
    if truck_type == "large_truck":
        return {
            "age_years_mean": 7.0,
            "age_years_sd": 2.0,
            "base_breakdown_prob": 0.018,
            "minor_fault_prob": 0.035,
        }

    return {
        "age_years_mean": 5.0,
        "age_years_sd": 1.5,
        "base_breakdown_prob": 0.012,
        "minor_fault_prob": 0.025,
    }


def reliability_multiplier(
    age_years,
    days_since_service,
    maintenance_due,
):
    multiplier = 1.0

    if age_years >= 8:
        multiplier *= 1.35
    elif age_years >= 6:
        multiplier *= 1.15

    if days_since_service >= 90:
        multiplier *= 1.35
    elif days_since_service >= 60:
        multiplier *= 1.15

    if maintenance_due:
        multiplier *= 1.50

    return multiplier


def main():
    rng = np.random.default_rng(RANDOM_SEED)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    fleet = gpd.read_file(FLEET_PATH)

    dates = pd.date_range(
        START_DATE,
        periods=DAYS,
        freq="D",
    )

    # --------------------------------------------------------------
    # Persistent truck reliability attributes
    # --------------------------------------------------------------

    truck_state = {}

    for _, truck in fleet.iterrows():
        profile = truck_profile(
            truck["truck_type"]
        )

        age_years = max(
            1.0,
            rng.normal(
                profile["age_years_mean"],
                profile["age_years_sd"],
            ),
        )

        days_since_service = int(
            rng.integers(5, 100)
        )

        truck_state[truck["truck_id"]] = {
            "truck_age_years": round(
                age_years,
                1,
            ),
            "days_since_service": (
                days_since_service
            ),
        }

    rows = []

    total_iterations = (
        len(dates) * len(fleet)
    )

    with tqdm(
        total=total_iterations,
        desc="Daily operations",
        unit="truck-day",
    ) as progress:

        for date in dates:
            weekday = date.weekday()

            for _, truck in fleet.iterrows():
                truck_id = truck["truck_id"]
                truck_type = truck["truck_type"]

                profile = truck_profile(
                    truck_type
                )

                persistent = truck_state[
                    truck_id
                ]

                age_years = persistent[
                    "truck_age_years"
                ]

                days_since_service = persistent[
                    "days_since_service"
                ]

                # --------------------------------------------------
                # Planned maintenance
                # --------------------------------------------------

                maintenance_due = (
                    days_since_service >= 90
                )

                scheduled_maintenance = False

                # Prefer planned maintenance on a weekday and only
                # occasionally when due.
                if maintenance_due:
                    scheduled_maintenance = (
                        weekday < 5
                        and rng.random() < 0.20
                    )

                # --------------------------------------------------
                # Crew availability
                # --------------------------------------------------

                crew_sick = (
                    rng.random() < 0.015
                )

                crew_leave = (
                    rng.random() < 0.010
                )

                crew_late = False
                crew_late_minutes = 0

                if (
                    not crew_sick
                    and not crew_leave
                    and rng.random() < 0.035
                ):
                    crew_late = True
                    crew_late_minutes = int(
                        rng.integers(10, 36)
                    )

                crew_available = not (
                    crew_sick
                    or crew_leave
                )

                # --------------------------------------------------
                # Vehicle reliability
                # --------------------------------------------------

                reliability = (
                    reliability_multiplier(
                        age_years,
                        days_since_service,
                        maintenance_due,
                    )
                )

                breakdown_probability = (
                    profile[
                        "base_breakdown_prob"
                    ]
                    * reliability
                )

                minor_fault_probability = (
                    profile[
                        "minor_fault_prob"
                    ]
                    * reliability
                )

                breakdown = False
                minor_fault = False
                fault_delay_minutes = 0
                breakdown_after_minutes = np.nan

                if not scheduled_maintenance:
                    roll = rng.random()

                    if roll < breakdown_probability:
                        breakdown = True

                        # Vehicle can fail during the workday rather
                        # than always being unavailable from 08:00.
                        breakdown_after_minutes = int(
                            rng.integers(
                                60,
                                max(
                                    61,
                                    NET_OPERATING_MINUTES
                                    - 30,
                                ),
                            )
                        )

                    elif (
                        roll
                        < breakdown_probability
                        + minor_fault_probability
                    ):
                        minor_fault = True
                        fault_delay_minutes = int(
                            rng.integers(20, 61)
                        )

                vehicle_available_at_start = (
                    not scheduled_maintenance
                )

                # --------------------------------------------------
                # Human-safe usable time budget
                # --------------------------------------------------

                usable_minutes = (
                    NET_OPERATING_MINUTES
                )

                if crew_late:
                    usable_minutes -= (
                        crew_late_minutes
                    )

                if minor_fault:
                    usable_minutes -= (
                        fault_delay_minutes
                    )

                if not crew_available:
                    usable_minutes = 0

                if not vehicle_available_at_start:
                    usable_minutes = 0

                usable_minutes = max(
                    0,
                    usable_minutes,
                )

                if breakdown:
                    usable_minutes_before_breakdown = min(
                        usable_minutes,
                        int(
                            breakdown_after_minutes
                        ),
                    )
                else:
                    usable_minutes_before_breakdown = (
                        usable_minutes
                    )

                route_operable_at_start = (
                    crew_available
                    and vehicle_available_at_start
                )

                rows.append(
                    {
                        "date": date.date().isoformat(),
                        "truck_id": truck_id,
                        "truck_type": truck_type,
                        "hub_id": truck["hub_id"],

                        "shift_start": SHIFT_START,
                        "shift_end": SHIFT_END,

                        "shift_minutes": SHIFT_MINUTES,
                        "prep_minutes": PREP_MINUTES,
                        "lunch_minutes": LUNCH_MINUTES,
                        "short_break_minutes": SHORT_BREAK_MINUTES,
                        "closeout_minutes": CLOSEOUT_MINUTES,
                        "base_net_operating_minutes": (
                            NET_OPERATING_MINUTES
                        ),

                        "crew_sick": crew_sick,
                        "crew_leave": crew_leave,
                        "crew_late": crew_late,
                        "crew_late_minutes": (
                            crew_late_minutes
                        ),
                        "crew_available": (
                            crew_available
                        ),

                        "truck_age_years": age_years,
                        "days_since_service": (
                            days_since_service
                        ),
                        "maintenance_due": (
                            maintenance_due
                        ),
                        "scheduled_maintenance": (
                            scheduled_maintenance
                        ),

                        "minor_fault": minor_fault,
                        "fault_delay_minutes": (
                            fault_delay_minutes
                        ),

                        "breakdown": breakdown,
                        "breakdown_after_minutes": (
                            breakdown_after_minutes
                        ),

                        "vehicle_available_at_start": (
                            vehicle_available_at_start
                        ),
                        "route_operable_at_start": (
                            route_operable_at_start
                        ),

                        "usable_operating_minutes": (
                            usable_minutes
                        ),
                        "usable_minutes_before_breakdown": (
                            usable_minutes_before_breakdown
                        ),
                    }
                )

                # Service-age progression.
                if scheduled_maintenance:
                    persistent[
                        "days_since_service"
                    ] = 0
                else:
                    persistent[
                        "days_since_service"
                    ] += 1

                progress.update(1)

    state = pd.DataFrame(rows)

    output_path = (
        OUTPUT_DIR
        / "daily_truck_crew_state.csv"
    )

    state.to_csv(
        output_path,
        index=False,
    )

    print()
    print("Daily operational state created.")
    print(
        f"Period                : "
        f"{dates.min().date()} → {dates.max().date()}"
    )
    print(
        f"Truck-days            : "
        f"{len(state):,}"
    )

    print()
    print("Human availability:")
    print(
        f"  crew sick           : "
        f"{state['crew_sick'].sum():,}"
    )
    print(
        f"  crew leave          : "
        f"{state['crew_leave'].sum():,}"
    )
    print(
        f"  late starts         : "
        f"{state['crew_late'].sum():,}"
    )

    print()
    print("Vehicle disruptions:")
    print(
        f"  scheduled maintenance: "
        f"{state['scheduled_maintenance'].sum():,}"
    )
    print(
        f"  minor faults          : "
        f"{state['minor_fault'].sum():,}"
    )
    print(
        f"  breakdowns            : "
        f"{state['breakdown'].sum():,}"
    )

    print()
    print(
        f"Base net operating time: "
        f"{NET_OPERATING_MINUTES} min/day"
    )

    available = state[
        state["route_operable_at_start"]
    ]

    print(
        f"Mean usable time       : "
        f"{available['usable_operating_minutes'].mean():.1f} min"
    )

    print(
        f"Fully unavailable days : "
        f"{(~state['route_operable_at_start']).sum():,}"
    )

    print()
    print(f"Output                 : {output_path}")


if __name__ == "__main__":
    main()
