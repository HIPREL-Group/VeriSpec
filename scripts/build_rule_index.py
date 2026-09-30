#!/usr/bin/env python3
"""Build .rule_index.json: per-marker mechanical fields + section grouping.

For each rule marker [^wxyz] in specs/<X>/anonymized_annotated.md, emit
the mechanical (non-LLM) fields of the rule record:
  - id          : the 4-char marker id
  - authority   : inherited from the nearest ancestor header declaring
                  authority=... ({root, system, developer, user, guideline}),
                  then resolved through authority_overrides.json when an
                  unlabelled container owns the rule directly
  - system_flags: parsed from the nearest ancestor header tags=...
                  (here, only ["under_18"] occurs)
  - sections    : ordered ancestor slug chain (outermost -> innermost)
  - text        : the source line containing the marker, verbatim
  - line        : 1-indexed line number for human reference

Also emit `jobs`: one entry per innermost-section group, each carrying
the list of marker ids it owns. The orchestrator fans these out to
subagents.

Usage: build_rule_index.py specs/<X>

Writes specs/<X>/.rule_index.json.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from rule_authority import load_authority_overrides, resolve_authorities

RULE = re.compile(r"\[\^(\w{4})\]")  # 4-char ids; eg tags are 5 chars
HEADER = re.compile(r"^(#{1,6})\s+(.*?)\s*(?:\{(.+?)\})?\s*$")
ATTR_ANCHOR = re.compile(r"#([\w_]+)")
ATTR_KV = re.compile(r"(\w+)=(\S+)")


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")


def parse_attrs(block: str | None):
    anchor = None
    kvs: dict[str, str] = {}
    if not block:
        return anchor, kvs
    m = ATTR_ANCHOR.search(block)
    if m:
        anchor = m.group(1)
    for k, v in ATTR_KV.findall(block):
        if k == "tags":
            v = v.rstrip("}")
        kvs[k] = v
    return anchor, kvs


def build(spec_dir: Path) -> int:
    anon_path = spec_dir / "anonymized_annotated.md"
    if not anon_path.exists():
        sys.exit(f"missing anonymized_annotated.md under {spec_dir}")

    lines = anon_path.read_text(encoding="utf-8").splitlines()
    stack: list[dict] = []
    records: list[dict] = []
    sections_meta: dict[str, dict] = {}
    in_fence = False

    def close_section(sec: dict, end_line: int):
        key = "/".join(sec["path"])
        if key not in sections_meta:
            sections_meta[key] = {
                "path": list(sec["path"]),
                "start_line": sec["start_line"],
                "end_line": end_line,
            }

    for i, line in enumerate(lines, 1):
        s = line.lstrip()
        if s.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue

        hm = HEADER.match(line)
        if hm:
            level = len(hm.group(1))
            title = hm.group(2).strip()
            anchor, kvs = parse_attrs(hm.group(3))
            while stack and stack[-1]["level"] >= level:
                close_section(stack.pop(), i - 1)
            slug = anchor or slugify(title)
            authority = kvs.get("authority")
            tags = kvs.get("tags")
            if authority is None and stack:
                authority = stack[-1]["authority"]
            if tags is None and stack:
                tags = stack[-1]["tags"]
            path = [s["slug"] for s in stack] + [slug]
            stack.append(
                {
                    "level": level,
                    "slug": slug,
                    "path": path,
                    "authority": authority,
                    "tags": tags,
                    "start_line": i,
                }
            )
            continue

        for m in RULE.finditer(line):
            rid = m.group(1)
            sections = [s["slug"] for s in stack]
            sys_flags: list[str] = []
            if stack and stack[-1]["tags"]:
                sys_flags = [t.strip() for t in stack[-1]["tags"].split(",") if t.strip()]
            authority = stack[-1]["authority"] if stack else None
            records.append(
                {
                    "id": rid,
                    "authority": authority,
                    "system_flags": sys_flags,
                    "sections": sections,
                    "text": line,
                    "line": i,
                }
            )

    while stack:
        close_section(stack.pop(), len(lines))

    seen_ids: dict[str, int] = {}
    for r in records:
        seen_ids[r["id"]] = seen_ids.get(r["id"], 0) + 1
    dupes = sorted(i for i, c in seen_ids.items() if c > 1)
    if dupes:
        sys.exit(f"duplicate rule-marker ids in source: {', '.join(dupes)}")

    try:
        overrides = load_authority_overrides(spec_dir)
        resolved = resolve_authorities({r["id"]: r["authority"] for r in records}, overrides)
    except ValueError as exc:
        sys.exit(str(exc))
    for record in records:
        record["authority"] = resolved[record["id"]]
    if overrides:
        print(
            f"info: applied {len(overrides)} explicit authority resolution(s) "
            f"from {spec_dir / 'authority_overrides.json'}",
            file=sys.stderr,
        )

    no_auth = [r["id"] for r in records if not r["authority"]]
    if no_auth:
        print(
            f"warn: {len(no_auth)} rule marker(s) have no inherited authority "
            f"(authority=null): {', '.join(no_auth)}",
            file=sys.stderr,
        )

    groups: dict[str, list[str]] = {}
    for r in records:
        key = "/".join(r["sections"]) if r["sections"] else ""
        groups.setdefault(key, []).append(r["id"])

    jobs = []
    for k, ids in groups.items():
        meta = sections_meta.get(k, {})
        jobs.append(
            {
                "section_path": k,
                "marker_ids": ids,
                "start_line": meta.get("start_line"),
                "end_line": meta.get("end_line"),
            }
        )
    jobs.sort(key=lambda j: -len(j["marker_ids"]))

    out = {"spec": spec_dir.name, "rules": records, "jobs": jobs}
    out_path = spec_dir / ".rule_index.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False))

    print(
        f"OK {spec_dir.name}: indexed {len(records)} rule markers across "
        f"{len(jobs)} innermost-section job(s) -> {out_path}"
    )
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit("usage: build_rule_index.py specs/<X>")
    spec_dir = Path(sys.argv[1]).resolve()
    if not spec_dir.is_dir():
        sys.exit(f"not a directory: {spec_dir}")
    return build(spec_dir)


if __name__ == "__main__":
    sys.exit(main())
