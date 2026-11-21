"""Build a source + dependencies artifact on the target Linux/Python runtime."""
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
out = root / "dist"
if out.exists():
    raise SystemExit("dist already exists; use a clean build workspace to avoid replacing artifacts.")
subprocess.run([sys.executable, "-B", "scripts/check_python.py"], cwd=root, check=True)
out.mkdir()
shutil.copytree(root / "nifty100_weekly", out / "nifty100_weekly", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
shutil.copyfile(root / "deploy/start_hosted.py", out / "start_hosted.py")
subprocess.run([sys.executable, "-m", "pip", "install", "--no-compile", "--target", str(out / "vendor"), "-r", str(root / "requirements.txt")], check=True)
print("Stormkit artifact prepared in dist. Build and run with the same OS, architecture and Python 3.12 runtime.")
