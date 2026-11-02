"""CLI: python -m sehatsathi.cli --notes data/sample_notes.txt [--json]"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date

from .agent import SehatSathiAgent


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="sehatsathi",
                                 description="Follow-up agent for ASHA/ANM health workers")
    ap.add_argument("--notes", help="path to a notes .txt file ('-' = stdin)")
    ap.add_argument("--text", help="notes text inline")
    ap.add_argument("--date", help="today, YYYY-MM-DD (default: system date)")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of Markdown")
    args = ap.parse_args(argv)

    if args.text:
        notes = args.text
    elif args.notes == "-" or args.notes is None and not sys.stdin.isatty():
        notes = sys.stdin.read()
    elif args.notes:
        with open(args.notes, encoding="utf-8") as fh:
            notes = fh.read()
    else:
        ap.error("provide --notes FILE, --text '...', or pipe notes on stdin")
        return 2
    today = date.fromisoformat(args.date) if args.date else date.today()
    agent = SehatSathiAgent()
    report = agent.run(notes, today=today)
    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    else:
        print(agent.render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
