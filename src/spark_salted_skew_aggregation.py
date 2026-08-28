from pyspark.sql import SparkSession
from pyspark.sql import functions as F
import time

INPUT_PATH = (
    "data/education_attendance/curated_national/"
    "national_attendance_severely_skewed.csv"
)

SALT_BUCKETS = 8

spark = (
    SparkSession.builder
    .master("local[4]")
    .appName("education-attendance-salted-skew")
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

# Salt only the hot district.
salted = df.withColumn(
    "salt",
    F.when(
        F.col("district_id") == 1,
        F.pmod(
            F.hash(F.col("student_id")),
            F.lit(SALT_BUCKETS)
        )
    ).otherwise(F.lit(0))
)

# --------------------------------------------------
# STAGE 1
# Aggregate hot keys into smaller salted subgroups.
# --------------------------------------------------

partial = (
    salted
    .groupBy(
        "district_id",
        "academic_year",
        "salt",
    )
    .agg(
        F.count("*").alias("student_days_partial"),
        F.sum("absent").alias("absent_days_partial"),
        F.sum("deprivation_score").alias(
            "deprivation_sum_partial"
        ),
        F.sum(
            F.when(
                F.col("rural").isNotNull(),
                1
            ).otherwise(0)
        ).alias("rural_known_partial"),
        F.sum(
            F.coalesce(
                F.col("rural"),
                F.lit(0)
            )
        ).alias("rural_count_partial"),
        F.sum("rural_missing").alias(
            "rural_missing_partial"
        ),
    )
)

print()
print("SALTED PARTIAL PLAN")
print("-------------------")

partial.explain(mode="formatted")

# Force redistribution of salted groups and inspect balance.
balanced = partial.repartition(
    4,
    "district_id",
    "academic_year",
    "salt",
)

partition_counts = (
    balanced
    .withColumn(
        "spark_partition_id",
        F.spark_partition_id()
    )
    .groupBy("spark_partition_id")
    .count()
    .orderBy("spark_partition_id")
)

print()
print("SALTED PARTIAL GROUPS PER PARTITION")
print("-----------------------------------")
partition_counts.show(truncate=False)

# --------------------------------------------------
# STAGE 2
# Remove salt and reconstruct final district-year.
# --------------------------------------------------

result = (
    partial
    .groupBy(
        "district_id",
        "academic_year"
    )
    .agg(
        F.sum("student_days_partial").alias(
            "student_days"
        ),
        F.sum("absent_days_partial").alias(
            "absent_days"
        ),
        F.sum("deprivation_sum_partial").alias(
            "deprivation_sum"
        ),
        F.sum("rural_known_partial").alias(
            "rural_known"
        ),
        F.sum("rural_count_partial").alias(
            "rural_count"
        ),
        F.sum("rural_missing_partial").alias(
            "rural_missing"
        ),
    )
    .withColumn(
        "absence_rate",
        F.col("absent_days") / F.col("student_days")
    )
    .withColumn(
        "mean_deprivation",
        F.col("deprivation_sum") / F.col("student_days")
    )
    .withColumn(
        "rural_share_among_observed",
        F.when(
            F.col("rural_known") > 0,
            F.col("rural_count") / F.col("rural_known")
        )
    )
    .withColumn(
        "rural_unknown_rate",
        F.col("rural_missing") / F.col("student_days")
    )
)

print()
print("FINAL GROUP COUNT:", result.count())

print()
print("DISTRICT 1 RESULTS")

(
    result
    .filter(F.col("district_id") == 1)
    .orderBy("academic_year")
    .select(
        "district_id",
        "academic_year",
        "student_days",
        "absence_rate",
        "mean_deprivation",
    )
    .show(truncate=False)
)

elapsed = time.perf_counter() - start

print()
print(f"Elapsed: {elapsed:.3f} seconds")

spark.stop()
