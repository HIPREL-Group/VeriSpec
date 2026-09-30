#!/usr/bin/env python3
"""Independent post-hoc verification of specs/<X>/grouped_rules.json.

``build_groups.py`` validates the structures it holds in memory. This checker
validates the artifact that was actually written, sharing no code with the
builder, so that a defect in projection, sorting, or serialization cannot pass
unnoticed. It re-derives every invariant from the emitted file plus the
specification, the rule inventory, and the dimension registry.

Checks
  C1  every neighbor id, dimension key, group id and group member resolves
  C2  edge symmetry: a -> b implies b -> a with inverted direction and
      identical relation, subtype, source and via
  C3  every quotation (thematic evidence and related_context material) is a
      verbatim substring of the specification
  C4  every `where` anchor / marker / example tag exists in the document
  C5  semantic completeness: pairs sharing dimensions carry exactly one
      shares_dimension edge per endpoint whose via equals the intersection,
      and are co-resident in each shared dimension's group; no
      shares_dimension edge exists between rules sharing nothing
  C6  structural completeness: one section group per innermost section,
      containing exactly its rules; same_section edges co-resident there
  C7  every rule of rules.json appears exactly once, with >=1 dimension,
      non-empty related_context, and >=1 group of each tier
  C8  field-shape conformance: v2 relation vocabulary (no opposition
      relation), subtype/direction/evidence constraints, tier and gid forms
  C9  the rules[].groups inverse index agrees exactly with groups[].members

Usage: check_grouped.py specs/<X>
Exit status is non-zero if any check fails.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

RELATIONS = {
    "same_sentence",
    "same_section",
    "shares_example",
    "cross_reference",
    "shares_dimension",
    "thematic",
}
XREF_SUB = {"defers_to", "carves_exception_from", "tightens", "style_modulates", "background"}
THEM_SUB = {"reinforces", "conditions", "specializes"}
INVERSE = {"out": "in", "in": "out", "none": "none"}
CTX_KEYS = {
    "sentence",
    "stem",
    "framing",
    "ancestor_guards",
    "definitions",
    "meta_resolution",
    "exceptions",
    "facets",
    "facet_specifics",
    "facet_evidence",
    "examples",
    "commentary",
    "section_references",
    "authority_provenance",
    "coverage_notes",
}


def norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    for a, b in (("’", "'"), ("‘", "'"), ("“", '"'), ("”", '"'), ("—", "-"), ("–", "-")):
        text = text.replace(a, b)
    text = re.sub(r"\[\^\w+\]", "", text)
    text = re.sub(r"-{2,}", "-", text)
    return re.sub(r"\s+", " ", text).strip()


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit("usage: check_grouped.py specs/<X>")
    spec = Path(sys.argv[1]).resolve()
    art = json.loads((spec / "grouped_rules.json").read_text(encoding="utf-8"))
    inv = {r["id"] for r in json.loads((spec / "rules.json").read_text(encoding="utf-8"))["rules"]}
    dims = {
        d["key"]
        for d in json.loads((spec / "dimensions.json").read_text(encoding="utf-8"))["dimensions"]
    }
    doc = (spec / "anonymized_annotated_resolved.md").read_text(encoding="utf-8")
    doc_n = norm(doc)
    anchors = set(re.findall(r"^#{1,6}\s+.*?\{#([\w-]+)", doc, re.M))
    egs = set(re.findall(r"\[\^(eg\d{3})\]", doc))

    rules = art["rules"]
    groups = art["groups"]
    by = {r["id"]: r for r in rules}
    dim_of = {r["id"]: set(r.get("dimensions") or []) for r in rules}
    fail: dict[str, list[str]] = defaultdict(list)

    # ---- C1 identifier closure
    gid_set = {g["gid"] for g in groups}
    for r in rules:
        if r["id"] not in inv:
            fail["C1"].append(f"unknown rule {r['id']}")
        for k in r["dimensions"]:
            if k not in dims:
                fail["C1"].append(f"{r['id']}: unknown dimension {k}")
        for e in r["neighbor"]:
            if e["id"] not in by:
                fail["C1"].append(f"{r['id']}: neighbor {e['id']} not in artifact")
        for g in r.get("groups") or []:
            if g not in gid_set:
                fail["C1"].append(f"{r['id']}: unknown group {g}")
    for g in groups:
        for m in g["members"]:
            if m not in by:
                fail["C1"].append(f"group {g['gid']}: unknown member {m}")

    # ---- C2 symmetry
    def ekey(e):
        return (e["id"], e["relation"], e.get("subtype"), json.dumps(e.get("via")))

    index: dict[str, dict[tuple, dict]] = {
        r["id"]: {ekey(e): e for e in r["neighbor"]} for r in rules
    }
    asym = 0
    for a, aedges in index.items():
        for (b, rel, sub, via), e in aedges.items():
            back = index.get(b, {}).get((a, rel, sub, via))
            if back is None:
                fail["C2"].append(f"{a} -> {b} ({rel}) has no return edge")
                asym += 1
            elif back["direction"] != INVERSE[e["direction"]] or back["source"] != e["source"]:
                fail["C2"].append(f"{a}~{b} ({rel}): attribute mismatch")
                asym += 1

    # ---- C3 / C4 grounding
    def where_ok(w) -> bool:
        if not isinstance(w, str) or not w:
            return False
        if w.startswith("#"):
            return w[1:] in anchors
        m = re.fullmatch(r"\[\^(\w+)\]", w)
        return bool(m and (m.group(1) in inv or m.group(1) in egs))

    for r in rules:
        for e in r["neighbor"]:
            if e["relation"] != "thematic":
                continue
            ev = e.get("evidence") or {}
            q = (ev.get("quote") or "").replace("[...]", " ")
            if not q or norm(q) not in doc_n:
                fail["C3"].append(f"{r['id']}~{e['id']}: quote not verbatim")
            if not where_ok(ev.get("where")):
                fail["C4"].append(f"{r['id']}~{e['id']}: bad where {ev.get('where')!r}")
        c = r["related_context"]
        for fld in (
            "ancestor_guards",
            "definitions",
            "meta_resolution",
            "exceptions",
            "facet_evidence",
        ):
            for it in c.get(fld) or []:
                if not where_ok(it.get("where")):
                    fail["C4"].append(f"{r['id']}.{fld}: bad where {it.get('where')!r}")
                q = (it.get("quote") or "").replace("[...]", " ")
                if q and norm(q) not in doc_n:
                    fail["C3"].append(f"{r['id']}.{fld}: quote not verbatim")
        for ex in c.get("examples") or []:
            if ex.get("id") not in egs:
                fail["C4"].append(f"{r['id']}: unknown example {ex.get('id')}")

    # ---- C5 semantic completeness
    dim_group = {}
    for g in groups:
        if g["family"] == "dimension":
            dim_group[g["gid"][4:]] = set(g["members"])
    ids_sorted = sorted(by)
    sd_index: dict[tuple[str, str], dict] = {}
    for r in rules:
        for e in r["neighbor"]:
            if e["relation"] == "shares_dimension":
                sd_index[(r["id"], e["id"])] = e
    for i, a in enumerate(ids_sorted):
        for b in ids_sorted[i + 1 :]:
            shared = sorted(dim_of[a] & dim_of[b])
            e = sd_index.get((a, b))
            if shared:
                if e is None:
                    fail["C5"].append(f"{a}~{b}: shared {shared} but no shares_dimension edge")
                elif sorted(e.get("via") or []) != shared:
                    fail["C5"].append(f"{a}~{b}: via {e.get('via')} != intersection {shared}")
                else:
                    for k in shared:
                        if a not in dim_group.get(k, set()) or b not in dim_group.get(k, set()):
                            fail["C5"].append(f"{a}~{b}: not co-resident in dim:{k}")
            elif e is not None:
                fail["C5"].append(f"{a}~{b}: shares_dimension edge with empty intersection")

    # ---- C6 structural completeness
    sec_group = {g["gid"][4:]: set(g["members"]) for g in groups if g["family"] == "section"}
    by_path: dict[str, set] = defaultdict(set)
    for r in rules:
        by_path["/".join(r["sections"])].add(r["id"])
    if set(sec_group) != set(by_path):
        fail["C6"].append(
            f"section-group keys differ from section partition "
            f"(missing {sorted(set(by_path) - set(sec_group))[:3]}, "
            f"extra {sorted(set(sec_group) - set(by_path))[:3]})"
        )
    else:
        for pk, members in by_path.items():
            if sec_group[pk] != members:
                fail["C6"].append(f"sec:{pk}: member mismatch")
    for r in rules:
        pk = "/".join(r["sections"])
        for e in r["neighbor"]:
            if e["relation"] == "same_section" and e["id"] not in sec_group.get(pk, set()):
                fail["C6"].append(f"{r['id']}~{e['id']}: same_section not co-resident")

    # ---- C7 rule coverage
    ids = [r["id"] for r in rules]
    dup = [k for k, v in Counter(ids).items() if v > 1]
    if dup:
        fail["C7"].append(f"duplicate records: {dup}")
    if set(ids) != inv:
        fail["C7"].append(
            f"missing {sorted(inv - set(ids))[:5]} extra {sorted(set(ids) - inv)[:5]}"
        )
    for r in rules:
        if not r["dimensions"]:
            fail["C7"].append(f"{r['id']}: no dimension")
        fams = {g.split(":", 1)[0] for g in r.get("groups") or []}
        if "dim" not in fams or "sec" not in fams:
            fail["C7"].append(f"{r['id']}: missing a group tier ({sorted(fams)})")
        if not r.get("related_context"):
            fail["C7"].append(f"{r['id']}: empty related_context")

    # ---- C8 field shapes
    for g in groups:
        fam = g.get("family")
        if fam not in {"dimension", "section"}:
            fail["C8"].append(f"{g.get('gid')}: unknown family {fam}")
            continue
        want_tier = "primary" if fam == "dimension" else "secondary"
        if g.get("tier") != want_tier:
            fail["C8"].append(f"{g['gid']}: tier {g.get('tier')} != {want_tier}")
        want_prefix = "dim:" if fam == "dimension" else "sec:"
        if not g["gid"].startswith(want_prefix):
            fail["C8"].append(f"{g['gid']}: gid prefix does not match family")
    for r in rules:
        if set(r["related_context"]) != CTX_KEYS:
            fail["C8"].append(f"{r['id']}: related_context keys differ")
        for e in r["neighbor"]:
            rel = e["relation"]
            if rel not in RELATIONS:
                fail["C8"].append(f"{r['id']}: bad relation {rel}")
                continue
            if e["direction"] not in INVERSE:
                fail["C8"].append(f"{r['id']}: bad direction {e['direction']}")
            if e["source"] not in {"mechanical", "semantic"}:
                fail["C8"].append(f"{r['id']}: bad source {e['source']}")
            s = e.get("subtype")
            if rel == "cross_reference":
                if s is not None and s not in XREF_SUB:
                    fail["C8"].append(f"{r['id']}: bad xref subtype {s}")
            elif rel == "thematic":
                if s not in THEM_SUB:
                    fail["C8"].append(f"{r['id']}: bad thematic subtype {s}")
                if not (e.get("evidence") or {}).get("quote"):
                    fail["C8"].append(f"{r['id']}~{e['id']}: thematic edge without evidence")
            elif s is not None:
                fail["C8"].append(f"{r['id']}: subtype {s} invalid for {rel}")
            if rel == "shares_dimension":
                via = e.get("via")
                if not via or not isinstance(via, list):
                    fail["C8"].append(f"{r['id']}~{e['id']}: shares_dimension without via")
                elif not set(via) <= (dim_of[r["id"]] & dim_of.get(e["id"], set())):
                    fail["C8"].append(f"{r['id']}~{e['id']}: via not shared by both endpoints")
                if e.get("evidence") is not None:
                    fail["C8"].append(f"{r['id']}~{e['id']}: shares_dimension carries evidence")

    # ---- C9 inverse index agreement
    forward = {g["gid"]: set(g["members"]) for g in groups}
    for r in rules:
        declared = set(r.get("groups") or [])
        actual = {gid for gid, ms in forward.items() if r["id"] in ms}
        if declared != actual:
            fail["C9"].append(
                f"{r['id']}: missing {sorted(actual - declared)[:2]} "
                f"extra {sorted(declared - actual)[:2]}"
            )

    names = {
        "C1": "identifier closure",
        "C2": "edge symmetry",
        "C3": "quotation grounding",
        "C4": "anchor/tag existence",
        "C5": "semantic completeness",
        "C6": "structural completeness",
        "C7": "rule coverage",
        "C8": "field-shape conformance",
        "C9": "inverse index agreement",
    }
    total_edges = sum(len(r["neighbor"]) for r in rules)
    print(f"post-hoc verification of {spec.name}/grouped_rules.json")
    print(f"  {len(rules)} rules, {total_edges} directed edges, {len(groups)} groups")
    bad = 0
    for c in sorted(names):
        errs = fail.get(c, [])
        status = "PASS" if not errs else f"FAIL ({len(errs)})"
        print(f"  {c} {names[c]:26s} {status}")
        for e in errs[:3]:
            print(f"       {e}")
        bad += len(errs)
    print(f"  symmetry: {total_edges} edges checked, {asym} asymmetric")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
