"""Stormkit start command: python start_hosted.py (from uploaded artifact)."""
import os
from pathlib import Path
import sys

if os.environ.get("SI_TRADER_MODE") != "hosted":
    raise SystemExit("Set SI_TRADER_MODE=hosted and configure deployment secrets before starting.")
sys.path.insert(0, str(Path(__file__).resolve().parent / "vendor"))
from nifty100_weekly.nifty100_adapter.web_app import main

main()
