#!/usr/bin/env python3
"""Partition each per-authority rule graph into balanced analysis units.

Reads ``specs/<X>/grouped_rules_by_authority/<authority>.json`` (which is left
untouched) and writes one of two variants:

  default   ``specs/<X>/grouped_rules_partitioned/<authority>.json`` — natural
            per-dimension components are kept whole however large; only units
            below the floor are merged (affinity merge, combined size capped).
  --even    ``specs/<X>/grouped_rules_partitioned_even/<authority>.json`` — in
            addition, components larger than the cap are subdivided by capped
            agglomeration on thematic and mechanical edges.

Stage 3 analyzes one unit at a time, so each authority's single dense
component must be decomposed into contexts small enough to hold. Two steps:

1. **Vertex splitting.** Every rule carrying two or more behavioral
   dimensions is replaced by one copy per dimension (copy id
   ``<rule>@<dimension>``). Each edge attaches to the copies of its context
   dimensions: the ``via`` keys for ``shares_dimension`` edges, the
   endpoints' shared labels otherwise. An edge whose endpoints share no
   dimension has no context; it is recorded as a *bridge* between units
   rather than allowed to merge them. Splitting only high-degree vertices
   was measured and rejected: connectivity is distributed over all
   multi-dimension rules, so partial splitting leaves one component.

2. **Balancing.** Components larger than ``--cap`` are subdivided by capped
   agglomeration on their thematic and mechanical edges, so sub-units grow
   along the argued structure; structural edges cut this way are counted.
   Units smaller than ``--floor`` are merged with their highest-affinity
   partner, affinity being twice the number of shared original rules plus
   the number of bridges between the units. A unit that finds no partner
   within the cap stands as it is.

The emitted file carries the copy nodes, the context-tagged edges, the
bridge list, the units (as ``components``, each with provenance tracing
every subdivision and merge), and a ``balance_stats`` block.

Usage: partition_authority_graphs.py specs/<X> [--cap 28] [--floor 12]
"""

from __future__ import annotations

import argparse
import collections
import itertools
import json
import statistics as st
from pathlib import Path

AUTHORITIES = ["root", "guideline", "user", "system", "developer"]


def build_edges(rules: list[dict], dims: dict[str, list[str]]) -> dict:
    """Undirected typed edges with a context-key list (None = bridge)."""
    edges: dict[tuple, tuple] = {}
    for r in rules:
        for e in r["neighbor"]:
            a, b = sorted((r["id"], e["id"]))
            key = (a, b, e["relation"], e.get("subtype"), json.dumps(e.get("via")))
            if key in edges:
                continue
            if e["relation"] == "shares_dimension":
                ctx = list(e["via"])
            else:
                shared = sorted(set(dims[a]) & set(dims[b]))
                ctx = shared if shared else None
            edges[key] = (a, b, e["relation"], e.get("subtype"), ctx)
    return edges


def components_of(nodes: set[str], adj: dict[str, set]) -> list[list[str]]:
    seen: set[str] = set()
    out = []
    for n in sorted(nodes):
        if n in seen:
            continue
        stack, comp = [n], []
        seen.add(n)
        while stack:
            x = stack.pop()
            comp.append(x)
            for y in adj[x]:
                if y not in seen:
                    seen.add(y)
                    stack.append(y)
        out.append(sorted(comp))
    out.sort(key=lambda c: (-len(c), c[0]))
    return out


def subdivide(members: list[str], them_adj, full_adj, cap: int) -> list[list[str]]:
    """Capped agglomeration on structural edges; absorb fragments (<4)."""
    part = {m: i for i, m in enumerate(members)}
    groups: dict[int, list[str]] = {i: [m] for i, m in enumerate(members)}

    def between(i: int, j: int) -> int:
        return sum(1 for x in groups[i] for y in them_adj[x] if part.get(y) == j)

    while True:
        best = None
        for i, j in itertools.combinations(sorted(groups), 2):
            if len(groups[i]) + len(groups[j]) > cap:
                continue
            w = between(i, j)
            if w == 0:
                continue
            key = (-w, len(groups[i]) + len(groups[j]), i, j)
            if best is None or key < best[0]:
                best = (key, i, j)
        if best is None:
            break
        _, i, j = best
        groups[i] += groups[j]
        del groups[j]
        for m in groups[i]:
            part[m] = i

    for i in [g for g in list(groups) if len(groups[g]) < 4]:
        if len(groups) == 1:
            break
        cand = [
            (
                sum(1 for x in groups[i] for y in full_adj[x] if part.get(y) == j),
                -len(groups[j]),
                j,
            )
            for j in groups
            if j != i and len(groups[j]) + len(groups[i]) <= cap
        ]
        if not cand:
            continue
        cand.sort(reverse=True)
        j = cand[0][2]
        groups[j] += groups[i]
        del groups[i]
        for m in groups[j]:
            part[m] = j
    return [sorted(groups[i]) for i in sorted(groups, key=lambda g: (-len(groups[g]), g))]


def partition(src: dict, cap: int, floor: int, even: bool) -> dict:
    rules = src["rules"]
    by = {r["id"]: r for r in rules}
    dims = {r["id"]: r["dimensions"] for r in rules}
    edges = build_edges(rules, dims)
    split = {v for v in by if len(dims[v]) > 1}

    def node(v: str, k: str) -> str:
        return f"{v}@{k}" if v in split else v

    nodes: set[str] = set()
    for v in by:
        nodes.update({f"{v}@{k}" for k in dims[v]} if v in split else {v})

    full_adj: dict[str, set] = collections.defaultdict(set)
    them_adj: dict[str, set] = collections.defaultdict(set)
    out_edges, bridges = [], []
    for a, b, rel, sub, ctx in edges.values():
        if ctx is None:
            bridges.append({"a": a, "b": b, "relation": rel, "subtype": sub})
            continue
        for k in ctx:
            na, nb = node(a, k), node(b, k)
            full_adj[na].add(nb)
            full_adj[nb].add(na)
            if rel != "shares_dimension":
                them_adj[na].add(nb)
                them_adj[nb].add(na)
            out_edges.append({"a": na, "b": nb, "relation": rel, "subtype": sub, "context": k})
    for n in nodes:
        full_adj[n]

    comps = components_of(nodes, full_adj)
    units: list[list] = []  # [label, members, provenance]
    for i, comp in enumerate(comps, 1):
        cid = f"comp:{i:02d}"
        if not even or len(comp) <= cap:
            units.append([cid, comp, f"component {cid} unchanged"])
        else:
            for k, part_members in enumerate(subdivide(comp, them_adj, full_adj, cap), 1):
                units.append([f"{cid}.{k}", part_members, f"subdivision {k} of {cid}"])

    prim = {v: (f"{v}@{dims[v][0]}" if v in split else v) for v in by}

    def unit_of(copy_id: str) -> list:
        return next(u for u in units if copy_id in u[1])

    def originals(u: list) -> set:
        return {m.split("@")[0] for m in u[1]}

    bridge_pairs: collections.Counter = collections.Counter()
    for brg in bridges:
        ua, ub = unit_of(prim[brg["a"]])[0], unit_of(prim[brg["b"]])[0]
        bridge_pairs[frozenset((ua, ub))] += 1

    while True:
        units.sort(key=lambda u: (len(u[1]), u[0]))
        target = next((u for u in units if len(u[1]) < floor), None)
        if target is None or len(units) == 1:
            break
        cand = []
        for v in units:
            if v is target or len(target[1]) + len(v[1]) > cap:
                continue
            aff = (
                2 * len(originals(target) & originals(v))
                + bridge_pairs[frozenset((target[0], v[0]))]
            )
            cand.append((aff, -len(v[1]), v[0], v))
        if not cand:
            break
        cand.sort(reverse=True)
        aff, _, _, v = cand[0]
        v[1] = sorted(v[1] + target[1])
        v[2] += f" + merged {target[0]} (affinity {aff})"
        units.remove(target)

    units.sort(key=lambda u: (-len(u[1]), u[0]))
    sizes = [len(u[1]) for u in units]
    cut = sum(1 for a in them_adj for b in them_adj[a] if a < b and unit_of(a)[0] != unit_of(b)[0])
    context_of = {n: (n.split("@")[1] if "@" in n else dims[n.split("@")[0]][0]) for n in nodes}
    return {
        "spec": src["spec"],
        "source": src["source"],
        "authority": src["authority"],
        "derivation": (
            (
                "vertex splitting of grouped_rules_by_authority/"
                f"{src['authority']}.json (every multi-dimension rule becomes one copy per "
                "dimension; edges attach to their context dimensions; context-free edges are "
                f"bridges), then balancing to units of at most {cap} copies (capped "
                "agglomeration on thematic and mechanical edges) with units smaller than "
                f"{floor} merged by affinity (2 x shared original rules + bridges)."
            )
            if even
            else (
                "vertex splitting of grouped_rules_by_authority/"
                f"{src['authority']}.json (every multi-dimension rule becomes one copy per "
                "dimension; edges attach to their context dimensions; context-free edges are "
                "bridges). Natural per-dimension components are kept whole however large; "
                f"only units smaller than {floor} are merged by affinity (2 x shared "
                f"original rules + bridges), with merged units capped at {cap} copies."
            )
        ),
        "config": (
            {"cap": cap, "floor": floor}
            if even
            else {"cap": cap, "floor": floor, "subdivide": False}
        ),
        "split_vertices": sorted(split),
        "nodes": [
            {
                "id": n,
                "rule": n.split("@")[0],
                "context": context_of[n],
                "section": by[n.split("@")[0]]["sections"][-1],
            }
            for n in sorted(nodes)
        ],
        "edges": sorted(out_edges, key=lambda e: (e["a"], e["b"], e["relation"], e["context"])),
        "bridges": sorted(bridges, key=lambda e: (e["a"], e["b"], e["relation"])),
        "components": [
            {
                "cid": f"unit:{i:02d}",
                "size": len(u[1]),
                "provenance": u[2],
                "dominant_dimension": collections.Counter(context_of[m] for m in u[1]).most_common(
                    1
                )[0][0],
                "members": u[1],
            }
            for i, u in enumerate(units, 1)
        ],
        "balance_stats": {
            "rules": len(by),
            "copies": len(nodes),
            "duplication": round(len(nodes) / len(by), 2),
            "units": len(units),
            "sizes": sizes,
            "min": min(sizes),
            "median": int(st.median(sizes)),
            "max": max(sizes),
            "structural_edges_cut": cut,
            "bridges": len(bridges),
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Partition per-authority rule graphs.")
    ap.add_argument("spec_dir", type=Path)
    ap.add_argument("--cap", type=int, default=28)
    ap.add_argument("--floor", type=int, default=12)
    ap.add_argument(
        "--even",
        action="store_true",
        help="also subdivide components larger than the cap; writes the _even variant",
    )
    args = ap.parse_args()
    indir = args.spec_dir / "grouped_rules_by_authority"
    name = "grouped_rules_partitioned_even" if args.even else "grouped_rules_partitioned"
    outdir = args.spec_dir / name
    outdir.mkdir(exist_ok=True)
    for auth in AUTHORITIES:
        src = json.loads((indir / f"{auth}.json").read_text(encoding="utf-8"))
        out = partition(src, args.cap, args.floor, args.even)
        (outdir / f"{auth}.json").write_text(json.dumps(out, indent=2, ensure_ascii=False))
        s = out["balance_stats"]
        print(
            f"{auth:10s} rules {s['rules']:3d} -> copies {s['copies']:3d} "
            f"(x{s['duplication']:.2f}) | units {s['units']:2d} sizes {s['sizes']} | "
            f"cut {s['structural_edges_cut']} bridges {s['bridges']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
