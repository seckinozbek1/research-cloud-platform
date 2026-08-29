from pathlib import Path
import sqlite3


BASE_DIR = Path(__file__).resolve().parents[1]
DB_PATH = BASE_DIR / "metadata" / "metadata.sqlite"

RAW_ROOT = BASE_DIR / "data" / "education_attendance" / "raw"


def handle_storage_event(event: dict) -> dict:
    bucket = event.get("bucket")
    object_name = event.get("object_name")
    event_type = event.get("event_type")

    if not bucket or not object_name or not event_type:
        return {
            "status": "error",
            "message": "Event missing bucket, object_name, or event_type",
        }

    if event_type != "object_created":
        return {
            "status": "ignored",
            "message": f"Unsupported event type: {event_type}",
        }

    if bucket != "education-attendance-raw":
        return {
            "status": "ignored",
            "message": f"Unexpected bucket: {bucket}",
        }

    file_path = RAW_ROOT / object_name

    if not file_path.exists():
        return {
            "status": "error",
            "message": f"Object not found locally: {object_name}",
        }

    relative_path = file_path.relative_to(BASE_DIR)

    with sqlite3.connect(DB_PATH) as connection:
        connection.execute(
            """
            INSERT OR IGNORE INTO datasets (name, path, stage)
            VALUES (?, ?, ?)
            """,
            (
                file_path.name,
                str(relative_path),
                "raw",
            ),
        )

    return {
        "status": "registered",
        "bucket": bucket,
        "object_name": object_name,
        "stage": "raw",
        "path": str(relative_path),
    }


if __name__ == "__main__":
    test_event = {
        "bucket": "education-attendance-raw",
        "object_name": "attendance_2025.csv",
        "event_type": "object_created",
    }

    print(handle_storage_event(test_event))
