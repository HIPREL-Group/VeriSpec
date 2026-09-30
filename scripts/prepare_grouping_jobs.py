#!/usr/bin/env python3
"""Materialize per-agent input packets for stage-2 semantic pass A.

The ``group-rules`` skill fans enrichment out over the innermost-section
partition recorded in ``specs/<X>/.rule_index.json``. This helper coalesces
that partition into a bounded number of agent packets and writes each packet
as a self-contained JSON document under
``specs/<X>/.grouping_jobs/<job_id>.json``, carrying for every rule in scope:

  * its inventory record (authority, sections, text, trigger, behavior,
    modality, examples);
  * its mechanical context from ``.rule_graph.json`` (sentence, stem and
    framing, ancestor guards, in-section commentary, in-section examples with
    verdict annotations, section-level references, authority provenance);
  * the cross-reference edges awaiting subtype classification, each with the
    verbatim citing sentence.

Coalescing is deterministic: sections are ordered by descending marker count
and assigned to the currently smallest packet, so repeated executions produce
identical packets.

Usage: prepare_grouping_jobs.py specs/<X> [--packets N]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

JOBS_DIR = ".grouping_jobs"


def build(spec_dir: Path, packets: int) -> int:
    index_path = spec_dir / ".rule_index.json"
    graph_path = spec_dir / ".rule_graph.json"
    rules_path = spec_dir / "rules.json"
    for p in (index_path, graph_path, rules_path):
        if not p.exists():
            sys.exit(f"missing {p} (run build_rule_index.py and build_rule_graph.py first)")

    index = json.loads(index_path.read_text(encoding="utf-8"))
    graph = {r["id"]: r for r in json.loads(graph_path.read_text(encoding="utf-8"))["rules"]}
    rules = {r["id"]: r for r in json.loads(rules_path.read_text(encoding="utf-8"))["rules"]}

    sections = sorted(index["jobs"], key=lambda j: (-len(j["marker_ids"]), j["section_path"]))
    buckets: list[dict] = [
        {"job_id": f"job{i + 1:02d}", "sections": [], "size": 0} for i in range(packets)
    ]
    for sec in sections:
        target = min(buckets, key=lambda b: (b["size"], b["job_id"]))
        target["sections"].append(sec)
        target["size"] += len(sec["marker_ids"])

    out_dir = spec_dir / JOBS_DIR
    out_dir.mkdir(exist_ok=True)
    for stale in out_dir.glob("*.json"):
        stale.unlink()

    written = []
    for bucket in buckets:
        if not bucket["sections"]:
            continue
        payload_sections = []
        for sec in sorted(bucket["sections"], key=lambda s: s["start_line"] or 0):
            entries = []
            for rid in sorted(sec["marker_ids"]):
                rec = rules[rid]
                ctx = graph[rid]["context"]
                xrefs = [
                    {
                        "target_id": e["id"],
                        "anchor": e.get("anchor"),
                        "citing_sentence": e.get("citing_sentence"),
                    }
                    for e in graph[rid]["edges"]
                    if e["relation"] == "cross_reference"
                ]
                entries.append(
                    {
                        "id": rid,
                        "authority": rec["authority"],
                        "modality": rec["modality"],
                        "system_flags": rec["system_flags"],
                        "sections": rec["sections"],
                        "text": rec["text"],
                        "trigger": rec["trigger"],
                        "behavior": rec["behavior"],
                        "inventory_examples": rec["examples"],
                        "line": ctx["line"],
                        "sentence": ctx["sentence"],
                        "stem": ctx["stem"],
                        "framing": ctx["framing"],
                        "ancestor_guards": ctx["ancestor_guards"],
                        "commentary": ctx["commentary"],
                        "section_examples": ctx["section_examples"],
                        "section_references": ctx["section_references"],
                        "authority_provenance": ctx["authority_provenance"],
                        "cross_reference_edges": xrefs,
                    }
                )
            payload_sections.append(
                {
                    "section_path": sec["section_path"],
                    "start_line": sec["start_line"],
                    "end_line": sec["end_line"],
                    "marker_ids": sorted(sec["marker_ids"]),
                    "rules": entries,
                }
            )
        payload = {
            "spec": spec_dir.name,
            "job_id": bucket["job_id"],
            "rule_count": bucket["size"],
            "section_count": len(payload_sections),
            "sections": payload_sections,
        }
        path = out_dir / f"{bucket['job_id']}.json"
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
        written.append((bucket["job_id"], len(payload_sections), bucket["size"]))

    total = sum(w[2] for w in written)
    print(f"OK {spec_dir.name}: {len(written)} packet(s), {total} rules -> {out_dir}")
    for job_id, nsec, nrules in written:
        print(f"  {job_id}: {nsec:2d} section(s), {nrules:3d} rule(s)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Materialize stage-2 pass-A job packets.")
    ap.add_argument("spec_dir", type=Path)
    ap.add_argument("--packets", type=int, default=12)
    args = ap.parse_args()
    spec_dir = args.spec_dir.resolve()
    if not spec_dir.is_dir():
        sys.exit(f"not a directory: {spec_dir}")
    return build(spec_dir, args.packets)


if __name__ == "__main__":
    sys.exit(main())
