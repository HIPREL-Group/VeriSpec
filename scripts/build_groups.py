#!/usr/bin/env python3
"""Merge stage-2 fragments and emit specs/<X>/grouped_rules.json.

Implements steps 5 and 6 of the ``group-rules`` skill: it joins the mechanical
graph with the semantic fragments of passes A and B, rejects semantic material
that is not textually grounded, generates the semantic-adjacency edges from
the dimension labelling, symmetrizes the edge set, and emits the two-tier
group family.

Group families (both unbounded; no splitting or covering constructions)
  dimension  one group per behavioral-dimension key, tier primary,
             gid = dim:<key>
  section    one group per innermost section owning >=1 rule, tier
             secondary, gid = sec:<section path>

Stage 2 asserts relatedness only. No opposition relation exists;
conflict identification belongs to stage 3.

Usage: build_groups.py specs/<X>

Writes specs/<X>/grouped_rules.json and prints the verification report.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

RESOLVED = "anonymized_annotated_resolved.md"
FRAG_SECTION = ".grouping_fragments/section"
FRAG_DIMENSION = ".grouping_fragments/dimension"

XREF_SUBTYPES = {"defers_to", "carves_exception_from", "tightens", "style_modulates", "background"}
THEMATIC_SUBTYPES = {"reinforces", "conditions", "specializes"}
FACET_VALUES = {"applies", "excluded", "unconditional_or_unspecified"}
FACETS = ("surface", "modality", "age", "setting", "state")
MARKER = re.compile(r"\[\^\w+\]")


def normalize(text: str) -> str:
    """Whitespace- and typography-normalized form used for quote grounding."""
    text = unicodedata.normalize("NFKC", text)
    for src, dst in (
        ("’", "'"),
        ("‘", "'"),
        ("“", '"'),
        ("”", '"'),
        ("—", "-"),
        ("–", "-"),
        ("…", "..."),
    ):
        text = text.replace(src, dst)
    text = MARKER.sub("", text)
    text = re.sub(r"-{2,}", "-", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def build(spec_dir: Path) -> int:
    rules_list = load_json(spec_dir / "rules.json")["rules"]
    rules = {r["id"]: r for r in rules_list}
    graph_doc = load_json(spec_dir / ".rule_graph.json")
    graph = {r["id"]: r for r in graph_doc["rules"]}
    registry = load_json(spec_dir / "dimensions.json")["dimensions"]
    dim_keys = {d["key"] for d in registry}
    max_quote_words = graph_doc.get("config", {}).get("max_quote_words", 40)

    doc_raw = (spec_dir / RESOLVED).read_text(encoding="utf-8")
    doc_norm = normalize(doc_raw)
    anchors = set(re.findall(r"^#{1,6}\s+.*?\{#([\w-]+)", doc_raw, re.M))
    eg_tags = set(re.findall(r"\[\^(eg\d{3})\]", doc_raw))

    rejects: dict[str, int] = {}

    def reject(reason: str) -> None:
        rejects[reason] = rejects.get(reason, 0) + 1

    def grounded(quote: str | None) -> bool:
        if not quote or not isinstance(quote, str):
            return False
        needle = normalize(quote.replace("[...]", " "))
        return len(needle) >= 12 and needle in doc_norm

    def valid_where(where: str | None) -> bool:
        if not isinstance(where, str) or not where:
            return False
        if where.startswith("#"):
            return where[1:] in anchors
        m = re.fullmatch(r"\[\^(\w+)\]", where)
        if m:
            return m.group(1) in rules or m.group(1) in eg_tags
        return where in rules or where in eg_tags

    # --- pass A fragments --------------------------------------------------
    enrich: dict[str, dict] = {}
    frag_a = sorted((spec_dir / FRAG_SECTION).glob("*.json"))
    for path in frag_a:
        for rec in load_json(path).get("records", []):
            rid = rec.get("id")
            if rid not in rules:
                reject("passA:unknown_rule_id")
                continue
            if rid in enrich:
                reject("passA:duplicate_record")
                continue
            dims = sorted({d for d in rec.get("dimensions") or [] if d in dim_keys})
            if len(dims) != len(rec.get("dimensions") or []):
                reject("passA:unknown_dimension_key")
            facets, specifics = {}, {}
            for f in FACETS:
                v = (rec.get("facets") or {}).get(f)
                if v in FACET_VALUES:
                    facets[f] = v
                elif isinstance(v, str) and v.strip() and len(v) <= 40:
                    facets[f] = "applies"
                    specifics[f] = v.strip()
                else:
                    facets[f] = None if f == "state" else "unconditional_or_unspecified"

            def keep_list(items, need_quote=True):
                out = []
                for it in items or []:
                    if (
                        isinstance(it, dict)
                        and valid_where(it.get("where"))
                        and (not need_quote or grounded(it.get("quote")))
                    ):
                        out.append(it)
                return out

            defs = keep_list(rec.get("definitions"))
            meta = keep_list(rec.get("meta_resolution"))
            exc = [
                e
                for e in keep_list(rec.get("exceptions"))
                if e.get("kind") in {"hard_edge", "judgment_delegated"}
            ]
            fev = [e for e in keep_list(rec.get("facet_evidence")) if e.get("facet") in FACETS]
            for name, kept, raw in (
                ("definitions", defs, rec.get("definitions")),
                ("meta_resolution", meta, rec.get("meta_resolution")),
                ("exceptions", exc, rec.get("exceptions")),
                ("facet_evidence", fev, rec.get("facet_evidence")),
            ):
                for _ in range(max(0, len(raw or []) - len(kept))):
                    reject(f"passA:{name}_ungrounded")
            ext = []
            for e in rec.get("external_examples") or []:
                if (
                    isinstance(e, dict)
                    and e.get("id") in eg_tags
                    and e.get("id") not in (rules[rid].get("examples") or [])
                ):
                    ext.append(e)
                else:
                    reject("passA:external_example_invalid")
            subtypes = {}
            for s in rec.get("xref_subtypes") or []:
                if (
                    isinstance(s, dict)
                    and s.get("target_id") in rules
                    and s.get("subtype") in XREF_SUBTYPES
                ):
                    subtypes[s["target_id"]] = s["subtype"]
                else:
                    reject("passA:xref_subtype_invalid")
            enrich[rid] = {
                "dimensions": dims,
                "facets": facets,
                "facet_specifics": specifics,
                "facet_evidence": fev,
                "exceptions": exc,
                "definitions": defs,
                "meta_resolution": meta,
                "external_examples": ext,
                "xref_subtypes": subtypes,
                "coverage_notes": rec.get("coverage_notes") or None,
            }

    dim_of = {rid: set(enrich.get(rid, {}).get("dimensions") or []) for rid in rules}

    # --- edges -------------------------------------------------------------
    edges: dict[str, dict[tuple, dict]] = {rid: {} for rid in rules}

    def put(src: str, dst: str, entry: dict) -> None:
        key = (dst, entry["relation"], entry.get("subtype"), entry.get("_k"))
        if key not in edges[src]:
            edges[src][key] = entry

    # mechanical, from the graph
    for rid, node in graph.items():
        for e in node["edges"]:
            entry = {
                "id": e["id"],
                "relation": e["relation"],
                "subtype": None,
                "direction": "none",
                "source": "mechanical",
                "evidence": None,
                "note": None,
            }
            if e["relation"] == "shares_example":
                entry["_k"] = e.get("via")
                entry["note"] = f"both illustrated by {e.get('via')}"
            if e["relation"] == "cross_reference":
                entry["direction"] = "out"
                entry["subtype"] = enrich.get(rid, {}).get("xref_subtypes", {}).get(e["id"])
                entry["evidence"] = {
                    "where": f"#{e['anchor']}" if e.get("anchor") else None,
                    "quote": e.get("citing_sentence"),
                }
                entry["note"] = "cited from the rule's own sentence"
            put(rid, e["id"], entry)
            mirror = dict(entry)
            mirror["id"] = rid
            if e["relation"] == "cross_reference":
                mirror["direction"] = "in"
                mirror["note"] = "cited by that rule's sentence"
            put(e["id"], rid, mirror)

    # semantic adjacency, generated mechanically from the labelling
    ids_sorted = sorted(rules)
    shares_pairs = 0
    for i, a in enumerate(ids_sorted):
        da = dim_of[a]
        if not da:
            continue
        for b in ids_sorted[i + 1 :]:
            shared = da & dim_of[b]
            if not shared:
                continue
            shares_pairs += 1
            via = sorted(shared)
            for src, dst in ((a, b), (b, a)):
                put(
                    src,
                    dst,
                    {
                        "id": dst,
                        "relation": "shares_dimension",
                        "subtype": None,
                        "direction": "none",
                        "source": "semantic",
                        "via": via,
                        "evidence": None,
                        "note": None,
                    },
                )

    # thematic structure, from pass B
    thematic_raw = 0
    for path in sorted((spec_dir / FRAG_DIMENSION).glob("*.json")):
        payload = load_json(path)
        for e in payload.get("edges", []):
            thematic_raw += 1
            a, b = e.get("a"), e.get("b")
            if a not in rules or b not in rules or a == b:
                reject("passB:unknown_or_self_id")
                continue
            if e.get("relation") != "thematic" or e.get("subtype") not in THEMATIC_SUBTYPES:
                reject("passB:bad_relation_or_subtype")
                continue
            ev = e.get("evidence") or {}
            if not valid_where(ev.get("where")):
                reject("passB:bad_anchor")
                continue
            if not grounded(ev.get("quote")):
                reject("passB:ungrounded_quote")
                continue
            sub = e["subtype"]
            direction = (
                e.get("direction") if e.get("direction") in {"out", "in", "none"} else "none"
            )
            if sub == "reinforces":
                direction = "none"
            entry = {
                "id": b,
                "relation": "thematic",
                "subtype": sub,
                "direction": direction,
                "source": "semantic",
                "evidence": {"where": ev["where"], "quote": ev["quote"]},
                "note": (e.get("note") or None),
            }
            put(a, b, entry)
            mirror = dict(entry)
            mirror["id"] = a
            mirror["direction"] = {"out": "in", "in": "out", "none": "none"}[direction]
            put(b, a, mirror)

    # --- groups ------------------------------------------------------------
    title_of = {d["key"]: d["title"] for d in registry}
    groups: list[dict] = []
    for d in registry:
        key = d["key"]
        members = sorted(rid for rid in rules if key in dim_of[rid])
        if not members:
            continue
        groups.append(
            {
                "gid": f"dim:{key}",
                "family": "dimension",
                "tier": "primary",
                "members": members,
                "rationale": f"behavioral dimension '{key}' ({title_of[key]})",
            }
        )
    by_path: dict[str, list[str]] = {}
    for r in rules_list:
        by_path.setdefault("/".join(r["sections"]), []).append(r["id"])
    for path_key in sorted(by_path):
        members = sorted(by_path[path_key])
        auths = sorted({rules[m]["authority"] for m in members if rules[m].get("authority")})
        groups.append(
            {
                "gid": f"sec:{path_key}",
                "family": "section",
                "tier": "secondary",
                "members": members,
                "rationale": (
                    f"innermost section #{path_key.rsplit('/', 1)[-1]}"
                    f" (authority={', '.join(auths)})"
                ),
            }
        )
    groups_of: dict[str, list[str]] = {rid: [] for rid in rules}
    for g in groups:
        for m in g["members"]:
            groups_of[m].append(g["gid"])

    # --- emit --------------------------------------------------------------
    out_rules = []
    for rid in sorted(rules):
        rec = dict(rules[rid])
        ctx = graph[rid]["context"]
        en = enrich.get(rid, {})
        neighbor = [{k: v for k, v in e.items() if k != "_k"} for e in edges[rid].values()]
        neighbor.sort(
            key=lambda e: (e["relation"], e["id"], e.get("subtype") or "", str(e.get("via") or ""))
        )
        rec["dimensions"] = en.get("dimensions") or []
        rec["groups"] = sorted(groups_of[rid])
        rec["neighbor"] = neighbor
        rec["related_context"] = {
            "sentence": ctx["sentence"],
            "stem": {"where": ctx["section_anchor"], "quote": ctx["stem"]} if ctx["stem"] else None,
            "framing": {"where": ctx["section_anchor"], "quote": ctx["framing"]}
            if ctx["framing"]
            else None,
            "ancestor_guards": ctx["ancestor_guards"],
            "definitions": en.get("definitions") or [],
            "meta_resolution": en.get("meta_resolution") or [],
            "exceptions": en.get("exceptions") or [],
            "facets": en.get("facets")
            or {f: ("unconditional_or_unspecified" if f != "state" else None) for f in FACETS},
            "facet_specifics": en.get("facet_specifics") or {},
            "facet_evidence": en.get("facet_evidence") or [],
            "examples": [
                {
                    "id": ex["id"],
                    "housed_in": ctx["section_anchor"],
                    "origin": "inventory"
                    if ex["id"] in (rules[rid].get("examples") or [])
                    else "same_section",
                    "title": ex.get("title"),
                    "verdict_notes": [
                        (
                            f"{v['verdict']}"
                            + (f"[#{v['cause_anchor']}]" if v.get("cause_anchor") else "")
                            + (f": {v['note']}" if v.get("note") else "")
                        )
                        for v in ex.get("verdicts", [])
                    ],
                }
                for ex in ctx["section_examples"]
            ]
            + [
                {
                    "id": ex["id"],
                    "housed_in": ex.get("housed_in"),
                    "origin": "external",
                    "title": ex.get("why"),
                    "verdict_notes": ex.get("verdict_notes") or [],
                }
                for ex in (en.get("external_examples") or [])
            ],
            "commentary": [
                {"where": c["where"], "quote": c["quote"], "normative": False}
                for c in ctx["commentary"]
            ],
            "section_references": ctx["section_references"],
            "authority_provenance": ctx["authority_provenance"],
            "coverage_notes": en.get("coverage_notes"),
        }
        out_rules.append(rec)

    out = {
        "spec": spec_dir.name,
        "source": RESOLVED,
        "config": {"max_quote_words": max_quote_words},
        "rules": out_rules,
        "groups": groups,
    }
    out_path = spec_dir / "grouped_rules.json"
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False))

    # --- verification (in-memory) ------------------------------------------
    rel_counts: dict[str, int] = {}
    src_counts: dict[str, int] = {}
    for rid in edges:
        for e in edges[rid].values():
            rel_counts[e["relation"]] = rel_counts.get(e["relation"], 0) + 1
            src_counts[e["source"]] = src_counts.get(e["source"], 0) + 1

    v: dict[str, str] = {}
    gid_set = {g["gid"] for g in groups}
    bad_ids = sum(1 for rid in edges for e in edges[rid].values() if e["id"] not in rules)
    bad_gids = sum(1 for rid in groups_of for g in groups_of[rid] if g not in gid_set)
    v["V1 identifier closure"] = (
        "PASS" if not bad_ids and not bad_gids else f"FAIL ({bad_ids + bad_gids})"
    )

    ungrounded = sum(
        1
        for rid in edges
        for e in edges[rid].values()
        if e["relation"] == "thematic" and not grounded((e["evidence"] or {}).get("quote"))
    )
    v["V2 quotation grounding"] = "PASS" if not ungrounded else f"FAIL ({ungrounded})"

    inv = {"out": "in", "in": "out", "none": "none"}
    asym = 0
    for rid in edges:
        for key, e in edges[rid].items():
            back = edges[e["id"]].get((rid, e["relation"], e.get("subtype"), e.get("_k")))
            if (
                back is None
                or back["direction"] != inv[e["direction"]]
                or back["source"] != e["source"]
                or back.get("via") != e.get("via")
            ):
                asym += 1
    v["V3 symmetry"] = "PASS" if asym == 0 else f"FAIL ({asym})"

    dim_members = {g["gid"][4:]: set(g["members"]) for g in groups if g["family"] == "dimension"}
    sem_bad = 0
    for i, a in enumerate(ids_sorted):
        for b in ids_sorted[i + 1 :]:
            shared = dim_of[a] & dim_of[b]
            edge = next(
                (
                    e
                    for e in edges[a].values()
                    if e["id"] == b and e["relation"] == "shares_dimension"
                ),
                None,
            )
            if shared:
                if edge is None or edge.get("via") != sorted(shared):
                    sem_bad += 1
                elif any(
                    a not in dim_members.get(k, set()) or b not in dim_members.get(k, set())
                    for k in shared
                ):
                    sem_bad += 1
            elif edge is not None:
                sem_bad += 1
    v["V4 semantic completeness"] = "PASS" if sem_bad == 0 else f"FAIL ({sem_bad})"

    sec_groups = {g["gid"][4:]: set(g["members"]) for g in groups if g["family"] == "section"}
    struct_bad = 0
    for path_key, members in by_path.items():
        if sec_groups.get(path_key) != set(members):
            struct_bad += 1
    for rid in edges:
        for e in edges[rid].values():
            if e["relation"] == "same_section":
                pk = "/".join(rules[rid]["sections"])
                if e["id"] not in sec_groups.get(pk, set()):
                    struct_bad += 1
    v["V5 structural completeness"] = "PASS" if struct_bad == 0 else f"FAIL ({struct_bad})"

    no_dim = [rid for rid in rules if not dim_of[rid]]
    missing_enrich = sorted(set(rules) - set(enrich))
    tier_bad = 0
    for rid in rules:
        fams = {g.split(":", 1)[0] for g in groups_of[rid]}
        if "dim" not in fams or "sec" not in fams:
            tier_bad += 1
    v["V6 rule coverage"] = (
        "PASS"
        if not no_dim and not missing_enrich and tier_bad == 0
        else (
            f"FAIL (no_dimension={len(no_dim)}, unenriched={len(missing_enrich)}, "
            f"tier_gaps={tier_bad})"
        )
    )

    out_of_dim = sorted(
        {
            tuple(sorted((rid, e["id"])))
            for rid in edges
            for e in edges[rid].values()
            if e["relation"] == "thematic" and not (dim_of[rid] & dim_of[e["id"]])
        }
    )
    no_thematic = sorted(
        rid for rid in rules if not any(e["relation"] == "thematic" for e in edges[rid].values())
    )

    dim_sizes = sorted(
        (len(g["members"]) for g in groups if g["family"] == "dimension"), reverse=True
    )
    sec_sizes = sorted(
        (len(g["members"]) for g in groups if g["family"] == "section"), reverse=True
    )

    print(f"OK {spec_dir.name}: {len(rules)} rules -> {out_path}")
    print(f"  pass-A fragments : {len(frag_a)} file(s), {len(enrich)} enriched record(s)")
    print(f"  edges by relation: {dict(sorted(rel_counts.items()))}")
    print(f"  edges by source  : {dict(sorted(src_counts.items()))}")
    print(f"  shares_dimension : {shares_pairs} pairs; thematic proposed: {thematic_raw}")
    print(f"  rejected         : {dict(sorted(rejects.items())) if rejects else 'none'}")
    print(
        f"  groups[dimension/primary] : {len(dim_sizes):3d}  "
        f"sizes max={dim_sizes[0]} min={dim_sizes[-1]}"
    )
    print(
        f"  groups[section/secondary] : {len(sec_sizes):3d}  "
        f"sizes max={sec_sizes[0]} min={sec_sizes[-1]}"
    )
    print(f"  out-of-dimension thematic pairs ({len(out_of_dim)}): {out_of_dim[:8]}")
    print(f"  rules with no thematic edge ({len(no_thematic)}): {', '.join(no_thematic[:16])}")
    print("  verification:")
    for k in sorted(v):
        print(f"    {k:28s} {v[k]}")
    return 0 if all(x == "PASS" for x in v.values()) else 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Merge stage-2 fragments into grouped_rules.json."
    )
    ap.add_argument("spec_dir", type=Path)
    args = ap.parse_args()
    spec_dir = args.spec_dir.resolve()
    if not spec_dir.is_dir():
        sys.exit(f"not a directory: {spec_dir}")
    return build(spec_dir)


if __name__ == "__main__":
    sys.exit(main())
