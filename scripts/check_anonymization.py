#!/usr/bin/env python3
"""Verify every changed line in anonymized.md mentions a Lumen Labs brand word.

Usage: check_anonymization.py specs/<X>

For each line where raw.md and anonymized.md differ, asserts the
anonymized line contains "lumen" or "lumo" (case-insensitive substring).
Anonymization is supposed to introduce brand replacements, so any
rewritten line that lacks all brand markers is suspicious.
"""

from __future__ import annotations

import sys
from pathlib import Path

BRAND_MARKERS = ("lumen", "lumo")


def check(spec_dir: Path) -> int:
    raw_path = spec_dir / "raw.md"
    anon_path = spec_dir / "anonymized.md"
    if not raw_path.exists() or not anon_path.exists():
        sys.exit(f"missing raw.md or anonymized.md under {spec_dir}")

    raw = raw_path.read_text().splitlines()
    anon = anon_path.read_text().splitlines()
    if len(raw) != len(anon):
        sys.exit(
            f"line count mismatch: raw={len(raw)} anonymized={len(anon)}. "
            "Anonymization must preserve line count."
        )

    failures: list[tuple[int, str, str]] = []
    differing = 0
    for i, (r, a) in enumerate(zip(raw, anon), 1):
        if r == a:
            continue
        differing += 1
        a_lower = a.lower()
        if not any(m in a_lower for m in BRAND_MARKERS):
            failures.append((i, r, a))

    spec_name = spec_dir.name
    if failures:
        markers = "/".join(BRAND_MARKERS)
        print(f"FAIL {spec_name}: {len(failures)} changed line(s) lack a brand marker ({markers})")
        for i, r, a in failures:
            print(f"  line {i}:")
            print(f"    raw : {r}")
            print(f"    anon: {a}")
        return 1

    print(
        f"OK {spec_name}: {differing}/{len(raw)} substituted lines, "
        f"all contain a brand marker ({'/'.join(BRAND_MARKERS)})"
    )
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit("usage: check_anonymization.py specs/<X>")
    spec_dir = Path(sys.argv[1]).resolve()
    if not spec_dir.is_dir():
        sys.exit(f"not a directory: {spec_dir}")
    return check(spec_dir)


if __name__ == "__main__":
    sys.exit(main())
