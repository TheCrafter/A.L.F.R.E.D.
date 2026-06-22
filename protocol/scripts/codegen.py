"""Regenerate committed Pydantic + TypeScript types from the protocol schema.

Run from the protocol/ directory:
    uv run python scripts/codegen.py            # both languages
    uv run python scripts/codegen.py --python   # Python only
    uv run python scripts/codegen.py --typescript

Output is deterministic (no timestamps) so CI can diff it against the committed
files and fail on drift.
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schema" / "protocol.schema.json"
PY_OUT = ROOT / "gen" / "python" / "alfred_protocol" / "models.py"
TS_OUT = ROOT / "gen" / "typescript" / "index.ts"


def generate_python() -> None:
    PY_OUT.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "datamodel-codegen",
        "--input", str(SCHEMA),
        "--input-file-type", "jsonschema",
        "--output", str(PY_OUT),
        "--output-model-type", "pydantic_v2.BaseModel",
        "--use-annotated",
        "--use-schema-description",
        "--use-field-description",
        "--target-python-version", "3.12",
        "--disable-timestamp",
        "--use-double-quotes",
    ]
    print("->", " ".join(cmd))
    subprocess.run(cmd, check=True)


def generate_typescript() -> None:
    TS_OUT.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "pnpm", "exec", "json2ts",
        "-i", str(SCHEMA),
        "-o", str(TS_OUT),
        "--additionalProperties",
    ]
    print("->", " ".join(cmd))
    subprocess.run(cmd, check=True, shell=(sys.platform == "win32"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--python", action="store_true")
    parser.add_argument("--typescript", action="store_true")
    args = parser.parse_args()
    do_all = not (args.python or args.typescript)
    if args.python or do_all:
        generate_python()
    if args.typescript or do_all:
        generate_typescript()


if __name__ == "__main__":
    main()
