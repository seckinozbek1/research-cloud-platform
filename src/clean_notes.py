from pathlib import Path

input_path = Path("data/raw/research_notes.txt")
output_path = Path("data/cleaned/research_notes_cleaned.txt")

text = input_path.read_text(encoding="utf-8")

cleaned = " ".join(text.split()).strip().lower()

output_path.write_text(cleaned + "\n", encoding="utf-8")

print(f"Read:    {input_path}")
print(f"Wrote:   {output_path}")
print(f"Chars in:  {len(text)}")
print(f"Chars out: {len(cleaned)}")
