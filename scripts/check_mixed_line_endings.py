#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Extensions that are almost certainly binary in your repo context.
BINARY_EXTS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".db",
}

def is_probably_binary(path: Path) -> bool:
    if path.suffix.lower() in BINARY_EXTS:
        return True
    # Heuristic: if NUL byte exists, treat as binary.
    try:
        data = path.read_bytes()
    except OSError:
        return True
    return b"\x00" in data

def has_mixed_eols(data: bytes) -> bool:
    """
    Mixed EOLs means at least one CRLF and at least one lone LF.
    - CRLF: b'\\r\\n'
    - lone LF: b'\\n' not immediately preceded by b'\\r'
    """
    if b"\n" not in data:
        return False  # no line endings at all
    has_crlf = b"\r\n" in data
    if not has_crlf:
        return False

    # Find any LF not preceded by CR.
    # Easiest: count all LFs and count CRLFs; lone LF exists if total LFs > CRLF count.
    total_lf = data.count(b"\n")
    total_crlf = data.count(b"\r\n")
    return total_lf > total_crlf

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("files", nargs="*", help="Files to check (provided by pre-commit).")
    args = parser.parse_args(argv)

    bad: list[str] = []

    for f in args.files:
        p = Path(f)
        if not p.exists() or p.is_dir():
            continue
        if is_probably_binary(p):
            continue

        try:
            data = p.read_bytes()
        except OSError:
            # If unreadable, fail closed.
            bad.append(f"{f} (unreadable)")
            continue

        if has_mixed_eols(data):
            bad.append(f)

    if bad:
        print("[EOL] Mixed line endings detected (CRLF + LF in same file).")
        for f in bad:
            print(f"  - {f}")
        print()
        print("Fix: convert the file to a single EOL style (LF recommended in-editor).")
        return 1

    return 0

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
