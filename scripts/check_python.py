"""Syntax-check maintained source only; archived prototypes are not CI targets."""
import ast
from pathlib import Path

files = [*Path("nifty100_weekly").rglob("*.py"), *Path("tests").rglob("*.py"), *Path("scripts").glob("*.py")]
for file in files:
    ast.parse(file.read_text(encoding="utf-8-sig"), filename=str(file))
print(f"Maintained Python syntax: {len(files)} files passed")
