"""Generate 120 teaching-only records with a fixed seed, never by p-value search.

The bounded formula is data generation, not cleaning. This script never edits
the four historical CSV fixtures or adjusts its seed after inspecting results.
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

SEED = 20261012
N_STUDENTS = 120
DEFAULT_OUTPUT = Path(__file__).resolve().parents[1] / "examples" / "students_synthetic.csv"


def generate(path: Path = DEFAULT_OUTPUT) -> Path:
    rng = np.random.default_rng(SEED)
    tutoring = np.array(["yes"] * 60 + ["no"] * 60)
    rng.shuffle(tutoring)
    hours = rng.uniform(2, 18, N_STUDENTS)
    scores = 45 + 1.7 * hours + 5 * (tutoring == "yes") + rng.uniform(-12, 12, N_STUDENTS)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["student_id", "tutoring", "study_hours", "score", "passed"])
        writer.writeheader()
        for i, (group, hour, score) in enumerate(zip(tutoring, hours, scores), start=1):
            rounded_score = round(float(score), 2)
            writer.writerow({"student_id": f"S{i:03d}", "tutoring": group,
                             "study_hours": f"{hour:.2f}", "score": f"{rounded_score:.2f}",
                             "passed": "yes" if rounded_score >= 70 else "no"})
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    print(f"Generated {N_STUDENTS} synthetic records with fixed seed {SEED}: {generate(args.output)}")
