#!/usr/bin/env python3
"""Merge mechanical index + semantic fragments into rules.json.

Inputs (read):
  - specs/<X>/.rule_index.json
      mechanical fields per marker (id, authority, system_flags,
      sections, text, line)
  - specs/<X>/.rules_fragments/*.json
      either a single object `{records: [{id, trigger, behavior,
      modality, examples}, ...]}` or a workflow result object
      `{fragments: [{section_path, records: [...]}, ...]}` --
      the workflow's aggregate dump.

Output (write):
  - specs/<X>/rules.json
      list of joined records; one per rule marker.

Validates: every mechanical id has exactly one semantic record;
modality in {must, should}; authority in valid set or null;
every referenced `eg` tag exists in anonymized_annotated.md.

Usage: build_rules.py specs/<X>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

AUTHORITY = {"root", "system", "developer", "user", "guideline"}
MODALITY = {"must", "should"}
SEMANTIC_FIELDS = ("trigger", "behavior", "modality", "examples")
EG = re.compile(r"\[\^(eg\d{3})\]")
RULE = re.compile(r"\[\^(\w{4})\]")


def _flatten_records(payload):
    out = []
    if isinstance(payload, dict) and "records" in payload:
        out.extend(payload["records"])
    if isinstance(payload, dict) and "fragments" in payload:
        for frag in payload["fragments"]:
            out.extend(frag.get("records", []))
    return out


def build(spec_dir: Path) -> int:
    spec_name = spec_dir.name
    index_path = spec_dir / ".rule_index.json"
    frag_dir = spec_dir / ".rules_fragments"
    out_path = spec_dir / "rules.json"
    annotated_path = spec_dir / "anonymized_annotated.md"

    if not index_path.exists():
        sys.exit(f"missing {index_path} - run build_rule_index.py first")
    if not annotated_path.exists():
        sys.exit(f"missing {annotated_path}")
    if not frag_dir.exists() or not any(frag_dir.glob("*.json")):
        sys.exit(f"missing fragments under {frag_dir} - run the extract-rules workflow first")

    index = json.loads(index_path.read_text(encoding="utf-8"))
    mechanical = {r["id"]: r for r in index["rules"]}

    semantic: dict[str, dict] = {}
    dupes_seen: list[str] = []
    for f in sorted(frag_dir.glob("*.json")):
        payload = json.loads(f.read_text(encoding="utf-8"))
        for rec in _flatten_records(payload):
            rid = rec.get("id")
            if not rid:
                continue
            if rid in semantic:
                dupes_seen.append(rid)
                continue
            semantic[rid] = rec

    if dupes_seen:
        print(
            f"warn: {len(dupes_seen)} duplicate semantic records dropped "
            f"(first 5: {', '.join(dupes_seen[:5])})",
            file=sys.stderr,
        )

    missing = sorted(set(mechanical) - set(semantic))
    extra = sorted(set(semantic) - set(mechanical))
    failures: list[str] = []
    if missing:
        failures.append(
            f"{len(missing)} mechanical id(s) without a semantic record "
            f"(first 5: {', '.join(missing[:5])})"
        )
    if extra:
        failures.append(
            f"{len(extra)} semantic id(s) not in mechanical index (first 5: {', '.join(extra[:5])})"
        )

    annotated_text = annotated_path.read_text(encoding="utf-8")
    eg_tags = set(EG.findall(annotated_text))

    joined = []
    bad_modality: list[str] = []
    bad_authority: list[str] = []
    bad_examples: list[tuple[str, str]] = []
    for rid in sorted(mechanical):
        m = mechanical[rid]
        s = semantic.get(rid)
        if not s:
            continue
        modality = s.get("modality")
        if modality not in MODALITY:
            bad_modality.append(rid)
        authority = m.get("authority")
        if authority is not None and authority not in AUTHORITY:
            bad_authority.append(rid)
        examples = s.get("examples") or []
        for eg in examples:
            if eg not in eg_tags:
                bad_examples.append((rid, eg))
        joined.append(
            {
                "id": rid,
                "authority": authority,
                "system_flags": m.get("system_flags", []),
                "sections": m.get("sections", []),
                "text": m.get("text", ""),
                "trigger": s.get("trigger", ""),
                "behavior": s.get("behavior", ""),
                "modality": modality,
                "examples": examples,
            }
        )

    if bad_modality:
        failures.append(
            f"{len(bad_modality)} record(s) with modality not in {sorted(MODALITY)} "
            f"(first 5: {', '.join(bad_modality[:5])})"
        )
    if bad_authority:
        failures.append(
            f"{len(bad_authority)} record(s) with authority not in {sorted(AUTHORITY)} "
            f"(first 5: {', '.join(bad_authority[:5])})"
        )
    if bad_examples:
        sample = ", ".join(f"{r}->{e}" for r, e in bad_examples[:5])
        failures.append(
            f"{len(bad_examples)} record-example references to unknown eg tag (first 5: {sample})"
        )

    if failures:
        print(f"FAIL {spec_name}:")
        for f in failures:
            print(f"  - {f}")
        return 1

    out_path.write_text(
        json.dumps({"spec": spec_name, "rules": joined}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"OK {spec_name}: {len(joined)} rule records -> {out_path}")
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit("usage: build_rules.py specs/<X>")
    spec_dir = Path(sys.argv[1]).resolve()
    if not spec_dir.is_dir():
        sys.exit(f"not a directory: {spec_dir}")
    return build(spec_dir)


if __name__ == "__main__":
    sys.exit(main())
