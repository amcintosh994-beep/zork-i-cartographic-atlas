#!/usr/bin/env python3
"""
normalize_rooms.py

Deterministically normalizes Zork room Markdown notes to a canonical schema:
- Ensures all required sections exist
- Enforces section order and heading levels
- Normalizes bullet style and blank lines
- Produces an audit report (CSV) of changes and issues

Usage:
  python normalize_rooms.py --root /path/to/rooms --check
  python normalize_rooms.py --root /path/to/rooms --write --backup

Notes:
- Unknown H2 sections are preserved under "## Appendix (non-canonical)" unless --drop-unknown is used.
- Idempotent: running twice should produce no further diffs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Optional

CANONICAL_SECTIONS: List[str] = [
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

APPENDIX_HEADER = "Appendix (non-canonical)"

H1_RE = re.compile(r"^#\s+(.+?)\s*$")
H2_RE = re.compile(r"^##\s+(.+?)\s*$")

def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def normalize_bullets(text: str) -> str:
    # Convert leading "* " bullets to "- "
    text = re.sub(r"(?m)^\*\s+", "- ", text)
    # Normalize Unicode bullets if present
    text = re.sub(r"(?m)^[•·]\s+", "- ", text)
    return text

def normalize_newlines(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text

def strip_trailing_ws(text: str) -> str:
    return re.sub(r"(?m)[ \t]+$", "", text)

def ensure_single_blank_lines(block: str) -> str:
    # Collapse 3+ blank lines to 2 max, then later we enforce single spacing between sections.
    block = re.sub(r"\n{3,}", "\n\n", block)
    return block

@dataclass
class ParseResult:
    title: str
    sections: Dict[str, str]          # known sections content
    unknown_sections: Dict[str, str]  # unknown H2 sections content
    issues: List[str]

def parse_markdown(md: str, default_title: str) -> ParseResult:
    issues: List[str] = []
    md = normalize_newlines(md)

    lines = md.split("\n")

    # Find first H1
    title = default_title
    h1_indices = [i for i, ln in enumerate(lines) if H1_RE.match(ln)]
    if not h1_indices:
        issues.append("missing_h1")
    else:
        if len(h1_indices) > 1:
            issues.append("multiple_h1")
        m = H1_RE.match(lines[h1_indices[0]])
        if m:
            title = m.group(1).strip()

    # Collect H2 blocks (tolerant: everything before first H2 after H1 is ignored except title)
    section_starts: List[Tuple[int, str]] = []
    for i, ln in enumerate(lines):
        m = H2_RE.match(ln)
        if m:
            section_starts.append((i, m.group(1).strip()))

    sections: Dict[str, str] = {}
    unknown: Dict[str, str] = {}

    if not section_starts:
        issues.append("missing_all_h2")
        return ParseResult(title=title, sections={}, unknown_sections={}, issues=issues)

    for idx, (start_i, header) in enumerate(section_starts):
        end_i = section_starts[idx + 1][0] if idx + 1 < len(section_starts) else len(lines)
        content_lines = lines[start_i + 1 : end_i]
        # Trim leading/trailing blank lines in content
        while content_lines and content_lines[0].strip() == "":
            content_lines.pop(0)
        while content_lines and content_lines[-1].strip() == "":
            content_lines.pop()
        content = "\n".join(content_lines).strip()

        if header in sections or header in unknown:
            issues.append(f"duplicate_section:{header}")

        if header in CANONICAL_SECTIONS:
            sections[header] = content
        else:
            unknown[header] = content
            issues.append(f"unknown_section:{header}")

    # Detect missing canonical sections
    for h in CANONICAL_SECTIONS:
        if h not in sections:
            issues.append(f"missing_section:{h}")

    # Detect out-of-order canonical sections (based on first occurrence order)
    observed_order = [h for (_, h) in section_starts if h in CANONICAL_SECTIONS]
    if observed_order:
        canonical_filtered = [h for h in CANONICAL_SECTIONS if h in observed_order]
        # If observed order differs from canonical order (restricted to present headers), flag
        obs_unique = []
        for h in observed_order:
            if h not in obs_unique:
                obs_unique.append(h)
        if obs_unique != canonical_filtered:
            issues.append("out_of_order_sections")

    return ParseResult(title=title, sections=sections, unknown_sections=unknown, issues=issues)

def placeholder_for(header: str) -> str:
    # One consistent placeholder convention. Adjust to your taste, but keep it invariant.
    # I treat most sections as list-like by default.
    list_like = {
        "Exits (as reported)",
        "Blocked movements",
        "Hidden/conditional transitions",
        "Objects present",
        "Hazards/NPCs",
        "Key parser interactions",
    }
    return "- (none)" if header in list_like else "(none)"

def rebuild_markdown(pr: ParseResult, keep_unknown: bool = True) -> str:
    # Build canonical output with normalized formatting.
    parts: List[str] = []
    parts.append(f"# {pr.title}".strip())
    parts.append("")  # blank line after title

    for header in CANONICAL_SECTIONS:
        parts.append(f"## {header}")
        content = pr.sections.get(header, "").strip()
        if not content:
            content = placeholder_for(header)
        content = normalize_bullets(content)
        content = strip_trailing_ws(content)
        parts.append(content)
        parts.append("")  # blank line between sections

    if keep_unknown and pr.unknown_sections:
        parts.append(f"## {APPENDIX_HEADER}")
        parts.append("- (preserved content from non-canonical headers)")
        parts.append("")
        for uh, ucontent in pr.unknown_sections.items():
            parts.append(f"### {uh}")
            parts.append(ucontent.strip() if ucontent.strip() else "(none)")
            parts.append("")
    # Final cleanup: trim trailing blank lines, enforce newline at EOF
    out = "\n".join(parts)
    out = ensure_single_blank_lines(out)
    out = out.strip() + "\n"
    return out

def iter_markdown_files(root: Path) -> List[Path]:
    files = []
    for p in root.rglob("*.md"):
        if p.is_file():
            files.append(p)
    return sorted(files)

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="Root directory containing room .md files")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="Only report issues, do not modify files")
    mode.add_argument("--write", action="store_true", help="Rewrite files in place to canonical schema")
    ap.add_argument("--backup", action="store_true", help="Create .bak copies before writing")
    ap.add_argument("--drop-unknown", action="store_true", help="Drop non-canonical sections instead of preserving them in an appendix")
    ap.add_argument("--report", default="normalization_report.csv", help="CSV report path (relative to root unless absolute)")
    args = ap.parse_args()

    root = Path(args.root).expanduser().resolve()
    if not root.exists():
        raise SystemExit(f"Root not found: {root}")

    report_path = Path(args.report)
    if not report_path.is_absolute():
        report_path = root / report_path

    files = iter_markdown_files(root)
    if not files:
        raise SystemExit(f"No .md files found under: {root}")

    rows = []
    changed_count = 0
    issue_count = 0

    for fp in files:
        original = fp.read_text(encoding="utf-8")
        default_title = fp.stem.replace("_", " ").strip()
        pr = parse_markdown(original, default_title=default_title)

        normalized = rebuild_markdown(pr, keep_unknown=not args.drop_unknown)

        orig_hash = sha256_text(normalize_newlines(original))
        norm_hash = sha256_text(normalize_newlines(normalized))
        changed = orig_hash != norm_hash

        if pr.issues:
            issue_count += 1

        if args.write and changed:
            if args.backup:
                bak = fp.with_suffix(fp.suffix + ".bak")
                if not bak.exists():
                    shutil.copy2(fp, bak)
            fp.write_text(normalized, encoding="utf-8")
            changed_count += 1

        rows.append({
            "file": str(fp.relative_to(root)),
            "changed": "yes" if changed else "no",
            "issues": ";".join(pr.issues) if pr.issues else "",
            "unknown_sections_count": str(len(pr.unknown_sections)),
        })

    with report_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["file", "changed", "issues", "unknown_sections_count"])
        w.writeheader()
        w.writerows(rows)

    print(f"Scanned: {len(files)} files")
    print(f"Issues found in: {issue_count} files")
    if args.write:
        print(f"Rewritten: {changed_count} files")
    print(f"Report: {report_path}")

if __name__ == "__main__":
    main()
