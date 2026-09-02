from pathlib import Path

import geopandas as gpd
import numpy as np
import osmnx as ox
import pandas as pd
from tqdm import tqdm


PROJECT_ROOT = Path(__file__).resolve().parents[2]

BOUNDARY_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_boundary.geojson"
)

CELLS_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_zone_population.geojson"
)

RAW_POI_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_activity_osm.geojson"
)

OUTPUT_PATH = (
    PROJECT_ROOT / "data" / "gis" / "karsiyaka_activity_features.geojson"
)


OSM_TAGS = {
    "amenity": [
        "hospital",
        "clinic",
        "restaurant",
        "cafe",
        "fast_food",
        "school",
        "university",
        "marketplace",
    ],
    "shop": [
        "supermarket",
        "mall",
        "department_store",
        "convenience",
    ],
    "tourism": [
        "hotel",
    ],
    "landuse": [
        "retail",
        "commercial",
        "industrial",
    ],
    "leisure": [
        "park",
        "sports_centre",
        "stadium",
    ],
}


CATEGORY_RULES = {
    "healthcare": {
        "amenity": {"hospital", "clinic"},
    },
    "food_service": {
        "amenity": {"restaurant", "cafe", "fast_food"},
    },
    "education": {
        "amenity": {"school", "university"},
    },
    "market": {
        "amenity": {"marketplace"},
    },
    "supermarket": {
        "shop": {"supermarket", "convenience"},
    },
    "major_retail": {
        "shop": {"mall", "department_store"},
        "landuse": {"retail"},
    },
    "hotel": {
        "tourism": {"hotel"},
    },
    "commercial": {
        "landuse": {"commercial"},
    },
    "industrial": {
        "landuse": {"industrial"},
    },
    "recreation": {
        "leisure": {"park", "sports_centre", "stadium"},
    },
}


def classify_feature(row):
    categories = []

    for category, rules in CATEGORY_RULES.items():
        matched = False

        for column, values in rules.items():
            value = row.get(column)

            if pd.notna(value) and value in values:
                matched = True
                break

        if matched:
            categories.append(category)

    return categories


def representative_points(gdf):
    result = gdf.copy()

    # Points stay points. Polygons/lines become representative interior points
    # for cell assignment and proximity calculations.
    non_points = result.geometry.geom_type != "Point"

    result.loc[non_points, "geometry"] = (
        result.loc[non_points]
        .geometry
        .representative_point()
    )

    return result


def main():
    boundary = gpd.read_file(BOUNDARY_PATH)
    cells = gpd.read_file(CELLS_PATH)

    polygon = boundary.geometry.union_all()

    print("Fetching Karşıyaka activity features from OpenStreetMap...")
    pois = ox.features_from_polygon(
        polygon,
        tags=OSM_TAGS,
    )

    if pois.empty:
        raise RuntimeError("No OSM activity features returned.")

    pois = pois.reset_index()

    keep_columns = [
        col
        for col in [
            "element",
            "id",
            "name",
            "amenity",
            "shop",
            "tourism",
            "landuse",
            "leisure",
            "geometry",
        ]
        if col in pois.columns
    ]

    pois = pois[keep_columns].copy()

    pois["categories"] = pois.apply(
        classify_feature,
        axis=1,
    )

    pois = pois[
        pois["categories"].map(len) > 0
    ].copy()

    # Store raw source-derived activity layer.
    pois_for_file = pois.copy()
    pois_for_file["categories"] = (
        pois_for_file["categories"]
        .apply(lambda x: ",".join(x))
    )

    pois_for_file.to_file(
        RAW_POI_PATH,
        driver="GeoJSON",
    )

    metric_crs = cells.estimate_utm_crs()

    cells_m = cells.to_crs(metric_crs)
    pois_m = representative_points(
        pois.to_crs(metric_crs)
    )

    # One row per POI-category pair.
    expanded_rows = []

    for idx, row in tqdm(
        pois_m.iterrows(),
        total=len(pois_m),
        desc="Classifying OSM activity",
        unit="feature",
    ):
        for category in row["categories"]:
            expanded_rows.append(
                {
                    "category": category,
                    "geometry": row.geometry,
                }
            )

    activity = gpd.GeoDataFrame(
        expanded_rows,
        geometry="geometry",
        crs=metric_crs,
    )

    joined = gpd.sjoin(
        activity,
        cells_m[["zone_id", "geometry"]],
        how="left",
        predicate="within",
    )

    counts = (
        joined.dropna(subset=["zone_id"])
        .groupby(["zone_id", "category"])
        .size()
        .unstack(fill_value=0)
    )

    features = cells_m.copy()

    for category in CATEGORY_RULES:
        column = f"{category}_count"

        if category in counts.columns:
            mapping = counts[category]
            features[column] = (
                features["zone_id"]
                .map(mapping)
                .fillna(0)
                .astype(int)
            )
        else:
            features[column] = 0

    # Distance-to-nearest features for high-impact activity types.
    cell_centroids = features.geometry.centroid

    distance_categories = [
        "healthcare",
        "supermarket",
        "major_retail",
        "food_service",
        "industrial",
    ]

    for category in distance_categories:
        subset = activity[
            activity["category"] == category
        ]

        column = f"nearest_{category}_m"

        if subset.empty:
            features[column] = np.nan
            continue

        union = subset.geometry.union_all()

        features[column] = cell_centroids.distance(union)

    count_columns = [
        f"{category}_count"
        for category in CATEGORY_RULES
    ]

    # Simple transparent activity score for the first-pass demand model.
    # It is a feature-engineering proxy, not observed municipal waste.
    features["activity_score"] = (
        features["healthcare_count"] * 4.0
        + features["major_retail_count"] * 5.0
        + features["supermarket_count"] * 3.0
        + features["food_service_count"] * 1.5
        + features["market_count"] * 2.5
        + features["hotel_count"] * 2.0
        + features["education_count"] * 1.5
        + features["commercial_count"] * 2.0
        + features["industrial_count"] * 2.0
        + features["recreation_count"] * 0.5
    )

    features.to_crs("EPSG:4326").to_file(
        OUTPUT_PATH,
        driver="GeoJSON",
    )

    print()
    print("Activity enrichment completed.")
    print(f"OSM activity features : {len(pois):,}")
    print(f"Demand cells          : {len(features):,}")
    print(
        f"Cells with activity   : "
        f"{(features[count_columns].sum(axis=1) > 0).sum():,}"
    )
    print(
        f"Zero-pop but active   : "
        f"{((features['population_2025'] == 0) & (features[count_columns].sum(axis=1) > 0)).sum():,}"
    )

    print()
    print("Feature totals:")

    for column in count_columns:
        print(
            f"  {column:24} "
            f"{features[column].sum():,}"
        )

    print()
    print(f"Raw OSM output        : {RAW_POI_PATH}")
    print(f"Cell feature output   : {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
