#!/usr/bin/env python3
"""Independent verifier for the two-level dimension taxonomy (R1-R8).

Evaluates the registry verification conditions of the group-rules
skill against the committed artifacts, sharing no code with any builder:

  R1  contract shape (root cardinality band, slugs, required fields,
      parent references, depth at most two)
  R2  textual traceability (seed anchors exist; roots span >= 2 chapters;
      no child merely restates a section group)
  R3  distinguishability over the leaf vocabulary (no two leaves share one
      extension; strict nestings are admissible and reported)
  R4  coverage and non-degeneracy (every rule labelled; no leaf below the
      membership floor)
  R5  held-out structural validation (citation-graph enrichment with a
      label-permutation test, computed at leaf granularity)
  R6  pilot reliability (Cohen's kappa between independent labelers)
  R7  granularity (no leaf above tau_max except those recorded as
      retained whole)
  R8  refinement validity (subsumption, exhaustiveness, sibling
      separation, per-child reliability; coarse groups equal descendant
      unions)

A flat registry -- every entry a childless root -- is the degenerate case
and is checked as such: R8 reports SKIP and R7 flags any oversized axis.
Exits non-zero on any FAIL.

Usage: check_taxonomy.py specs/<X> [--min-members 2] [--tau-max 30]
       [--permutations 1000] [--p-max 0.01] [--kappa-min 0.6] [--seed 0]
"""

from __future__ import annotations

import argparse
import itertools
import json
import random
import re
from pathlib import Path

SLUG_RE = re.compile(r"^[a-z][a-z0-9_]*$")
HEADING_RE = re.compile(r"^(#{1,6})\s+.*?\{([^}]*)\}\s*$", re.MULTILINE)
ANCHOR_RE = re.compile(r"(?:^|\s)#([A-Za-z0-9_-]+)(?=\s|$)")

FAILURES: list[str] = []


def report(cond: str, ok: bool | None, detail: str) -> None:
    verdict = "PASS" if ok else ("FAIL" if ok is False else "SKIP")
    print(f"{cond}: {verdict} - {detail}")
    if ok is False:
        FAILURES.append(cond)


def heading_index(doc: str) -> tuple[dict[str, str], set[str]]:
    """Map each section anchor to its top-level chapter anchor."""
    headings = []
    for m in HEADING_RE.finditer(doc):
        a = ANCHOR_RE.search(m.group(2))
        if a:
            headings.append((len(m.group(1)), a.group(1)))
    if not headings:
        return {}, set()
    top = min(level for level, _ in headings)
    chapter_of: dict[str, str] = {}
    current = None
    for level, anchor in headings:
        if level == top:
            current = anchor
        chapter_of[anchor] = current if current is not None else anchor
    return chapter_of, {a for _, a in headings}


def leaves_of(dims: list[dict]) -> list[str]:
    parents = {d["parent"] for d in dims if d.get("parent")}
    return [d["key"] for d in dims if d["key"] not in parents]


def check_r1(dims: list[dict], band: tuple[int, int]) -> None:
    problems = []
    keys = [d.get("key", "") for d in dims]
    if len(set(keys)) != len(keys):
        problems.append("duplicate keys")
    roots = [d for d in dims if not d.get("parent")]
    if not band[0] <= len(roots) <= band[1]:
        problems.append(f"root cardinality {len(roots)} outside {list(band)}")
    keyset = set(keys)
    for d in dims:
        k = d.get("key", "")
        if not SLUG_RE.match(k):
            problems.append(f"non-slug key {k!r}")
        for field in ("title", "definition", "seed_anchors"):
            if not d.get(field):
                problems.append(f"{k}: empty {field}")
        if "counter_poles" not in d:
            problems.append(f"{k}: missing counter_poles")
        p = d.get("parent")
        if p is not None:
            if p not in keyset:
                problems.append(f"{k}: unknown parent {p!r}")
            else:
                grandparent = next(x for x in dims if x["key"] == p).get("parent")
                if grandparent:
                    problems.append(f"{k}: depth exceeds two (parent {p} has parent)")
    defs = [d.get("definition", "") for d in dims]
    if len(set(defs)) != len(defs):
        problems.append("duplicate definitions")
    detail = "; ".join(problems) or (
        f"{len(dims)} axes = {len(roots)} roots + {len(dims) - len(roots)} children; "
        f"{len(leaves_of(dims))} leaves"
    )
    report("R1 contract shape", not problems, detail)


def check_r2(
    dims: list[dict],
    doc: str,
    sec_groups: list[set] | None = None,
    labels: dict[str, set] | None = None,
) -> None:
    """Roots must reach across chapters; children must not restate a section group.

    A root axis exists to recover relations the section tree cannot express, so
    its seed anchors must span at least two top-level chapters. A child inherits
    that reach by subsumption (G7) and may legitimately concentrate in one
    section -- a sub-act can be localized -- so the operative test for a child is
    the purpose behind G3 rather than its root-level proxy: its membership must
    not coincide with a section group, which would duplicate the secondary tier.
    """
    chapter_of, anchors = heading_index(doc)
    problems = []
    for d in dims:
        spans_ch = set()
        for anchor in d.get("seed_anchors", []):
            bare = anchor.lstrip("#")
            if bare not in anchors:
                problems.append(f"{d['key']}: unknown seed anchor {anchor}")
            else:
                spans_ch.add(chapter_of[bare])
        if not d.get("parent") and len(spans_ch) < 2:
            problems.append(f"{d['key']}: root spans {len(spans_ch)} chapter(s)")
    restated = []
    if sec_groups is not None and labels is not None:
        for d in dims:
            if not d.get("parent"):
                continue
            mem = {r for r, s in labels.items() if d["key"] in s}
            if mem and any(mem == m for m in sec_groups):
                restated.append(d["key"])
                problems.append(f"{d['key']}: child coextensive with a section group")
    detail = "; ".join(problems) or (
        "all seed anchors resolve; roots span >= 2 chapters"
        + ("; no child restates a section group" if sec_groups is not None else "")
    )
    report("R2 textual traceability", not problems, detail)


def check_r3(leaves: list[str], labels: dict[str, set]) -> None:
    """Two axes fail only when neither separates from the other.

    A pair with no witness in *either* direction has one extension under two
    names -- a duplicated construct, which fails. A pair witnessed in exactly
    one direction is a strict nesting: one axis's members are a proper subset
    of the other's. Nesting is admissible (the tests differ; the extensions
    happen to nest on this corpus) but is reported, since a persistent nesting
    across corpora would argue for consolidation.
    """
    ext = {k: {r for r, s in labels.items() if k in s} for k in leaves}
    duplicates, nested = [], []
    for a, b in itertools.combinations(leaves, 2):
        fwd, rev = ext[a] - ext[b], ext[b] - ext[a]
        if not fwd and not rev:
            duplicates.append(f"{a} == {b}")
        elif not fwd:
            nested.append(f"{a} subset of {b}")
        elif not rev:
            nested.append(f"{b} subset of {a}")
    detail = (
        f"{len(leaves) * (len(leaves) - 1) // 2} unordered leaf pairs; "
        f"{len(duplicates)} duplicated extension(s)"
        + (f": {duplicates[:4]}" if duplicates else "")
        + (f"; {len(nested)} strict nesting(s) reported: {nested[:4]}" if nested else "")
    )
    report("R3 distinguishability witnesses", not duplicates, detail)


def check_r4(leaves: list[str], labels: dict[str, set], rule_ids: list[str], floor: int) -> None:
    residue = [r for r in rule_ids if not labels.get(r)]
    counts = {k: sum(1 for s in labels.values() if k in s) for k in leaves}
    thin = [f"{k} ({v})" for k, v in counts.items() if v < floor]
    problems = []
    if residue:
        problems.append(f"{len(residue)} unlabelled rules: {residue[:5]}")
    if thin:
        problems.append("below floor: " + ", ".join(thin))
    detail = "; ".join(problems) or (
        f"all {len(rule_ids)} rules labelled; leaf membership "
        f"{min(counts.values())}-{max(counts.values())}"
    )
    report("R4 coverage and non-degeneracy", not problems, detail)


def check_r5(
    labels: dict[str, set], xref_pairs: set, permutations: int, p_max: float, seed: int
) -> None:
    ids = sorted(labels)
    if not xref_pairs:
        report("R5 held-out enrichment", None, "no cross-reference pairs to test")
        return
    hits = sum(1 for a, b in itertools.combinations(ids, 2) if labels[a] & labels[b])
    baseline = hits / (len(ids) * (len(ids) - 1) / 2)
    observed = sum(1 for a, b in xref_pairs if labels[a] & labels[b]) / len(xref_pairs)
    ratio = observed / baseline if baseline else float("inf")
    rng = random.Random(seed)
    sets = [labels[i] for i in ids]
    at_least = 0
    for _ in range(permutations):
        rng.shuffle(sets)
        perm = dict(zip(ids, sets))
        if sum(1 for a, b in xref_pairs if perm[a] & perm[b]) / len(xref_pairs) >= observed:
            at_least += 1
    p_value = (at_least + 1) / (permutations + 1)
    report(
        "R5 held-out enrichment",
        ratio > 1 and p_value <= p_max,
        f"P(share|xref)={observed:.3f} vs baseline {baseline:.3f}, ratio {ratio:.2f}, "
        f"p={p_value:.4g} ({permutations} permutations, {len(xref_pairs)} xref pairs)",
    )


def kappa(a: list[bool], b: list[bool]) -> float:
    n = len(a)
    po = sum(1 for x, y in zip(a, b) if x == y) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    if pe == 1:
        return 1.0 if po == 1 else 0.0
    return (po - pe) / (1 - pe)


def check_r6(dims: list[dict], prov: dict, pilot_dir: Path, kappa_min: float) -> None:
    recorded: dict[str, float] = {}
    pilot = (prov.get("pilot") or {}) if prov else {}
    for src in ("round1_kappa", "appended_axes_kappa"):
        recorded.update(pilot.get(src) or {})
    if isinstance(pilot.get("round2"), dict) and pilot["round2"].get("kappa") is not None:
        rev = (prov.get("pilot", {}).get("revision") or {}).get("key")
        if rev:
            recorded[rev] = pilot["round2"]["kappa"]
    for ref in prov.get("refinements") or []:
        recorded.update(ref.get("kappa") or {})
    if pilot_dir.is_dir():
        for d in dims:
            pair = [pilot_dir / f"{d['key']}_{s}.json" for s in ("a", "b")]
            if all(p.is_file() for p in pair):
                recs = [
                    {r["id"]: bool(r["applies"]) for r in json.loads(p.read_text())["records"]}
                    for p in pair
                ]
                common = sorted(set(recs[0]) & set(recs[1]))
                if common:
                    recorded[d["key"]] = kappa(
                        [recs[0][i] for i in common], [recs[1][i] for i in common]
                    )
    if not recorded:
        report("R6 pilot reliability", None, "no reliability results recorded")
        return
    low = [f"{k} ({v:.2f})" for k, v in recorded.items() if v < kappa_min]
    missing = [d["key"] for d in dims if d["key"] not in recorded]
    problems = []
    if low:
        problems.append("below threshold: " + ", ".join(low))
    if missing:
        problems.append(f"{len(missing)} axes without a result: {missing[:5]}")
    report(
        "R6 pilot reliability",
        not problems,
        "; ".join(problems) or f"{len(recorded)} axes at kappa >= {kappa_min}",
    )


def check_r7(leaves: list[str], labels: dict[str, set], tau: int, prov: dict) -> None:
    counts = {k: sum(1 for s in labels.values() if k in s) for k in leaves}
    retained = {r["parent"] for r in (prov.get("refinements") or []) if r.get("retained_whole")}
    over = {k: v for k, v in counts.items() if v > tau}
    undocumented = {k: v for k, v in over.items() if k not in retained}
    documented = sorted(set(over) & retained)
    largest = max(counts.values()) if counts else 0
    detail = (
        f"{len(over)} of {len(leaves)} leaf group(s) above tau_max={tau} (largest {largest})"
        + (f"; documented as retained whole: {documented}" if documented else "")
        + (
            f"; undocumented: {sorted(undocumented.items(), key=lambda x: -x[1])}"
            if undocumented
            else ""
        )
    )
    report("R7 granularity", not undocumented, detail)


def check_r8(dims: list[dict], labels: dict[str, set], prov: dict, kappa_min: float) -> None:
    children_of: dict[str, list[str]] = {}
    for d in dims:
        if d.get("parent"):
            children_of.setdefault(d["parent"], []).append(d["key"])
    if not children_of:
        report("R8 refinement validity", None, "flat registry; no refinements to check")
        return
    parent_members = {
        r["parent"]: set(r.get("parent_members") or [])
        for r in (prov.get("refinements") or [])
        if r.get("parent_members")
    }
    problems = []
    for parent, kids in sorted(children_of.items()):
        union: set[str] = set()
        for k in kids:
            union |= {r for r, s in labels.items() if k in s}
        pm = parent_members.get(parent)
        if pm is None:
            problems.append(f"{parent}: no recorded membership to check subsumption against")
        else:
            if union - pm:
                problems.append(f"{parent}: {len(union - pm)} child rule(s) outside the parent")
            if pm - union:
                problems.append(f"{parent}: {len(pm - union)} parent rule(s) in no child")
        for a, b in itertools.permutations(kids, 2):
            if not any(a in s and b not in s for s in labels.values()):
                problems.append(f"{parent}: {a} not separated from {b}")
    kap = {}
    for ref in prov.get("refinements") or []:
        kap.update(ref.get("kappa") or {})
    low = [f"{k} ({v:.2f})" for k, v in kap.items() if v < kappa_min]
    if low:
        problems.append("child reliability below threshold: " + ", ".join(low))
    detail = "; ".join(problems) or (
        f"{len(children_of)} refinement(s): subsumption, exhaustiveness, separation and "
        f"reliability hold for all {sum(len(v) for v in children_of.values())} children"
    )
    report("R8 refinement validity", not problems, detail)


def main() -> int:
    ap = argparse.ArgumentParser(description="Verify the dimension taxonomy (R1-R8).")
    ap.add_argument("spec_dir", type=Path)
    ap.add_argument("--min-members", type=int, default=2)
    ap.add_argument("--tau-max", type=int, default=30)
    ap.add_argument("--permutations", type=int, default=1000)
    ap.add_argument("--p-max", type=float, default=0.01)
    ap.add_argument("--kappa-min", type=float, default=0.6)
    ap.add_argument("--band", type=int, nargs=2, default=(12, 20))
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    dims = json.loads((args.spec_dir / "dimensions.json").read_text(encoding="utf-8"))["dimensions"]
    doc = (args.spec_dir / "anonymized_annotated_resolved.md").read_text(encoding="utf-8")
    rule_ids = [
        r["id"]
        for r in json.loads((args.spec_dir / "rules.json").read_text(encoding="utf-8"))["rules"]
    ]
    prov_path = args.spec_dir / "dimensions_derivation.json"
    prov = json.loads(prov_path.read_text(encoding="utf-8")) if prov_path.is_file() else {}
    print(f"taxonomy status: {'protocol' if prov else 'legacy (no provenance record)'}")

    leaves = leaves_of(dims)
    check_r1(dims, tuple(args.band))

    grouped = args.spec_dir / "grouped_rules.json"
    if grouped.is_file():
        g = json.loads(grouped.read_text(encoding="utf-8"))
        labels = {r["id"]: set(r["dimensions"]) for r in g["rules"]}
        sec_groups = [set(x["members"]) for x in g["groups"] if x.get("family") == "section"]
        check_r2(dims, doc, sec_groups, labels)
        xref = {
            tuple(sorted((r["id"], e["id"])))
            for r in g["rules"]
            for e in r["neighbor"]
            if e["relation"] == "cross_reference"
        }
        check_r3(leaves, labels)
        check_r4(leaves, labels, rule_ids, args.min_members)
        check_r5(labels, xref, args.permutations, args.p_max, args.seed)
        check_r6(dims, prov, args.spec_dir / ".registry_fragments" / "pilot", args.kappa_min)
        check_r7(leaves, labels, args.tau_max, prov)
        check_r8(dims, labels, prov, args.kappa_min)
    else:
        check_r2(dims, doc)
        for cond in (
            "R3 distinguishability witnesses",
            "R4 coverage and non-degeneracy",
            "R5 held-out enrichment",
            "R6 pilot reliability",
            "R7 granularity",
            "R8 refinement validity",
        ):
            report(cond, None, "grouped_rules.json absent")

    if FAILURES:
        print(f"FAILED: {', '.join(FAILURES)}")
        return 1
    print("OK: taxonomy conditions hold (SKIP lines list what was not evaluated)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
