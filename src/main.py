"""Launch Dark Fantasy Chess.

Run from the project root with:
    python src/main.py
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ui.game import DarkFantasyChess


if __name__ == "__main__":
    DarkFantasyChess().run()
