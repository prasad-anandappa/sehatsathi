#!/usr/bin/env python3
"""Run the SehatSathi effectiveness benchmark and print JSON.

    PYTHONPATH=src python3 benchmarks/run_benchmark.py

Exit code is non-zero if a safety threshold fails (danger recall
below 1.0, or any false escalation on a negated line) — the harness
doubles as a release gate for the extractor.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sehatsathi.benchmark import run_benchmark  # noqa: E402

_SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample_notes.txt"


def main() -> int:
    notes = _SAMPLE.read_text(encoding="utf-8") if _SAMPLE.exists() else ""
    result = run_benchmark(notes)
    print(json.dumps(result, indent=2))
    ok = result["danger_recall"] == 1.0 and result["false_escalations"] == 0
    print("SAFETY GATE:", "PASS" if ok else "FAIL", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
