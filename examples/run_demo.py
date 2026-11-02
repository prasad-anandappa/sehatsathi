"""One-command demo: PYTHONPATH=src python3 examples/run_demo.py"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sehatsathi.agent import SehatSathiAgent  # noqa: E402

notes = (Path(__file__).resolve().parents[1] / "data" / "sample_notes.txt").read_text(encoding="utf-8")
agent = SehatSathiAgent()
print(agent.render_markdown(agent.run(notes, today=date(2026, 11, 2))))
