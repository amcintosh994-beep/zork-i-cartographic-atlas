# Zork I cartographic atlas

A schema-authoritative, complier validated cartographic index of Zork I.

This repository implements deterministic normalization and structural validation for a complete room-by-room atlas of the game.

The system enforces:

* JSON-schema authority over structure
* Deterministic Markdown → JSON compilation
* Canonical exit formatting
* Title authority inversion (JSON = filename = H1)
* Pre-commit structural validation
* Drift resistance via schema lock

The project behaves as a compiler toolchain rather than a note repository.

## Architecture
Input:
rooms/*.md

Output:
normalized/*.json

Compiler:
scripts/normalize_rooms_schema_authoritative.py

Pre-commit gate:
scripts/atlast_compile_gate.py

Schema:
schema/room_schema_v1.0.json

## Invariants (v1.0)
* No unknown headers permitted
* Exit lines must match canonical regex
* Mapping notes must include:
	* Internal ID (Z1-R-###)
	* First mapped
* JSON.title is authoritative across filename and H1
* Structural modifications require schema revision

## v1.0 freeze
The tag:
z1-atlas-v1.0

represents the first fully validated, schema-clean canonical baseline.