#!/usr/bin/env python3
"""Derive the semantic-only and per-authority views of ``grouped_rules.json``.

Reads ``specs/<X>/grouped_rules.json`` (which is left untouched) and writes:

  ``specs/<X>/grouped_rules_semantic_only.json`` — the graph with the
      structural tier removed: every ``sec:<path>`` group is dropped from the
      top-level ``groups`` and from each rule's ``groups``, and every
      ``same_section`` edge is dropped from both endpoints.
  ``specs/<X>/grouped_rules_by_authority/<authority>.json`` — for each
      authority level, the subgraph of the semantic-only view induced by that
      level's rules: only edges with both endpoints inside, groups filtered to
      surviving members with empty groups dropped, plus a top-level
      ``authority`` field.

Same-authority pairs are the ones the chain of command cannot resolve, so
each per-authority file is a self-contained input for
``partition_authority_graphs.py`` and stage 3. Cross-authority edges are
intentionally absent from those files.

Usage: build_authority_views.py specs/<X>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

AUTHORITIES = ("root", "system", "developer", "user", "guideline")
SECTION_PREFIX = "sec:"
SECTION_RELATION = "same_section"


def semantic_only(art: dict) -> dict:
    out = dict(art)
    out["groups"] = [g for g in art["groups"] if not g["gid"].startswith(SECTION_PREFIX)]
    rules = []
    for rule in art["rules"]:
        rule = dict(rule)
        rule["groups"] = [g for g in rule["groups"] if not g.startswith(SECTION_PREFIX)]
        rule["neighbor"] = [n for n in rule["neighbor"] if n["relation"] != SECTION_RELATION]
        rules.append(rule)
    out["rules"] = rules
    return out


def authority_view(art: dict, authority: str) -> dict:
    ids = {r["id"] for r in art["rules"] if r["authority"] == authority}
    rules = []
    for rule in art["rules"]:
        if rule["id"] not in ids:
            continue
        rule = dict(rule)
        rule["neighbor"] = [n for n in rule["neighbor"] if n["id"] in ids]
        rules.append(rule)
    groups = []
    for group in art["groups"]:
        members = [m for m in group["members"] if m in ids]
        if members:
            groups.append({**group, "members": members})
    return {
        "spec": art["spec"],
        "source": art["source"],
        "authority": authority,
        "config": art["config"],
        "rules": rules,
        "groups": groups,
    }


def write_json(path: Path, obj: dict) -> None:
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Derive per-authority views of grouped_rules.json.")
    ap.add_argument("spec_dir", type=Path)
    args = ap.parse_args()
    art = json.loads((args.spec_dir / "grouped_rules.json").read_text(encoding="utf-8"))
    sem = semantic_only(art)
    write_json(args.spec_dir / "grouped_rules_semantic_only.json", sem)
    edges = sum(len(r["neighbor"]) for r in sem["rules"])
    print(f"semantic_only  rules {len(sem['rules']):3d} | groups {len(sem['groups']):3d} | directed edges {edges}")
    outdir = args.spec_dir / "grouped_rules_by_authority"
    outdir.mkdir(exist_ok=True)
    covered = 0
    for auth in AUTHORITIES:
        view = authority_view(sem, auth)
        write_json(outdir / f"{auth}.json", view)
        covered += len(view["rules"])
        edges = sum(len(r["neighbor"]) for r in view["rules"])
        print(f"{auth:14s} rules {len(view['rules']):3d} | groups {len(view['groups']):3d} | directed edges {edges}")
    if covered != len(sem["rules"]):
        print(f"FAIL: {len(sem['rules']) - covered} rule(s) have no known authority")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
