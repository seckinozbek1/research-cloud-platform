import os
import time
import resource
from collections import Counter

N_DOCS = 100_000
WORDS_PER_DOC = 80

base_words = [
    "research", "cloud", "data", "model", "analysis",
    "policy", "system", "compute", "storage", "network"
]

print(f"Logical CPUs visible to Python: {os.cpu_count()}")
print(f"Documents: {N_DOCS:,}")
print(f"Words per document: {WORDS_PER_DOC}")

start = time.perf_counter()

documents = [
    " ".join(base_words[(i + j) % len(base_words)] for j in range(WORDS_PER_DOC))
    for i in range(N_DOCS)
]

counts = Counter()

for doc in documents:
    counts.update(doc.split())

elapsed = time.perf_counter() - start

peak_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
peak_mb = peak_kb / 1024

print()
print("=== RESULTS ===")
print(f"Runtime: {elapsed:.3f} seconds")
print(f"Peak memory: {peak_mb:.1f} MiB")
print(f"Unique tokens: {len(counts)}")
print(f"Total tokens processed: {sum(counts.values()):,}")
print(f"Most common token: {counts.most_common(1)[0]}")
