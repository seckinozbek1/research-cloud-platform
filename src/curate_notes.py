from pathlib import Path
import csv

input_path = Path("data/cleaned/research_notes_cleaned.txt")
output_path = Path("data/curated/research_notes_curated.csv")

text = input_path.read_text(encoding="utf-8").strip()

rows = [
    {
        "note_id": 1,
        "text": text,
        "word_count": len(text.split())
    }
]

with output_path.open("w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(
        f,
        fieldnames=["note_id", "text", "word_count"]
    )
    writer.writeheader()
    writer.writerows(rows)

print(f"Read:  {input_path}")
print(f"Wrote: {output_path}")
print(f"Rows:  {len(rows)}")
