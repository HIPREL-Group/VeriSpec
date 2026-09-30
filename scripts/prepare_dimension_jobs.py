#!/usr/bin/env python3
"""Materialize per-dimension input packets for stage-2 semantic pass B.

Pass B authors typed relatedness edges among the rules of a single behavioral
dimension. This helper reads the dimension registry, the pass-A section
fragments (which carry the multi-label dimension assignment), the mechanical
graph, and the rule inventory, and writes one packet per dimension key to
``specs/<X>/.dimension_jobs/<key>.json``.

Each packet carries the registry entry and, for every member rule, the fields
an edge author needs: authority and modality, the verbatim rule text and its
sentence, list framing, facets, exceptions, definitions, and the in-section
example verdicts.

Usage: prepare_dimension_jobs.py specs/<X> [--min-members 2]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

JOBS_DIR = ".dimension_jobs"
FRAG_SECTION = ".grouping_fragments/section"


def build(spec_dir: Path, min_members: int) -> int:
    rules = {r["id"]: r for r in json.loads((spec_dir / "rules.json").read_text())["rules"]}
    graph = {r["id"]: r for r in json.loads((spec_dir / ".rule_graph.json").read_text())["rules"]}
    registry = json.loads((spec_dir / "dimensions.json").read_text())["dimensions"]

    enrich: dict[str, dict] = {}
    frags = sorted((spec_dir / FRAG_SECTION).glob("*.json"))
    if not frags:
        sys.exit(f"no pass-A fragments under {spec_dir / FRAG_SECTION}")
    for path in frags:
        for rec in json.loads(path.read_text()).get("records", []):
            if rec.get("id") in rules:
                enrich[rec["id"]] = rec

    members: dict[str, list[str]] = {d["key"]: [] for d in registry}
    for rid, rec in enrich.items():
        for key in rec.get("dimensions") or []:
            if key in members:
                members[key].append(rid)

    out_dir = spec_dir / JOBS_DIR
    out_dir.mkdir(exist_ok=True)
    for stale in out_dir.glob("*.json"):
        stale.unlink()

    written = []
    for d in registry:
        key = d["key"]
        ids = sorted(members[key])
        if len(ids) < min_members:
            continue
        entries = []
        for rid in ids:
            rec, ctx, en = rules[rid], graph[rid]["context"], enrich[rid]
            entries.append(
                {
                    "id": rid,
                    "authority": rec["authority"],
                    "modality": rec["modality"],
                    "system_flags": rec["system_flags"],
                    "sections": rec["sections"],
                    "section_anchor": ctx["section_anchor"],
                    "text": rec["text"],
                    "sentence": ctx["sentence"],
                    "trigger": rec["trigger"],
                    "behavior": rec["behavior"],
                    "stem": ctx["stem"],
                    "framing": ctx["framing"],
                    "line": ctx["line"],
                    "dimensions": en.get("dimensions") or [],
                    "facets": en.get("facets") or {},
                    "exceptions": en.get("exceptions") or [],
                    "definitions": en.get("definitions") or [],
                    "meta_resolution": en.get("meta_resolution") or [],
                    "examples": [
                        {
                            "id": ex["id"],
                            "title": ex.get("title"),
                            "verdicts": ex.get("verdicts", []),
                        }
                        for ex in ctx["section_examples"]
                    ],
                }
            )
        payload = {
            "spec": spec_dir.name,
            "dimension": d,
            "member_count": len(ids),
            "members": entries,
        }
        (out_dir / f"{key}.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        written.append((key, len(ids)))

    print(f"OK {spec_dir.name}: {len(written)} dimension packet(s) -> {out_dir}")
    for key, n in sorted(written, key=lambda x: -x[1]):
        print(f"  {key:48s} {n:3d} member(s)")
    unassigned = sorted(set(rules) - set(enrich))
    if unassigned:
        print(
            f"  WARNING: {len(unassigned)} rule(s) lack pass-A enrichment: {', '.join(unassigned[:15])}"
        )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Materialize stage-2 pass-B dimension packets.")
    ap.add_argument("spec_dir", type=Path)
    ap.add_argument("--min-members", type=int, default=2)
    args = ap.parse_args()
    spec_dir = args.spec_dir.resolve()
    if not spec_dir.is_dir():
        sys.exit(f"not a directory: {spec_dir}")
    return build(spec_dir, args.min_members)


if __name__ == "__main__":
    sys.exit(main())
