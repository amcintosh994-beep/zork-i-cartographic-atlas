#!/usr/bin/env python3
"""
Compiler-grade gate for Zork I Cartographic Atlas.

Enforces:

1. Markdown → normalized JSON via explicit schema path
2. JSON Schema validation of all normalized output
3. No git diff in rooms/ or normalized/ (compiler output must be committed)
"""

import subprocess
import sys
import json
from pathlib import Path

SCHEMA = Path("schema/room_schema_v1.0.json")
IN_DIR = Path("rooms")
OUT_DIR = Path("normalized")

NORMALIZER = [
    sys.executable,
    "scripts/normalize_rooms_schema_authoritative.py",
    "--schema", str(SCHEMA),
    "--in", str(IN_DIR) + "/",
    "--out", str(OUT_DIR) + "/",
    "--fail-fast",
]


def run(cmd):
    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(result.returncode)


def validate_schema():
    try:
        import jsonschema
    except Exception:
        print("[pre-commit] ERROR: Missing dependency: jsonschema", file=sys.stderr)
        print("Install with: python -m pip install jsonschema", file=sys.stderr)
        sys.exit(1)

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    json_files = sorted(OUT_DIR.glob("*.json"))

    if not json_files:
        print("[pre-commit] ERROR: No JSON files found in normalized/.", file=sys.stderr)
        sys.exit(1)

    errors = 0
    for p in json_files:
        try:
            instance = json.loads(p.read_text(encoding="utf-8"))
            jsonschema.validate(instance=instance, schema=schema)
        except Exception as e:
            errors += 1
            print(f"[pre-commit] SCHEMA VALIDATION FAILED: {p}: {e}", file=sys.stderr)

    if errors:
        sys.exit(1)

    print(f"[pre-commit] Schema validation OK: {len(json_files)} file(s).")


def ensure_no_diff():
    result = subprocess.run(
        ["git", "diff", "--exit-code", "--", "rooms", "normalized"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        print("[pre-commit] ERROR: Working tree differs from compiler output.", file=sys.stderr)
        print("Run the normalizer and commit changes.", file=sys.stderr)
        sys.exit(1)


def main():
    if not SCHEMA.exists():
        print(f"[pre-commit] ERROR: Schema not found: {SCHEMA}", file=sys.stderr)
        sys.exit(1)

    print("[pre-commit] Running compiler...")
    run(NORMALIZER)

    print("[pre-commit] Validating JSON against schema...")
    validate_schema()

    print("[pre-commit] Verifying no diff...")
    ensure_no_diff()

    print("[pre-commit] Atlas compiler gate PASSED.")


if __name__ == "__main__":
    main()
