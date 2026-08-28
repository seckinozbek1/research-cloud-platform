from pathlib import Path
import csv
import sqlite3

RAW_PATH = Path("data/raw/research_notes.txt")
CLEANED_PATH = Path("data/cleaned/research_notes_cleaned.txt")
CURATED_PATH = Path("data/curated/research_notes_curated.csv")
WAREHOUSE_PATH = Path("analytical/warehouse.sqlite")

# 1. EXTRACT
text = RAW_PATH.read_text(encoding="utf-8")

# 2. TRANSFORM: clean
cleaned = " ".join(text.split()).strip().lower()
CLEANED_PATH.write_text(cleaned + "\n", encoding="utf-8")

# 3. TRANSFORM: curate into tabular structure
row = {
    "note_id": 1,
    "text": cleaned,
    "word_count": len(cleaned.split()),
}

with CURATED_PATH.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=["note_id", "text", "word_count"],
    )
    writer.writeheader()
    writer.writerow(row)

# 4. LOAD into warehouse
con = sqlite3.connect(WAREHOUSE_PATH)

con.execute("""
INSERT INTO notes_fact (note_id, text, word_count)
VALUES (?, ?, ?)
ON CONFLICT(note_id) DO UPDATE SET
    text = excluded.text,
    word_count = excluded.word_count
""", (
    row["note_id"],
    row["text"],
    row["word_count"],
))

con.commit()
con.close()

print("Pipeline completed")
print(f"Raw:       {RAW_PATH}")
print(f"Cleaned:   {CLEANED_PATH}")
print(f"Curated:   {CURATED_PATH}")
print(f"Warehouse: {WAREHOUSE_PATH}")
