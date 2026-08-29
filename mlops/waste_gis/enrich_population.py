from pathlib import Path
import time

import geopandas as gpd
import requests
from shapely.geometry import mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]

FEATURES_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_zone_features.geojson"
)

OUTPUT_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_zone_population.geojson"
)

SUBMIT_URL = "https://api.worldpop.org/v2/population"
TASK_URL = "https://api.worldpop.org/v2/tasks/{task_id}"

YEAR = 2025
RESOLUTION = "100m"

POLL_INTERVAL_SECONDS = 1
MAX_POLLS = 60


def submit_population_task(session, geometry):
    payload = {
        "geojson": mapping(geometry),
        "year": YEAR,
        "resolution": RESOLUTION,
    }

    response = session.post(
        SUBMIT_URL,
        json=payload,
        timeout=60,
    )
    response.raise_for_status()

    data = response.json()

    if "task_id" not in data:
        raise RuntimeError(
            f"WorldPop submission did not return task_id: {data}"
        )

    return data["task_id"]


def wait_for_result(session, task_id):
    url = TASK_URL.format(task_id=task_id)

    for _ in range(MAX_POLLS):
        response = session.get(url, timeout=60)
        response.raise_for_status()

        data = response.json()
        status = data.get("status")

        if status == "success":
            return data["result"]

        if status in {"failed", "error"}:
            raise RuntimeError(
                f"WorldPop task {task_id} failed: {data}"
            )

        time.sleep(POLL_INTERVAL_SECONDS)

    raise TimeoutError(
        f"WorldPop task {task_id} did not complete after "
        f"{MAX_POLLS} polls."
    )


def main():
    zones = gpd.read_file(FEATURES_PATH)

    population_values = []
    population_density_values = []
    worldpop_area_values = []

    session = requests.Session()

    total = len(zones)

    for number, (_, zone) in enumerate(zones.iterrows(), start=1):
        zone_id = zone["zone_id"]

        print(f"[{number:02d}/{total}] {zone_id}: submitting...")

        task_id = submit_population_task(
            session,
            zone.geometry,
        )

        result = wait_for_result(
            session,
            task_id,
        )

        population = float(result["total_population"])
        density = float(result["population_density"])
        area_km2 = float(result["area_km2"])

        population_values.append(population)
        population_density_values.append(density)
        worldpop_area_values.append(area_km2)

        print(
            f"         population={population:.0f}, "
            f"density={density:.0f}/km²"
        )

    zones["population_2025"] = population_values
    zones["population_density_2025"] = population_density_values
    zones["worldpop_area_km2"] = worldpop_area_values
    zones["population_source"] = "worldpop_R2025A_2025_100m"

    zones.to_file(
        OUTPUT_PATH,
        driver="GeoJSON",
    )

    print()
    print("Population enrichment completed.")
    print(f"Zones              : {len(zones):,}")
    print(
        f"Population total   : "
        f"{zones['population_2025'].sum():,.0f}"
    )
    print(
        f"Population range   : "
        f"{zones['population_2025'].min():,.0f}–"
        f"{zones['population_2025'].max():,.0f}"
    )
    print(
        f"Density range      : "
        f"{zones['population_density_2025'].min():,.0f}–"
        f"{zones['population_density_2025'].max():,.0f} /km²"
    )
    print(
        f"Median density     : "
        f"{zones['population_density_2025'].median():,.0f} /km²"
    )
    print(f"Output             : {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
