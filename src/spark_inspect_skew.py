from pyspark.sql import SparkSession
from pyspark.sql import functions as F

INPUT_PATH = (
    "data/education_attendance/curated_national/"
    "national_attendance_skewed.csv"
)

spark = (
    SparkSession.builder
    .master("local[4]")
    .appName("education-attendance-skew-inspection")
    .config("spark.sql.shuffle.partitions", "4")
    .getOrCreate()
)

spark.sparkContext.setLogLevel("WARN")

df = (
    spark.read
    .option("header", True)
    .option("inferSchema", True)
    .csv(INPUT_PATH)
)

print()
print("INPUT PARTITIONS:", df.rdd.getNumPartitions())

partitioned = df.repartition(
    4,
    "district_id",
    "academic_year"
)

partition_counts = (
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
print("ROWS AFTER HASH PARTITIONING")
print("----------------------------")

partition_counts.show(
    10,
    truncate=False
)

largest_groups = (
    df
    .groupBy(
        "district_id",
        "academic_year"
    )
    .count()
    .orderBy(
        F.desc("count")
    )
)

print()
print("LARGEST KEYS")
print("------------")

largest_groups.show(
    10,
    truncate=False
)

spark.stop()
