from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import subprocess
import sys
import time

INPUT_DIR = Path(
    "data/education_attendance/ministry_exports"
)

WORKER_SCRIPT = Path(
    "src/clean_ministry_export_worker.py"
)

FILES = sorted(
    INPUT_DIR.glob("regional_attendance_export_*.csv")
)


def run_worker(path):
    start = time.perf_counter()

    result = subprocess.run(
        [
            sys.executable,
            str(WORKER_SCRIPT),
            str(path),
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )

    elapsed = time.perf_counter() - start

    if result.returncode != 0:
        raise RuntimeError(
            f"{path.name} failed:\n{result.stderr}"
        )

    return path.name, elapsed


def run_sequential():
    print("MODE: sequential")

    start = time.perf_counter()

    for path in FILES:
        name, elapsed = run_worker(path)
        print(
            f"Completed {name:<35} "
            f"{elapsed:6.2f} s"
        )

    total = time.perf_counter() - start

    print()
    print(f"Sequential wall time: {total:.3f} seconds")


def run_parallel():
    print("MODE: parallel")
    print(f"Workers: {len(FILES)}")

    start = time.perf_counter()

    with ThreadPoolExecutor(
        max_workers=len(FILES)
    ) as executor:

        futures = {
            executor.submit(run_worker, path): path
            for path in FILES
        }

        for future in as_completed(futures):
            name, elapsed = future.result()

            print(
                f"Completed {name:<35} "
                f"{elapsed:6.2f} s"
            )

    total = time.perf_counter() - start

    print()
    print(f"Parallel wall time: {total:.3f} seconds")


if len(sys.argv) != 2 or sys.argv[1] not in {
    "sequential",
    "parallel",
}:
    raise SystemExit(
        "Usage: python3 run_distributed_cleaning.py "
        "[sequential|parallel]"
    )

if sys.argv[1] == "sequential":
    run_sequential()
else:
    run_parallel()
