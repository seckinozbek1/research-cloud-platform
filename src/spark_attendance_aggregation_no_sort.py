from pathlib import Path
from pyspark.sql import SparkSession
from pyspark.sql import functions as F
import time

INPUT_PATH = (
    "data/education_attendance/curated_national/"
    "national_attendance_curated.csv"
)

OUTPUT_PATH = (
    "data/education_attendance/spark_analytics/"
    "district_year_attendance_metrics_no_sort"
)

spark = (
    SparkSession.builder
    .master("local[4]")
    .appName("education-attendance-aggregation")
    .config("spark.sql.shuffle.partitions", "4")
    .getOrCreate()
)

spark.sparkContext.setLogLevel("WARN")

start = time.perf_counter()

df = (
    spark.read
    .option("header", True)
    .option("inferSchema", True)
    .csv(INPUT_PATH)
)

print()
print("INPUT PARTITIONS:", df.rdd.getNumPartitions())

result = (
    df
    .groupBy(
        "district_id",
        "academic_year"
    )
    .agg(
        F.count("*").alias("student_days"),

        F.sum("absent").alias(
            "absent_days"
        ),

        F.avg("absent").alias(
            "absence_rate"
        ),

        F.avg("deprivation_score").alias(
            "mean_deprivation"
        ),

        F.avg("rural").alias(
            "rural_share_among_observed"
        ),

        F.avg("rural_missing").alias(
            "rural_unknown_rate"
        ),
    )
)

print()
print("PHYSICAL / LOGICAL PLAN")
print("-----------------------")

result.explain(mode="formatted")

print()
print("FINAL GROUP COUNT:", result.count())

print()
print("SAMPLE OUTPUT")

result.show(
    8,
    truncate=False
)

(
    result
    .coalesce(1)
    .write
    .mode("overwrite")
    .option("header", True)
    .csv(OUTPUT_PATH)
)

elapsed = time.perf_counter() - start

print()
print(f"Elapsed: {elapsed:.3f} seconds")
print(f"Output: {OUTPUT_PATH}")

spark.stop()
