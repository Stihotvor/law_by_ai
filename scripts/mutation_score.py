"""Fail when the mutmut killed percentage is below ``MIN_KILLED_PERCENT``.

Reads the ``*.meta`` files mutmut writes under ``mutants/``. A mutant counts as
killed when its recorded exit code is neither 0 (tests passed, so it survived)
nor missing (never checked).

Usage: python scripts/mutation_score.py [mutants_dir]
"""

import json
import sys
from pathlib import Path

# The only place the mutation threshold lives. Raise it, never lower it.
MIN_KILLED_PERCENT = 97


def count(mutants_dir: Path) -> tuple[int, int]:
    """Return ``(killed, total)`` over every meta file below ``mutants_dir``."""
    killed = total = 0
    for meta in sorted(mutants_dir.rglob("*.meta")):
        codes = json.loads(meta.read_text(encoding="utf-8"))["exit_code_by_key"]
        for code in codes.values():
            total += 1
            killed += code not in (0, None)
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
