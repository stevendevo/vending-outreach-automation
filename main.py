#!/usr/bin/env python3
"""Replit entrypoint.

Replit runs `main.py` at the repo root, and `src/` is not importable by default,
so put it on the path before handing off to the real CLI.

    python main.py doctor
    python main.py daily --mode draft

Called with no arguments (the green Run button), it does a safe dry run:
everything except actually sending.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from vending_outreach.cli import main  # noqa: E402

if __name__ == "__main__":
    argv = sys.argv[1:] or ["daily", "--mode", "dry-run"]
    sys.exit(main(argv))
