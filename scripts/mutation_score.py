"""Fail when the mutmut killed percentage is below ``MIN_KILLED_PERCENT``.

Reads the ``*.meta`` files mutmut writes under ``mutants/``. A mutant counts as
killed when its recorded exit code means the mutant was detected in mutmut 3.8.1
(see ``mutmut.stats.status_by_exit_code``): killed, timeout, segfault or caught by
the type check. Survivors (0), no-tests (5, 33), skipped, suspicious, interrupted,
unchecked (None) and unknown codes stay in the total but do not count as killed.

Usage: python scripts/mutation_score.py [mutants_dir]
"""

import json
import sys
from pathlib import Path

# The only place the mutation threshold lives. Raise it, never lower it.
MIN_KILLED_PERCENT = 97


# Exit codes mutmut 3.8.1 maps to a detected mutant.
KILLED_CODES = frozenset({1, 3, 36, 24, -24, 152, 255, -11, -9, 37})


def count(mutants_dir: Path) -> tuple[int, int]:
    """Return ``(killed, total)`` over every meta file below ``mutants_dir``."""
    killed = total = 0
    for meta in sorted(mutants_dir.rglob("*.meta")):
        codes = json.loads(meta.read_text(encoding="utf-8"))["exit_code_by_key"]
        for code in codes.values():
            total += 1
            killed += code in KILLED_CODES
    return killed, total


def percent(killed: int, total: int) -> float:
    return 100.0 * killed / total if total else 0.0


def main(argv: list[str]) -> int:
    mutants_dir = Path(argv[1]) if len(argv) > 1 else Path("mutants")
    killed, total = count(mutants_dir)
    if total == 0:
        print(f"no mutants found under {mutants_dir}")
        return 1
    score = percent(killed, total)
    print(f"mutation score: {killed}/{total} killed = {score:.2f}% (minimum {MIN_KILLED_PERCENT}%)")
    return 0 if score >= MIN_KILLED_PERCENT else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
