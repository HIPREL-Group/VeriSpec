#!/usr/bin/env python3
"""Replace auto-labeled ``[?](#anchor)`` links with heading titles.

The upstream Model Spec renderer treats ``?`` as a placeholder and displays
the title of the heading identified by the fragment. Standard Markdown
renderers and LLM prompts do not perform that substitution, so this script
creates a derived, prompt-ready document without changing the source artifact.

Usage:
    python3 scripts/resolve_crossrefs.py INPUT [OUTPUT]

If OUTPUT is omitted, ``_resolved`` is appended to INPUT's stem.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s+\{([^}]*)\}\s*$", re.MULTILINE)
ANCHOR_RE = re.compile(r"(?:^|\s)#([A-Za-z0-9_-]+)(?=\s|$)")
AUTO_LINK_RE = re.compile(r"\[\?\]\(#([A-Za-z0-9_-]+)\)")


def heading_titles(text: str) -> dict[str, str]:
    titles: dict[str, str] = {}
    for match in HEADING_RE.finditer(text):
        title, attributes = match.groups()
        anchor_match = ANCHOR_RE.search(attributes)
        if anchor_match is None:
            continue
        anchor = anchor_match.group(1)
        if anchor in titles:
            sys.exit(f"duplicate heading anchor: #{anchor}")
        titles[anchor] = title.strip()
    return titles


def resolve(text: str) -> tuple[str, int]:
    titles = heading_titles(text)
    referenced = set(AUTO_LINK_RE.findall(text))
    missing = sorted(referenced - titles.keys())
    if missing:
        formatted = ", ".join(f"#{anchor}" for anchor in missing)
        sys.exit(f"unresolved heading anchor(s): {formatted}")

    count = 0

    def replacement(match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        anchor = match.group(1)
        return f"[{titles[anchor]}](#{anchor})"

    return AUTO_LINK_RE.sub(replacement, text), count


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolve [?](#anchor) links using their heading titles."
    )
    parser.add_argument("input", type=Path, help="Annotated Markdown source")
    parser.add_argument("output", type=Path, nargs="?", help="Derived Markdown output")
    args = parser.parse_args()

    source = args.input.resolve()
    if not source.is_file():
        sys.exit(f"not a file: {source}")

    output = args.output
    if output is None:
        output = source.with_name(f"{source.stem}_resolved{source.suffix}")
    else:
        output = output.resolve()
    if output == source:
        sys.exit("output must differ from input; the source artifact is read-only")

    text = source.read_text(encoding="utf-8")
    resolved, count = resolve(text)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(resolved, encoding="utf-8")
    print(f"OK: resolved {count} cross-reference(s) -> {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
