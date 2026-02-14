from __future__ import annotations
import json
from pathlib import Path
from jsonschema import Draft7Validator

schema_path = Path("schema/room_schema_v1.0.json")
rooms_dir = Path("build/rooms_json")

schema = json.loads(schema_path.read_text(encoding="utf-8"))
validator = Draft7Validator(schema)

errors = 0
for p in sorted(rooms_dir.glob("*.json")):
    data = json.loads(p.read_text(encoding="utf-8"))
    errs = sorted(validator.iter_errors(data), key=lambda e: e.path)
    if errs:
        errors += 1
        print(f"\n{p}:")
        for e in errs:
            loc = "/".join(str(x) for x in e.path) or "<root>"
            print(f"  - {loc}: {e.message}")

if errors:
    raise SystemExit(1)

print("All room JSON files validate against room_schema_v1.0.json.")
