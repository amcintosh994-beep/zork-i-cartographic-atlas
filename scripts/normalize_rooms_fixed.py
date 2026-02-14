# scripts/normalize_rooms.py
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Optional


CANONICAL_H2_ORDER: List[str] = [
    "Description (verbatim)",
    "Exits (as reported)",
    "Blocked movements",
    "Hidden/conditional transitions",
    "Objects present",
    "Hazards/NPCs",
    "Key parser interactions",
    "State notes",
    "Mapping notes",
]

# Which sections should become arrays vs strings vs mapping objects
SECTION_TYPE: Dict[str, str] = {
    "Description (verbatim)": "string",
    "Exits (as reported)": "list",
    "Blocked movements": "list",
    "Hidden/conditional transitions": "list",
    "Objects present": "list",
    "Hazards/NPCs": "list",
    "Key parser interactions": "list",
    "State notes": "list",
    "Mapping notes": "kv",
}


H1_RE = re.compile(r"^#\s+(?P<title>.+?)\s*$")
H2_RE = re.compile(r"^##\s+(?P<h2>.+?)\s*$")
BULLET_RE = re.compile(r"^\s*[-*]\s+(?P<item>.+?)\s*$")
KV_RE = re.compile(r"^\s*\*\*(?P<key>.+?)\*\*:\s*(?P<val>.*)\s*$")  # **Key**: Value
KV_PLAIN_RE = re.compile(r"^\s*(?P<key>[^:]{1,60}):\s*(?P<val>.*)\s*$")  # Key: Value


@dataclass
class ParseError(Exception):
    path: Path
    message: str

    def __str__(self) -> str:
        return f"{self.path}: {self.message}"


def split_into_blocks(lines: List[str]) -> Tuple[str, Dict[str, List[str]]]:
    """
    Returns (title, blocks_by_h2), where blocks_by_h2 maps each H2 heading to its raw lines.
    Enforces: exactly one H1, H2 headings must be unique, no content before H1.
    """
    title: Optional[str] = None
    blocks: Dict[str, List[str]] = {}
    current_h2: Optional[str] = None

    # strip only trailing newlines; keep content
    for i, raw in enumerate(lines):
        line = raw.rstrip("\n")

        if title is None:
            # allow leading blank lines
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

        # content line
        if current_h2 is None:
            # content after H1 but before first H2 is not allowed in v1.0
            if line.strip() != "":
                raise ValueError(f"Content found before first H2 section (line {i+1}).")
            continue

        blocks[current_h2].append(line)

    if title is None:
        raise ValueError("Missing H1 '# ...' title.")

    return title, blocks


def enforce_h2_set_and_order(blocks: Dict[str, List[str]]) -> None:
    found = list(blocks.keys())
    allowed = set(CANONICAL_H2_ORDER)

    extras = [h for h in found if h not in allowed]
    missing = [h for h in CANONICAL_H2_ORDER if h not in blocks]

    if extras:
        raise ValueError(f"Extra H2 headings not allowed: {extras}")
    if missing:
        raise ValueError(f"Missing required H2 headings: {missing}")

    # Order enforcement (strict): H2s must appear in canonical order in the markdown
    # We can check by comparing the sequence of encountered H2s to canonical order filtered.
    # Because all are required in v1.0, we expect exact match.
    if found != CANONICAL_H2_ORDER:
        raise ValueError(
            "H2 order mismatch.\n"
            f"Expected: {CANONICAL_H2_ORDER}\n"
            f"Found:    {found}"
        )


def parse_list_section(raw_lines: List[str]) -> List[str]:
    """
    Parse bullets from a section. Accepts:
    - bullet lines '- ...' or '* ...'
    - blank lines (ignored)
    - any non-bullet non-blank line -> treated as a single item line (strictness knob)
    """
    items: List[str] = []
    for line in raw_lines:
        if line.strip() == "":
            continue
        m = BULLET_RE.match(line)
        if m:
            items.append(m.group("item").strip())
        else:
            # strict: treat as a single item (helps if you forgot hyphen)
            items.append(line.strip())

    return items


def parse_string_section(raw_lines: List[str]) -> str:
    """
    Join raw lines into a paragraph-preserving string.
    Strip leading/trailing blank lines but keep internal newlines.
    """
    # trim blank edges
    start = 0
    end = len(raw_lines)
    while start < end and raw_lines[start].strip() == "":
        start += 1
    while end > start and raw_lines[end - 1].strip() == "":
        end -= 1
    return "\n".join(raw_lines[start:end]).strip()


def parse_mapping_notes(raw_lines: List[str]) -> Dict[str, object]:
    """
    Parse mapping notes as key/value pairs. Accept either:
    - **Internal ID**: Z1-R-001
    - Internal ID: Z1-R-001

    Any non-KV bullet/prose lines are collected under Notes: [...]
    """
    out: Dict[str, object] = {}
    notes: List[str] = []

    for line in raw_lines:
        if line.strip() == "":
            continue

        m = KV_RE.match(line) or KV_PLAIN_RE.match(line)
        if m:
            key = m.group("key").strip()
            val = m.group("val").strip()
            out[key] = val
            continue

        mb = BULLET_RE.match(line)
        if mb:
            notes.append(mb.group("item").strip())
        else:
            notes.append(line.strip())

    if notes:
        out["Notes"] = notes

    return out

EXIT_TOKEN_RE = re.compile(
    r"""^\s*
    (?P<prefix>\([^)]*\)\s*)?                                  # optional leading "(...)" like "(Once inside boat) "
    (?P<token>N|S|E|W|NE|NW|SE|SW|U|D|WAIT|LAND|LAUNCH)         # command/direction token
    (?P<inline>\s*\([^)]*\)\s*)?                               # optional inline "(...)" like "LAND (on west shore)"
    (?P<colon>\s*:)?\s*                                        # optional colon like "N (condition):"
    →\s*
    (?P<link>\[\[Z1 - [^\]]+\]\])                              # the wiki link
    (?P<trailing>\s+.*)?\s*$                                   # optional trailing notes like "(requires Rope)"
    """,
    re.VERBOSE,
)

PLACEHOLDER_EXITS = {"None", "(none)", "*", "-"}

def parse_exits_section(raw_lines: List[str]) -> Tuple[List[str], List[str]]:
    """
    Returns (clean_exits, extracted_notes).
    clean_exits matches strict schema like: 'N → [[Z1 - Room]]'
    extracted_notes are pushed into Hidden/conditional transitions.
    """
    items = parse_list_section(raw_lines)

    clean: List[str] = []
    notes: List[str] = []

    for item in items:
        s = item.strip()
        if not s or s in PLACEHOLDER_EXITS:
            continue

        m = EXIT_TOKEN_RE.match(s)
        if not m:
            # Fail fast: this is a real formatting anomaly you should fix manually
            raise ValueError(f"Exit line not in canonicalizable form: {s!r}")

        token = m.group("token")
        link = m.group("link")
        clean_exit = f"{token} → {link}"
        clean.append(clean_exit)

        # Collect any conditions/annotations into notes
        note_parts: List[str] = []
        for g in ("prefix", "inline", "trailing"):
            val = m.group(g)
            if val:
                val = val.strip()
                if val:
                    note_parts.append(val)

        if note_parts:
            # Put this into Hidden/conditional transitions in a stable, searchable form
            notes.append(f"Exit condition for {clean_exit}: " + " ".join(note_parts))

    return clean, notes


def normalize_room_markdown(md_path: Path) -> Dict:
    text = md_path.read_text(encoding="utf-8")
    lines = text.splitlines(True)

    try:
        parsed_h1, blocks = split_into_blocks(lines)
        enforce_h2_set_and_order(blocks)

        # Canonical title authority: filename stem (e.g., "Z1 - Behind House")
        title_from_filename = md_path.stem.strip()

        if parsed_h1 != title_from_filename and parsed_h1 != title_from_filename.replace("Z1 - ", "").strip():
            print(f"WARNING: {md_path.name}: H1 '{parsed_h1}' does not match filename '{title_from_filename}'")

        title = title_from_filename  # OVERRIDE

        sections_out: Dict[str, object] = {}
        exit_notes: List[str] = []

        for h2 in CANONICAL_H2_ORDER:
            raw = blocks.get(h2, [])
            kind = SECTION_TYPE[h2]

            if h2 == "Exits (as reported)":
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
                raise ValueError(f"Unknown section type: {kind}")

        # Append extracted exit conditions into Hidden/conditional transitions
        if exit_notes:
            # This is a required section in v1.0, but guard anyway
            if "Hidden/conditional transitions" not in sections_out or not isinstance(
                sections_out["Hidden/conditional transitions"], list
            ):
                sections_out["Hidden/conditional transitions"] = []
            sections_out["Hidden/conditional transitions"].extend(exit_notes)

        return {"title": title, "sections": sections_out}

    except ValueError as e:
        raise ParseError(md_path, str(e))

def main() -> int:
    ap = argparse.ArgumentParser(description="Normalize Zork room markdown into JSON objects.")
    ap.add_argument("--in", dest="in_dir", required=True, help="Input directory containing room .md files")
    ap.add_argument("--out", dest="out_dir", required=True, help="Output directory for normalized JSON")
    ap.add_argument("--glob", dest="glob", default="**/*.md", help="Glob pattern (default: **/*.md)")
    ap.add_argument("--fail-fast", action="store_true", help="Stop on first error")
    args = ap.parse_args()

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
            obj = normalize_room_markdown(md)
            out_path = out_dir / (md.stem + ".json")
            out_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            count_ok += 1
        except ParseError as e:
            errors.append(str(e))
            if args.fail_fast:
                print(errors[-1])
                return 1

    if errors:
        print(f"\nNormalization completed with errors ({len(errors)}).")
        for msg in errors:
            print(" - " + msg)
        print(f"\nOK: {count_ok} / {len(md_files)}")
        return 1

    print(f"Normalization successful. OK: {count_ok} / {len(md_files)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
