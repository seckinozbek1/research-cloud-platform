from pyspark.sql import SparkSession
from pyspark.sql import functions as F

INPUT_PATH = (
    "data/education_attendance/curated_national/"
    "national_attendance_severely_skewed.csv"
)

SALT_BUCKETS = 8

spark = (
    SparkSession.builder
    .master("local[4]")
    .appName("measure-salting-balance")
    .config("spark.sql.shuffle.partitions", "4")
    # Keep Spark from merging our diagnostic partitions.
    .config("spark.sql.adaptive.enabled", "false")
    .getOrCreate()
)

spark.sparkContext.setLogLevel("WARN")

df = (
    spark.read
    .option("header", True)
    .option("inferSchema", True)
    .csv(INPUT_PATH)
)

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

partitioned = salted.repartition(
    4,
    "district_id",
    "academic_year",
    "salt",
)

counts = (
    partitioned
    .withColumn(
        "spark_partition_id",
        F.spark_partition_id()
    )
    .groupBy("spark_partition_id")
    .count()
    .orderBy("spark_partition_id")
)

print()
print("RAW ROWS AFTER SALTED HASH PARTITIONING")
print("---------------------------------------")
counts.show(truncate=False)

print()
print("DISTRICT 1 ROWS BY SALT")
print("-----------------------")

(
    salted
    .filter(F.col("district_id") == 1)
    .groupBy("academic_year", "salt")
    .count()
    .orderBy("academic_year", "salt")
    .show(40, truncate=False)
)

spark.stop()
