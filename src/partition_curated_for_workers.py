from pathlib import Path
import csv
import hashlib
import time

INPUT_PATH = Path(
    "data/education_attendance/curated_national/"
    "national_attendance_curated.csv"
)

OUTPUT_DIR = Path(
    "data/education_attendance/worker_partitions"
)

PARTITIONS = 4

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

start = time.perf_counter()

handles = []
writers = []
counts = [0] * PARTITIONS

try:
    with INPUT_PATH.open("r", newline="", encoding="utf-8") as source:
        reader = csv.DictReader(source)

        for partition_id in range(PARTITIONS):
            path = OUTPUT_DIR / (
                f"attendance_worker_{partition_id:02d}.csv"
            )

            handle = path.open(
                "w",
                newline="",
                encoding="utf-8"
            )

            writer = csv.DictWriter(
                handle,
                fieldnames=reader.fieldnames
            )

            writer.writeheader()

            handles.append(handle)
            writers.append(writer)

        for row in reader:
            digest = hashlib.md5(
                row["student_id"].encode("utf-8")
            ).digest()

            partition_id = (
                int.from_bytes(digest[:4], "big")
                % PARTITIONS
            )

            writers[partition_id].writerow(row)
            counts[partition_id] += 1

finally:
    for handle in handles:
        handle.close()

elapsed = time.perf_counter() - start

print("WORKER PARTITIONS")

for partition_id, count in enumerate(counts):
    print(
        f"worker_{partition_id:02d}: "
        f"{count:>10,} rows"
    )

print()
print(f"Total:   {sum(counts):,}")
print(f"Elapsed: {elapsed:.3f} seconds")
