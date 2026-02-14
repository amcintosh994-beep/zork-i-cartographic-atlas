#!/usr/bin/env python3
"""
normalize_rooms.py — schema-authoritative normalizer for Zork I room Markdown.

v1.0 invariants (as requested):
- Canonical section order is derived ONLY from the schema file (section_order).
- Section parsing kinds are derived ONLY from the schema file (sections.properties[*].type),
  with a single schema-keyed specialization for "Exits (as reported)".
- Title authority is inverted:
    JSON.title is authoritative.
    Filename stem must equal JSON.title.
    Markdown H1 must equal JSON.title.
  All three must be identical, or the run fails (unless --fix-titles is used).

--fix-titles behavior (safe, explicit):
- If H1 does not match canonical JSON.title, rewrite H1.
- If filename stem does not match canonical JSON.title, rename the file to match (fails if collision).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

import re
from typing import List, Dict

# ----------------------------
# Schema loading (authority)
# ----------------------------

DEFAULT_SCHEMA_PATH = Path("schema/room_schema_v1.0.json")


class SchemaError(RuntimeError):
    pass


@dataclass(frozen=True)
class RoomSchema:
    title_pattern: str
    section_order: List[str]
    section_types: Dict[str, str]  # header -> "string" | "list" | "kv" | "exits"

    @staticmethod
    def from_json_schema(schema: dict) -> "RoomSchema":
        if not isinstance(schema, dict):
            raise SchemaError("Schema root must be a JSON object.")

        # Title pattern (instance constraint), used as a hard invariant for canonical titles
        try:
            title_pattern = schema["properties"]["title"]["pattern"]
        except Exception:
            raise SchemaError("Schema missing properties.title.pattern (needed for v1.0 title invariant).")
        if not isinstance(title_pattern, str) or not title_pattern.strip():
            raise SchemaError("Schema properties.title.pattern must be a non-empty string.")

        # Canonical ordered authority: schema must provide it via properties.section_order.const
        try:
            section_order = schema["properties"]["section_order"]["const"]
        except Exception:
            raise SchemaError(
                "Schema missing properties.section_order.const. "
                "Add explicit ordered authority (Option A) via a 'section_order' property whose schema uses 'const'."
            )
        if not (isinstance(section_order, list) and all(isinstance(x, str) for x in section_order)):
            raise SchemaError("Schema properties.section_order.const must be a list of strings.")
        section_order = [h.strip() for h in section_order if h.strip()]
        if len(section_order) != len(set(section_order)):
            dups = [h for h in section_order if section_order.count(h) > 1]
            raise SchemaError(f"Schema section_order contains duplicates: {sorted(set(dups))}")

        # Validate that schema's instance-level required sections match section_order exactly (no drift)
        try:
            required_sections = schema["properties"]["sections"]["required"]
        except Exception:
            raise SchemaError("Schema missing properties.sections.required.")
        if not (isinstance(required_sections, list) and all(isinstance(x, str) for x in required_sections)):
            raise SchemaError("Schema properties.sections.required must be a list of strings.")
        required_sections = [s.strip() for s in required_sections if s.strip()]

        if required_sections != section_order:
            raise SchemaError(
                "Schema drift: properties.sections.required must exactly match properties.section_order.const.\n"
                f"required:     {required_sections}\n"
                f"section_order:{section_order}"
            )

        # Derive section parse kinds from schema instance types (no code-defined structure)
        try:
            section_props = schema["properties"]["sections"]["properties"]
        except Exception:
            raise SchemaError("Schema missing properties.sections.properties (needed to derive section parse types).")
        if not isinstance(section_props, dict):
            raise SchemaError("Schema properties.sections.properties must be an object.")

        section_types: Dict[str, str] = {}
        for header in section_order:
            if header not in section_props:
                raise SchemaError(f"Schema missing section definition for {header!r} under properties.sections.properties.")
            sec_def = section_props[header]
            sec_type = sec_def.get("type")
            if sec_type == "string":
                section_types[header] = "string"
            elif sec_type == "array":
                # exits are still schema-keyed: the header name is canonical authority
                section_types[header] = "exits" if header == "Exits (as reported)" else "list"
            elif sec_type == "object":
                section_types[header] = "kv"
            else:
                raise SchemaError(f"Unsupported/unknown section type for {header!r}: {sec_type!r}")

        return RoomSchema(
            title_pattern=title_pattern,
            section_order=section_order,
            section_types=section_types,
        )


def load_schema(schema_path: Path) -> RoomSchema:
    if not schema_path.exists():
        raise SchemaError(f"Schema file not found: {schema_path}")
    try:
        data = json.loads(schema_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SchemaError(f"Schema JSON is invalid ({schema_path}): {e}") from e
    except Exception as e:
        raise SchemaError(f"Could not read schema file {schema_path}: {e}") from e

    return RoomSchema.from_json_schema(data)

def _canonicalize_internal_id(val: str) -> str:
    v = val.strip()
    if not v:
        return v  # leave empty; schema will fail and force you to fill it
    m = re.match(r"^Z1-R-(\d{1,3})$", v)
    if m:
        return f"Z1-R-{int(m.group(1)):03d}"
    return v

# ----------------------------
# Markdown parsing
# ----------------------------

H1_RE = re.compile(r"^#\s+(?P<title>.+?)\s*$")
H2_RE = re.compile(r"^##\s+(?P<h2>.+?)\s*$")
BULLET_RE = re.compile(r"^\s*[-*]\s+(?P<item>.+?)\s*$")
KV_RE = re.compile(r"^\s*\*\*(?P<key>.+?)\*\*:\s*(?P<val>.*)\s*$")       # **Key**: Value
KV_PLAIN_RE = re.compile(r"^\s*(?P<key>[^:]{1,60}):\s*(?P<val>.*)\s*$")  # Key: Value


@dataclass
class ParseError(Exception):
    path: Path
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


def rewrite_h1_in_markdown(md_path: Path, canonical_title: str) -> bool:
    """
    Replace the first Markdown H1 ('# ...') with '# {canonical_title}'.
    If no H1 exists, insert it at the top (after optional blank lines).
    Returns True if the file was modified.
    """
    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines(True)  # keep line endings
    new_h1_line = f"# {canonical_title}\n"

    for i, line in enumerate(lines):
        if H1_RE.match(line):
            if line == new_h1_line:
                return False
            lines[i] = new_h1_line
            md_path.write_text("".join(lines), encoding="utf-8")
            return True

    insert_at = 0
    while insert_at < len(lines) and lines[insert_at].strip() == "":
        insert_at += 1
    lines.insert(insert_at, new_h1_line)
    md_path.write_text("".join(lines), encoding="utf-8")
    return True


def split_into_blocks(lines: List[str]) -> Tuple[str, Dict[str, List[str]]]:
    """
    Returns (h1_title, blocks_by_h2), where blocks_by_h2 maps each H2 heading to its raw lines.
    Enforces: exactly one H1 near top, unique H2 headings, no content before first H2 (post-H1).
    """
    title: Optional[str] = None
    blocks: Dict[str, List[str]] = {}
    current_h2: Optional[str] = None

    for i, raw in enumerate(lines):
        line = raw.rstrip("\n")

        if title is None:
            if line.strip() == "":
                continue
            m1 = H1_RE.match(line)
            if not m1:
                raise ValueError(f"Expected H1 '# ...' near top (line {i+1}). Found: {line!r}")
            title = m1.group("title").strip()
            continue

        m2 = H2_RE.match(line)
        if m2:
            h2 = m2.group("h2").strip()
            if h2 in blocks:
                raise ValueError(f"Duplicate H2 heading '{h2}' (line {i+1}).")
            blocks[h2] = []
            current_h2 = h2
            continue

        if current_h2 is None:
            if line.strip() != "":
                raise ValueError(f"Content found before first H2 section (line {i+1}).")
            continue

        blocks[current_h2].append(line)

    if title is None:
        raise ValueError("Missing H1 '# ...' title.")

    return title, blocks


def enforce_h2_set_and_order(blocks: Dict[str, List[str]], *, schema: RoomSchema) -> None:
    found = list(blocks.keys())
    allowed = set(schema.section_order)

    extras = [h for h in found if h not in allowed]
    missing = [h for h in schema.section_order if h not in blocks]

    if extras:
        raise ValueError(f"Extra H2 headings not allowed: {extras}")
    if missing:
        raise ValueError(f"Missing required H2 headings: {missing}")

    if found != schema.section_order:
        raise ValueError(
            "H2 order mismatch.\n"
            f"Expected: {schema.section_order}\n"
            f"Found:    {found}"
        )


# ----------------------------
# Section parsing
# ----------------------------

def parse_list_section(raw_lines: List[str]) -> List[str]:
    items: List[str] = []
    for line in raw_lines:
        if line.strip() == "":
            continue
        m = BULLET_RE.match(line)
        if m:
            items.append(m.group("item").strip())
        else:
            items.append(line.strip())
    return items


def parse_string_section(raw_lines: List[str]) -> str:
    start = 0
    end = len(raw_lines)
    while start < end and raw_lines[start].strip() == "":
        start += 1
    while end > start and raw_lines[end - 1].strip() == "":
        end -= 1
    return "\n".join(raw_lines[start:end]).strip()


def _strip_md_bold(s: str) -> str:
    s = s.strip()
    # remove one layer of surrounding **...**
    if s.startswith("**") and s.endswith("**") and len(s) >= 4:
        s = s[2:-2].strip()
    # also strip stray leading/trailing **
    s = s.strip("*").strip()
    return s

def _notes(raw_lines: List[str]) -> Dict[str, object]:
    allowed_keys = {"Internal ID", "First mapped", "Revisions"}
    out: Dict[str, object] = {}
    notes: List[str] = []

    for line in raw_lines:
        s = line.strip()
        if not s:
            continue

        # Treat bullet lines as notes, even if they contain ':'.
        if s.startswith(("-", "*")):
            m = BULLET_RE.match(s)
            notes.append(_strip_md_bold(m.group("item") if m else s.lstrip("-* ").strip()))
            continue

        m = KV_RE.match(s) or KV_PLAIN_RE.match(s)
        if m:
            key = _strip_md_bold(m.group("key"))
            val = _strip_md_bold(m.group("val"))
            if key in allowed_keys:
                # Normalize Internal ID formatting here (see #3)
                if key == "Internal ID":
                    val = _canonicalize_internal_id(val)
                out[key] = val
            else:
                # Unknown “kv-ish” line goes to notes to avoid schema additionalProperties violations.
                notes.append(_strip_md_bold(s))
            continue

        # Anything else: treat as note
        notes.append(_strip_md_bold(s))

    if notes:
        out["Notes"] = notes
    return out



# Exit parsing remains strict and canonicalizes to schema's regex form.
EXIT_TOKEN_RE = re.compile(
    r"""^\s*
    (?P<prefix>\([^)]*\)\s*)?
    (?P<token>NE|NW|SE|SW|N|S|E|W|U|D|WAIT|LAND|LAUNCH)
    (?:/(?P<token2>NE|NW|SE|SW|N|S|E|W|U|D))?
    (?P<inline>\s*\([^)]*\)\s*)?
    (?P<colon>\s*:)?\s*
    →\s*
    (?P<link>\[\[Z1\s*-\s*[^\]]+\]\])
    (?P<trailing>\s+.*)?\s*$""",
    re.VERBOSE,
)

PLACEHOLDER_EXITS = {"None", "(none)", "*", "-"}

WIKILINK_RE = re.compile(r"^\[\[(?P<inner>.+)\]\]$")

WIKILINK_RE = re.compile(r"^\[\[(?P<inner>.+)\]\]$")

def _canonicalize_z1_wikilink(link: str) -> str:
    link = link.strip()
    m = WIKILINK_RE.match(link)
    if not m:
        return link

    inner = m.group("inner").strip()

    mz = re.match(r"^Z1\s*-\s*(?P<rest>.+)$", inner)
    if not mz:
        return f"[[{inner}]]"

    rest = mz.group("rest").strip()
    return f"[[Z1 - {rest}]]"

def parse_exits_section(raw_lines: List[str]) -> Tuple[List[str], List[str]]:
    items = parse_list_section(raw_lines)

    clean: List[str] = []
    notes: List[str] = []

    for item in items:
        s = item.strip()
        if not s or s in PLACEHOLDER_EXITS:
            continue

        m = EXIT_TOKEN_RE.match(s)
        if not m:
            raise ValueError(f"Exit line not in canonicalizable form: {s!r}")

        direction = m.group("token")
        link = _canonicalize_z1_wikilink(m.group("link"))
        clean_exit = f"{direction} → {link}"
        clean.append(clean_exit)

        note_parts: List[str] = []
        for g in ("prefix", "inline", "trailing"):
            val = m.group(g)
            if val:
                val = val.strip()
                if val:
                    note_parts.append(val)

        if note_parts:
            notes.append(f"Exit condition for {clean_exit}: " + " ".join(note_parts))

    return clean, notes



def _canonicalize_title_from_h1(h1: str, *, schema: RoomSchema) -> str:
    """
    Canonicalize and validate a title according to schema.title_pattern.

    If H1 lacks the required 'Z1 - ' prefix but would match after prefixing, we prefix it.
    Otherwise, fail fast (v1.0 no drift).
    """
    h1 = h1.strip()
    title_re = re.compile(schema.title_pattern)

    if title_re.match(h1):
        return h1

    prefixed = "Z1 - " + h1
    if title_re.match(prefixed):
        return prefixed

    raise ValueError(
        "Title does not satisfy schema pattern and cannot be canonicalized safely.\n"
        f"H1: {h1!r}\n"
        f"Pattern: {schema.title_pattern!r}"
    )


def _rename_file_to_title(md_path: Path, canonical_title: str) -> Path:
    target = md_path.with_name(canonical_title + md_path.suffix)
    if target == md_path:
        return md_path
    if target.exists():
        raise ValueError(f"Cannot rename file; target already exists: {target.name}")
    md_path.rename(target)
    return target

def parse_mapping_notes(raw_lines: List[str]) -> Dict[str, object]:
    allowed_keys = {"Internal ID", "First mapped", "Revisions"}
    out: Dict[str, object] = {}
    notes: List[str] = []

    def strip_md(s: str) -> str:
        s = s.strip()
        if s.startswith("**") and s.endswith("**") and len(s) >= 4:
            s = s[2:-2].strip()
        s = s.strip("*").strip()
        return s

    def canonicalize_internal_id(v: str) -> str:
        v = v.strip()
        if not v:
            return v
        m = re.match(r"^Z1-R-(\d{1,3})$", v)
        if m:
            return f"Z1-R-{int(m.group(1)):03d}"
        return v

    def try_parse_kv(s: str) -> bool:
        """Return True if s was parsed into out; False if it should be treated as a free note."""
        if ":" not in s:
            return False

        k_raw, v_raw = s.split(":", 1)

        key = strip_md(k_raw)
        key = re.sub(r"\*+", "", key)          # remove stray asterisks
        key = re.sub(r"\s+", " ", key).strip()

        val = strip_md(v_raw)

        if key in allowed_keys:
            if key == "Internal ID":
                val = canonicalize_internal_id(val)
                if not val:
                    raise ValueError("Mapping notes: Internal ID is empty")
            if key == "First mapped" and not val:
                raise ValueError("Mapping notes: First mapped is empty")

            out[key] = val
            return True

        return False

    for line in raw_lines:
        s = line.strip()
        if not s:
            continue

        # Bullet line: extract item, then attempt kv-parse first
        if s.startswith(("-", "*")):
            m = BULLET_RE.match(s)
            item = strip_md(m.group("item") if m else s.lstrip("-* ").strip())

            if not try_parse_kv(item):
                notes.append(item)
            continue

        # Non-bullet line: attempt kv-parse, else note
        if try_parse_kv(s):
            continue

        notes.append(strip_md(s))

    if notes:
        out["Notes"] = notes
    return out

def normalize_room_markdown(md_path: Path, *, schema: RoomSchema, fix_titles: bool = False) -> Tuple[Dict[str, Any], Path]:
    """
    Returns (normalized_object, effective_md_path). effective_md_path may differ if --fix-titles renames the file.
    """
    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines(True)

    try:
        parsed_h1, blocks = split_into_blocks(lines)
        enforce_h2_set_and_order(blocks, schema=schema)

        canonical_title = _canonicalize_title_from_h1(parsed_h1, schema=schema)

        # Enforce: H1 == JSON.title (canonical_title)
        if parsed_h1.strip() != canonical_title:
            if fix_titles:
                changed = rewrite_h1_in_markdown(md_path, canonical_title)
                if changed:
                    print(f"FIXED: {md_path.name}: H1 rewritten to '{canonical_title}'")
            else:
                raise ValueError(f"H1 does not match canonical JSON.title: {parsed_h1!r} != {canonical_title!r}")

        # Enforce: filename stem == JSON.title (canonical_title)
        if md_path.stem.strip() != canonical_title:
            if fix_titles:
                old = md_path
                md_path = _rename_file_to_title(md_path, canonical_title)
                print(f"FIXED: renamed file '{old.name}' → '{md_path.name}'")
            else:
                raise ValueError(f"Filename stem does not match canonical JSON.title: {md_path.stem!r} != {canonical_title!r}")

        sections_out: Dict[str, object] = {}
        exit_notes: List[str] = []

        for h2 in schema.section_order:
            raw = blocks.get(h2, [])
            kind = schema.section_types[h2]

            if kind == "exits":
                clean_exits, extracted = parse_exits_section(raw)
                sections_out[h2] = clean_exits
                exit_notes.extend(extracted)
                continue

            if kind == "string":
                sections_out[h2] = parse_string_section(raw)
            elif kind == "list":
                sections_out[h2] = parse_list_section(raw)
            elif kind == "kv":
                sections_out[h2] = parse_mapping_notes(raw)
            else:
                raise ValueError(f"Unknown section kind: {kind!r}")

        # Extracted exit conditions are appended into Hidden/conditional transitions (as before),
        # and the schema already requires that section.
        if exit_notes:
            tgt = "Hidden/conditional transitions"
            if tgt not in sections_out or not isinstance(sections_out[tgt], list):
                raise ValueError(f"Schema requires {tgt!r} as a list section; could not append exit notes safely.")
            sections_out[tgt].extend(exit_notes)

        return {
            "title": canonical_title,
            "sections": sections_out,
            "section_order": schema.section_order,  # derived from schema, not code
        }, md_path


    except ValueError as e:
        raise ParseError(md_path, str(e))


# ----------------------------
# CLI
# ----------------------------

def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Normalize Zork room markdown into JSON objects (schema-authoritative).")
    ap.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA_PATH,
        help=f"Path to room schema JSON Schema (default: {DEFAULT_SCHEMA_PATH.as_posix()})",
    )
    ap.add_argument(
        "--fix-titles",
        action="store_true",
        help="Rewrite Markdown H1 and/or rename file to match canonical JSON.title (strict).",
    )
    ap.add_argument("--in", dest="in_dir", required=True, help="Input directory containing room .md files")
    ap.add_argument("--out", dest="out_dir", required=True, help="Output directory for normalized JSON")
    ap.add_argument("--glob", dest="glob", default="**/*.md", help="Glob pattern (default: **/*.md)")
    ap.add_argument("--fail-fast", action="store_true", help="Stop on first error")
    args = ap.parse_args(argv)

    try:
        schema = load_schema(args.schema)
    except SchemaError as e:
        print(f"[normalize_rooms] SCHEMA ERROR: {e}", file=sys.stderr)
        return 2

    in_dir = Path(args.in_dir).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    md_files = sorted(in_dir.glob(args.glob))
    if not md_files:
        print(f"No markdown files found under {in_dir} matching {args.glob}")
        return 2

    errors: List[str] = []
    count_ok = 0

    for md in md_files:
        try:
            obj, effective_md = normalize_room_markdown(md, schema=schema, fix_titles=args.fix_titles)
            out_path = out_dir / (effective_md.stem + ".json")
            out_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            count_ok += 1
        except ParseError as e:
            errors.append(str(e))
            if args.fail_fast:
                print(errors[-1], file=sys.stderr)
                return 1

    if errors:
        print(f"\nNormalization completed with errors ({len(errors)}).", file=sys.stderr)
        for msg in errors:
            print(" - " + msg, file=sys.stderr)
        print(f"\nOK: {count_ok} / {len(md_files)}", file=sys.stderr)
        return 1

    print(f"Normalization successful. OK: {count_ok} / {len(md_files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
