#!/usr/bin/env python3
"""Verify specs/<X>/rules.json is in sync with anonymized_annotated.md.

Usage: check_rules.py specs/<X>

Asserts:
  1. rules.json exists and parses as {"spec": <X>, "rules": [...]}.
  2. The set of `id`s in rules.json equals exactly the set of
     [^wxyz] rule-marker ids in anonymized_annotated.md (no missing,
     no extra, no duplicates).
  3. Each record has exactly the expected keys with the expected
     scalar types (id/authority/text/trigger/behavior/modality strings;
     system_flags/sections/examples string arrays).
  4. `modality` ∈ {must, should}.
  5. `authority` ∈ {root, system, developer, user, guideline} (or null
     when an unlabelled container rule has not yet been explicitly resolved).
  6. Every `examples` entry matches /^eg\\d{3}$/ and appears in the
     annotated spec.
  7. Each rule's `sections` path matches the actual header hierarchy
     at the marker's location in the annotated spec.
  8. Each rule's `authority` matches the structurally inherited authority or
     its validated per-spec authority resolution.
Specs without an anonymized_annotated.md OR without a rules.json are
skipped (rule extraction has not run yet).
"""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

from rule_authority import load_authority_overrides, resolve_authorities

AUTHORITY = {"root", "system", "developer", "user", "guideline"}
MODALITY = {"must", "should"}
EG_RE = re.compile(r"\[\^(eg\d{3})\]")
RULE_RE = re.compile(r"\[\^(\w{4})\]")
EG_ID = re.compile(r"^eg\d{3}$")
HEADER = re.compile(r"^(#{1,6})\s+(.*?)\s*(?:\{(.+?)\})?\s*$")
ATTR_ANCHOR = re.compile(r"#([\w_]+)")
ATTR_KV = re.compile(r"(\w+)=(\S+)")

REQUIRED_FIELDS: dict[str, type] = {
    "id": str,
    "authority": (str, type(None)),
    "system_flags": list,
    "sections": list,
    "text": str,
    "trigger": str,
    "behavior": str,
    "modality": str,
    "examples": list,
}


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")


def parse_spec_structure(text: str, spec_dir: Path):
    """Parse annotated spec to get per-marker sections and authority."""
    lines = text.splitlines()
    stack: list[dict] = []
    marker_info: dict[str, dict] = {}  # id -> {sections, authority}
    in_fence = False

    for line in lines:
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
            attrs = hm.group(3)
            anchor = None
            authority = None
            if attrs:
                am = ATTR_ANCHOR.search(attrs)
                if am:
                    anchor = am.group(1)
                for k, v in ATTR_KV.findall(attrs):
                    if k == "authority":
                        authority = v
            while stack and stack[-1]["level"] >= level:
                stack.pop()
            slug = anchor or slugify(title)
            if authority is None and stack:
                authority = stack[-1]["authority"]
            stack.append({"level": level, "slug": slug, "authority": authority})
            continue

        for m in RULE_RE.finditer(line):
            rid = m.group(1)
            marker_info[rid] = {
                "sections": [s["slug"] for s in stack],
                "authority": stack[-1]["authority"] if stack else None,
            }

    overrides = load_authority_overrides(spec_dir)
    resolved = resolve_authorities(
        {rid: info["authority"] for rid, info in marker_info.items()}, overrides
    )
    for rid, authority in resolved.items():
        marker_info[rid]["authority"] = authority
    return marker_info


def check(spec_dir: Path) -> int:
    spec_name = spec_dir.name
    annotated_path = spec_dir / "anonymized_annotated.md"
    rules_path = spec_dir / "rules.json"

    if not annotated_path.exists() or not rules_path.exists():
        print(f"SKIP {spec_name}: rule extraction not yet run")
        return 0

    annotated_text = annotated_path.read_text(encoding="utf-8")
    eg_tags = set(EG_RE.findall(annotated_text))
    spec_ids = [m for m in RULE_RE.findall(annotated_text)]
    spec_id_set = set(spec_ids)
    spec_id_dupes = sorted(i for i, c in Counter(spec_ids).items() if c > 1)

    try:
        rules_obj = json.loads(rules_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"FAIL {spec_name}: rules.json is not valid JSON: {e}")
        return 1

    if not isinstance(rules_obj, dict) or rules_obj.get("spec") != spec_name:
        print(f"FAIL {spec_name}: rules.json missing top-level {{spec, rules}}.")
        return 1
    rules = rules_obj.get("rules")
    if not isinstance(rules, list):
        print(f"FAIL {spec_name}: rules.json `rules` is not a list.")
        return 1

    # Parse the spec structure for cross-checks
    try:
        marker_info = parse_spec_structure(annotated_text, spec_dir)
    except ValueError as exc:
        print(f"FAIL {spec_name}:\n  - {exc}")
        return 1

    failures: list[str] = []

    if spec_id_dupes:
        failures.append(
            f"spec contains duplicate rule-marker ids "
            f"({len(spec_id_dupes)}): {', '.join(spec_id_dupes)}"
        )

    if len(rules) != len(spec_id_set):
        failures.append(
            f"count mismatch: rules.json has {len(rules)} record(s); "
            f"anonymized_annotated.md has {len(spec_id_set)} rule marker(s)."
        )

    rules_ids = [r.get("id") for r in rules if isinstance(r, dict)]
    record_dupes = sorted(i for i, c in Counter(rules_ids).items() if c and c > 1)
    if record_dupes:
        failures.append(f"duplicate ids in rules.json: {', '.join(record_dupes)}")

    rules_id_set = set(rules_ids) - {None}
    missing = sorted(spec_id_set - rules_id_set)
    extra = sorted(rules_id_set - spec_id_set)
    if missing:
        failures.append(
            f"{len(missing)} marker(s) in spec but missing from rules.json "
            f"(first 5: {', '.join(missing[:5])})"
        )
    if extra:
        failures.append(
            f"{len(extra)} id(s) in rules.json but not in spec (first 5: {', '.join(extra[:5])})"
        )

    bad_schema: list[str] = []
    bad_modality: list[str] = []
    bad_authority: list[str] = []
    bad_examples: list[tuple[str, str]] = []
    bad_sections: list[str] = []
    bad_auth_mismatch: list[str] = []

    for r in rules:
        if not isinstance(r, dict):
            bad_schema.append("<non-dict record>")
            continue
        rid = r.get("id") or "<no-id>"
        keys = set(r.keys())
        if keys != set(REQUIRED_FIELDS):
            bad_schema.append(f"{rid}: keys {sorted(keys)}")
            continue
        for field, expected in REQUIRED_FIELDS.items():
            v = r[field]
            if not isinstance(v, expected):
                bad_schema.append(f"{rid}: {field} has type {type(v).__name__}")
        if r.get("modality") not in MODALITY:
            bad_modality.append(f"{rid} (={r.get('modality')!r})")
        auth = r.get("authority")
        if auth is not None and auth not in AUTHORITY:
            bad_authority.append(f"{rid} (={auth!r})")
        for eg in r.get("examples") or []:
            if not isinstance(eg, str) or not EG_ID.match(eg):
                bad_examples.append((rid, repr(eg)))
            elif f"Example[^{eg}]" not in annotated_text:
                bad_examples.append((rid, eg))

        # Check 7: sections match actual spec structure
        if rid in marker_info:
            actual_sections = marker_info[rid]["sections"]
            claimed_sections = r.get("sections", [])
            if claimed_sections != actual_sections:
                bad_sections.append(
                    f"{rid}: claimed {claimed_sections} != actual {actual_sections}"
                )

        # Check 8: authority matches actual spec structure
        if rid in marker_info:
            actual_auth = marker_info[rid]["authority"]
            claimed_auth = r.get("authority")
            if claimed_auth != actual_auth:
                bad_auth_mismatch.append(
                    f"{rid}: claimed {claimed_auth!r} != actual {actual_auth!r}"
                )

    if bad_schema:
        failures.append(
            f"{len(bad_schema)} record(s) with wrong schema (first 5: {'; '.join(bad_schema[:5])})"
        )
    if bad_modality:
        failures.append(
            f"{len(bad_modality)} record(s) with modality not in {sorted(MODALITY)} "
            f"(first 5: {', '.join(bad_modality[:5])})"
        )
    if bad_authority:
        failures.append(
            f"{len(bad_authority)} record(s) with authority not in {sorted(AUTHORITY)} or null "
            f"(first 5: {', '.join(bad_authority[:5])})"
        )
    if bad_examples:
        sample = ", ".join(f"{r}->{e}" for r, e in bad_examples[:5])
        failures.append(
            f"{len(bad_examples)} example reference(s) malformed or pointing to "
            f"a tag not in the spec (first 5: {sample})"
        )
    if bad_sections:
        failures.append(
            f"{len(bad_sections)} record(s) with sections not matching spec structure "
            f"(first 5: {'; '.join(bad_sections[:5])})"
        )
    if bad_auth_mismatch:
        failures.append(
            f"{len(bad_auth_mismatch)} record(s) with authority not matching spec structure "
            f"(first 5: {'; '.join(bad_auth_mismatch[:5])})"
        )

    if failures:
        print(f"FAIL {spec_name}:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print(
        f"OK {spec_name}: {len(rules)} records match {len(spec_id_set)} rule markers; "
        f"schema, modality, authority, sections, and {len(eg_tags)} eg tag(s) consistent."
    )
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit("usage: check_rules.py specs/<X>")
    spec_dir = Path(sys.argv[1]).resolve()
    if not spec_dir.is_dir():
        sys.exit(f"not a directory: {spec_dir}")
    return check(spec_dir)


if __name__ == "__main__":
    sys.exit(main())
