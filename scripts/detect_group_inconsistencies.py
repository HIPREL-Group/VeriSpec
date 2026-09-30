#!/usr/bin/env python3
"""Prepare and submit five independent full-group inconsistency searches together.

Offline preparation:
  python3 scripts/detect_group_inconsistencies.py prepare specs/<X> --model MODEL
Use a grouping stored outside the spec directory, with the same spec source:
  python3 scripts/detect_group_inconsistencies.py prepare specs/<X> \
    --grouping-dir GROUPING_DIR --model MODEL
Paid submission (explicit, never performed by prepare):
  python3 scripts/detect_group_inconsistencies.py submit RUN_DIRECTORY
Collection, optionally waiting for the batch:
  python3 scripts/detect_group_inconsistencies.py collect RUN_DIRECTORY --wait
Submit all five independent searches per group together and wait (paid, resumable):
  python3 scripts/detect_group_inconsistencies.py run RUN_DIRECTORY
Validate capacity without generating responses (requires API access):
  python3 scripts/detect_group_inconsistencies.py check-tokens RUN_DIRECTORY

Existing scripts and inputs are read-only. The resolved spec supplies complete
source passages and example bodies.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from string import Template

from build_groups import normalize
from build_rule_graph import EXAMPLE_HEAD, Document

ROOT = Path(__file__).resolve().parents[1]
AUTHORITIES = ("root", "system", "developer", "user", "guideline")
PROMPTS = ROOT / "scripts" / "prompts"
SYSTEM_TEMPLATE = PROMPTS / "detect_group_inconsistencies_system.md"
USER_TEMPLATE = PROMPTS / "detect_group_inconsistencies_user.md"
FIELDS = {"rule_ids", "witness", "unsat_reason", "context_resolution"}
MARKER = re.compile(r"\[\^([a-z0-9]{4})\]")
EXAMPLE_MARKER = re.compile(r"\[\^(eg\d{3})\]")
FENCE = re.compile(r"^\s*(`{3,}|~{3,})")
GOVERNING = ("definitions", "levels_of_authority", "follow_all_applicable_instructions")
REPEATS = 5
DEFAULT_MAX_TOKENS = 128000
TOKEN_HEADROOM = 2048
DIRECT_BATCH_MODES = {"independent_parallel", "extra_independent_parallel"}
# Documented fallback for API/SDK versions that omit model-limit metadata.
# https://platform.claude.com/docs/en/models/opus-5/whats-new-opus-5
MODEL_LIMITS = {"claude-opus-5": {"context_window": 1000000, "max_output_tokens": 128000}}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


class Source:
    """Canonical, nonoverlapping source passages and complete fenced examples."""

    def __init__(self, path):
        self.path = Path(path)
        self.lines = self.path.read_text(encoding="utf-8").splitlines()
        self.doc = Document(self.lines)
        self.anchors = self.doc.by_slug()
        if len(self.anchors) != len(self.doc.sections):
            raise ValueError("Duplicate section anchors in resolved source")
        self.examples = {}
        example_lines = set()
        for ln, line in enumerate(self.lines, 1):
            match = EXAMPLE_HEAD.match(line.strip())
            if not match or self.doc.fenced[ln]:
                continue
            eid = match.group(1)
            if eid in self.examples:
                raise ValueError(f"Duplicate example {eid}")
            opening = None
            for at in range(ln + 1, len(self.lines) + 1):
                candidate = self.lines[at - 1]
                fm = FENCE.match(candidate)
                if fm:
                    opening = (at, fm.group(1))
                    break
                if re.match(r"^#{1,6}\s", candidate) or EXAMPLE_HEAD.match(candidate.strip()):
                    break
            if opening is None:
                raise ValueError(f"Example {eid} has no fenced body; cannot safely extract")
            start, fence = opening
            closing = re.compile(r"^\s*" + re.escape(fence[0]) + "{" + str(len(fence)) + r",}\s*$")
            end = next(
                (
                    at
                    for at in range(start + 1, len(self.lines) + 1)
                    if closing.match(self.lines[at - 1])
                ),
                None,
            )
            if end is None:
                raise ValueError(f"Unclosed example {eid}")
            sec = self.doc.line_section[ln]
            self.examples[eid] = {
                "id": eid,
                "source": self.location(ln, end, sec),
                "text": "\n".join(self.lines[ln - 1 : end]),
            }
            example_lines.update(range(ln, end + 1))
        self.blocks = {}
        commentary_lines = set()
        in_commentary = False
        for ln, raw in enumerate(self.lines, 1):
            if re.match(r'^\s*!!!\s+meta\s+"Commentary"', raw):
                in_commentary = True
            elif raw.strip() and not raw.startswith((" ", "\t")):
                in_commentary = False
            if in_commentary:
                commentary_lines.add(ln)
        self.by_section = defaultdict(set)
        self.examples_by_section = defaultdict(set)
        self.marker_blocks = defaultdict(set)
        for eid, ex in self.examples.items():
            self.examples_by_section[ex["source"]["section"]].add(eid)
        buf = []

        def flush():
            if not buf:
                return
            first, last = buf[0], buf[-1]
            text = "\n".join(self.lines[first - 1 : last]).strip()
            sec = self.doc.line_section[first]
            bid = f"ctx{first:05d}"
            self.blocks[bid] = {
                "id": bid,
                "source": self.location(first, last, sec),
                "text": text,
                "commentary": first in commentary_lines,
            }
            self.by_section[self.blocks[bid]["source"]["section"]].add(bid)
            for rid in MARKER.findall(text):
                self.marker_blocks[rid].add(bid)
            buf.clear()

        headings = {s["header_line"] for s in self.doc.sections}
        for ln, line in enumerate(self.lines, 1):
            if (
                ln in example_lines
                or ln in headings
                or (not line.strip() and not self.doc.fenced[ln])
            ):
                flush()
            else:
                buf.append(ln)
        flush()
        self.normalized_blocks = {bid: normalize(b["text"]) for bid, b in self.blocks.items()}
        self.search_spans = []
        offset = 0
        for bid, text in self.normalized_blocks.items():
            self.search_spans.append((offset, offset + len(text), bid))
            offset += len(text) + 1
        self.search_text = " ".join(self.normalized_blocks.values())
        self.quote_cache = {}

    def quote_context(self, quote):
        """Ground a possibly multi-paragraph excerpt in complete source blocks."""
        if quote not in self.quote_cache:
            blocks, examples = set(), set()
            start = self.search_text.find(quote)
            while start >= 0:
                end = start + len(quote)
                blocks.update(bid for lo, hi, bid in self.search_spans if lo < end and hi > start)
                start = self.search_text.find(quote, start + 1)
            examples.update(
                eid for eid, ex in self.examples.items() if quote in normalize(ex["text"])
            )
            self.quote_cache[quote] = blocks, examples
        return self.quote_cache[quote]

    def location(self, start, end, section):
        sec = self.doc.sections[section] if section is not None else None
        return {
            "file": self.path.name,
            "lines": [start, end],
            "section": sec["slug"] if sec else None,
            "headings": [
                self.lines[self.doc.sections[self.anchors[s]]["header_line"] - 1]
                for s in sec["path"]
            ]
            if sec
            else [],
        }

    def section_context(self, anchor):
        """Full directly owned prose plus ancestor preambles, not all descendants."""
        anchor = anchor.lstrip("#")
        if anchor not in self.anchors:
            raise ValueError(f"Unknown source section #{anchor}")
        sec = self.doc.sections[self.anchors[anchor]]
        blocks, examples = set(), set()
        for name in sec["path"]:
            blocks.update(self.by_section[name])
            examples.update(self.examples_by_section[name])
        return blocks, examples

    def rule_context(self, rule):
        blocks, examples = set(), set(rule.get("examples", []))
        context = rule["related_context"]
        anchors = set(rule["sections"]) | set(GOVERNING)
        refs = set()
        quotes = set()

        def visit(value):
            if isinstance(value, dict):
                if "where" in value and value["where"]:
                    refs.add(value["where"])
                if value.get("quote"):
                    quotes.add(normalize(value["quote"].split("[...]")[0]))
                for item in value.values():
                    visit(item)
            elif isinstance(value, list):
                for item in value:
                    visit(item)

        visit(context)
        anchors.update(x["anchor"].lstrip("#") for x in context.get("section_references", []))
        examples.update(x["id"] for x in context.get("examples", []))
        for ref in refs:
            if ref.startswith("#"):
                anchors.add(ref[1:])
            else:
                rid = ref.removeprefix("[^").removesuffix("]")
                if rid in self.examples:
                    examples.add(rid)
                elif rid in self.marker_blocks:
                    blocks.update(self.marker_blocks[rid])
                    anchors.update(
                        self.blocks[b]["source"]["section"] for b in self.marker_blocks[rid]
                    )
                else:
                    raise ValueError(f"{rule['id']}: unresolved context reference {ref}")
        for anchor in anchors:
            bs, es = self.section_context(anchor)
            blocks.update(bs)
            examples.update(es)
        own = self.marker_blocks.get(rule["id"])
        if not own:
            raise ValueError(f"Rule marker {rule['id']} missing from source prose")
        blocks.update(own)
        # Some extracted ancestor commentary points at its container, although
        # the actual paragraph lives in a descendant. Recover the full original
        # paragraph instead of silently dropping it or reusing its clipped quote.
        for quote in quotes:
            if not quote or any(quote in self.normalized_blocks[b] for b in blocks):
                continue
            matches, example_matches = self.quote_context(quote)
            if not matches and not example_matches:
                raise ValueError(
                    f"{rule['id']}: extracted quote cannot be grounded in full source passages"
                )
            blocks.update(matches)
            examples.update(example_matches)
        for bid in blocks:
            examples.update(EXAMPLE_MARKER.findall(self.blocks[bid]["text"]))
        if examples - self.examples.keys():
            raise ValueError(f"Missing example bodies: {sorted(examples - self.examples.keys())}")
        return blocks, examples, own


def group_relations(rules, rule_ids):
    """Keep within-group relations as unordered pairs, collapsing mirrored entries."""
    relations = {}
    for rid in sorted(rule_ids):
        for edge in rules[rid]["neighbor"]:
            if edge["relation"] == "shares_dimension" or edge["id"] not in rule_ids:
                continue
            a, b = sorted((rid, edge["id"]))
            record = {
                "a": a,
                "b": b,
                "relation": edge["relation"],
            }
            for key in ("subtype", "source", "via", "evidence"):
                if edge.get(key) is not None:
                    record[key] = copy.deepcopy(edge[key])
            # Evidence is part of the identity: distinct supporting examples or
            # passages must survive even when endpoints and labels are identical.
            key = json.dumps(record, sort_keys=True, ensure_ascii=False)
            stored = relations.setdefault(key, record)
            note = edge.get("note")
            if edge["relation"] == "cross_reference" and note in (
                "cited from the rule's own sentence",
                "cited by that rule's sentence",
            ):
                note = None
            if note and note not in stored.setdefault("notes", []):
                stored["notes"].append(note)
    result = [relations[key] for key in sorted(relations)]
    for record in result:
        if "notes" in record:
            record["notes"].sort()
    return result


def build_packet(src, partition, unit, source):
    rules = {r["id"]: r for r in src["rules"]}
    nodes = {n["id"]: n for n in partition["nodes"]}
    roles = defaultdict(set)
    for member in unit["members"]:
        n = nodes[member]
        roles[n["rule"]].add(n["context"])
    mapping = {rid: source.rule_context(rules[rid]) for rid in sorted(roles)}
    block_ids = set().union(*(v[0] for v in mapping.values()))
    example_ids = set().union(*(v[1] for v in mapping.values()))
    # Deduplicate exact source text even when it occurs at multiple locations;
    # keep all source locations and remap every rule's references.
    passages, canonical, by_text = {}, {}, {}
    for bid in sorted(block_ids):
        b = source.blocks[bid]
        key = (b["text"], b["commentary"])
        chosen = by_text.setdefault(key, bid)
        canonical[bid] = chosen
        if chosen not in passages:
            passages[chosen] = {
                "id": chosen,
                "sources": [],
                "text": b["text"],
                "commentary": b["commentary"],
            }
        passages[chosen]["sources"].append(b["source"])
    records = []
    for rid in sorted(roles):
        r = rules[rid]
        blocks, examples, own = mapping[rid]
        record = {
            k: r[k]
            for k in (
                "id",
                "authority",
                "modality",
                "trigger",
                "behavior",
                "sections",
                "system_flags",
            )
        }
        record.update(
            dimension_roles_in_group=sorted(roles[rid]),
            source_text_refs=sorted({canonical[b] for b in own}),
            context_refs=sorted({canonical[b] for b in blocks}),
            example_refs=sorted(examples),
            authority_provenance=r["related_context"].get("authority_provenance"),
        )
        facets = {
            k: v
            for k, v in r["related_context"].get("facets", {}).items()
            if v not in (None, "unconditional_or_unspecified")
        }
        if facets:
            record["extracted_scope_hints"] = {
                "facets": facets,
                "specifics": r["related_context"].get("facet_specifics", {}),
            }
        records.append(record)
    return {
        "authority": partition["authority"],
        "group_id": unit["cid"],
        "group_key": f"{partition['authority']}/{unit['cid']}",
        "partition_provenance": unit["provenance"],
        "context": list(passages.values()),
        "examples": [source.examples[eid] for eid in sorted(example_ids)],
        "rules": records,
        "relations": group_relations(rules, set(roles)),
    }


def render_prompt(packet, template):
    def render_passages(passages):
        parts, previous_paths = [], None
        for passage in passages:
            locations = passage.get("sources") or [passage["source"]]
            paths = tuple(dict.fromkeys(tuple(loc["headings"]) for loc in locations))
            if paths != previous_paths:
                # Keep heading text, anchors, and authority attributes. Source
                # filenames and line numbers remain in the saved packet only.
                titles = [
                    " / ".join(re.sub(r"^#{1,6}\s+", "", heading) for heading in path)
                    or "Document preamble"
                    for path in paths
                ]
                parts.append("## " + "; ".join(titles))
                previous_paths = paths
            label = f"### {passage['id']}"
            if passage.get("commentary"):
                label += " [commentary, non-normative]"
            parts.append(label + "\n\n" + passage["text"])
        return "\n\n".join(parts)

    context_text = render_passages(packet["context"])
    example_text = render_passages(packet["examples"])
    common_context = set.intersection(*(set(r["context_refs"]) for r in packet["rules"]))
    rule_texts = []
    for rule in packet["rules"]:
        lines = [
            f"### {rule['id']}",
            f"modality: {rule['modality']}",
            f"trigger: {rule['trigger']}",
            f"behavior: {rule['behavior']}",
            "Source: " + ", ".join(rule["source_text_refs"]),
        ]
        additional = sorted(set(rule["context_refs"]) - common_context - set(rule["source_text_refs"]))
        if additional:
            lines.append("Context: " + ", ".join(additional))
        if rule["example_refs"]:
            lines.append("Examples: " + ", ".join(rule["example_refs"]))
        if rule["system_flags"]:
            lines.append("System flags: " + ", ".join(rule["system_flags"]))
        hints = rule.get("extracted_scope_hints", {})
        if hints:
            specifics = hints.get("specifics", {})
            scopes = [
                f"{facet}={value}" + (f" ({specifics[facet]})" if facet in specifics else "")
                for facet, value in hints.get("facets", {}).items()
            ]
            scopes.extend(f"{facet}={value}" for facet, value in specifics.items()
                          if facet not in hints.get("facets", {}))
            if scopes:
                lines.append("Scope hints: " + "; ".join(scopes))
        rule_texts.append("\n".join(lines))
    return Template(template).substitute(
        authority=packet["authority"],
        context=context_text,
        examples=example_text or "No associated examples.",
        common_context_refs=", ".join(sorted(common_context)) or "None.",
        rules="\n\n".join(rule_texts),
    )


def validate_partition(src, part):
    rules = {r["id"]: r for r in src["rules"]}
    nodes = {n["id"]: n for n in part["nodes"]}
    if len(rules) != len(src["rules"]) or len(nodes) != len(part["nodes"]):
        raise ValueError("Duplicate source rule or partition node IDs")
    if (
        src["authority"] != part["authority"]
        or src["spec"] != part["spec"]
        or src["source"] != part["source"]
    ):
        raise ValueError("Partition/source identity mismatch")
    if {n["rule"] for n in nodes.values()} != rules.keys():
        raise ValueError("Partition does not cover exactly the source rule inventory")
    for node in nodes.values():
        r = rules[node["rule"]]
        if node["context"] not in r["dimensions"] or r["authority"] != src["authority"]:
            raise ValueError(f"Invalid role node {node['id']}")
        for key in (
            "trigger",
            "behavior",
            "modality",
            "sections",
            "related_context",
            "system_flags",
            "neighbor",
        ):
            if key not in r:
                raise ValueError(f"Rule {r['id']} lacks {key}")
    all_members = []
    group_ids = set()
    for group in part["components"]:
        if not re.fullmatch(r"[A-Za-z0-9:_-]+", group["cid"]) or group["cid"] in group_ids:
            raise ValueError("Unsafe or duplicate group ID")
        group_ids.add(group["cid"])
        if not group["members"] or group["size"] != len(group["members"]):
            raise ValueError("Empty group or inconsistent size")
        all_members.extend(group["members"])
    if len(all_members) != len(set(all_members)) or set(all_members) != nodes.keys():
        raise ValueError("Every partition copy must occur in exactly one group")


def prepare(args):
    if args.max_tokens <= 0:
        raise ValueError("max-tokens must be positive")
    effort = getattr(args, "effort", None)
    if effort is None and args.model == "claude-opus-5":
        effort = "xhigh"
    if effort is not None and effort not in ("low", "medium", "high", "xhigh", "max"):
        raise ValueError(f"Unsupported effort: {effort}")
    limits = MODEL_LIMITS.get(args.model)
    if limits and args.max_tokens > limits["max_output_tokens"]:
        raise ValueError(
            f"{args.model} supports at most {limits['max_output_tokens']} output tokens"
        )
    spec = Path(args.spec).resolve()
    if not spec.is_dir():
        spec = ROOT / "specs" / args.spec
    spec = spec.resolve()
    grouping_arg = getattr(args, "grouping_dir", None)
    grouping = Path(grouping_arg).resolve() if grouping_arg else spec
    if not grouping.is_dir():
        raise ValueError(f"Grouping directory does not exist: {grouping}")
    requests, packets, inputs = [], [], {}
    system_prompt = SYSTEM_TEMPLATE.read_text(encoding="utf-8")
    user_template = USER_TEMPLATE.read_text(encoding="utf-8")
    for path in (SYSTEM_TEMPLATE, USER_TEMPLATE):
        inputs[str(path)] = sha(path)
    sources = {}
    selected = set(args.groups or [])
    for authority in args.authorities:
        src_path = grouping / "grouped_rules_by_authority" / f"{authority}.json"
        part_path = grouping / "grouped_rules_partitioned" / f"{authority}.json"
        src, part = read_json(src_path), read_json(part_path)
        if src["spec"] != spec.name:
            raise ValueError(f"Grouping spec {src['spec']} does not match {spec.name}")
        if src["authority"] != authority:
            raise ValueError(f"Wrong authority in {src_path}")
        validate_partition(src, part)
        source_path = (spec / src["source"]).resolve()
        if not source_path.is_relative_to(spec.resolve()):
            raise ValueError("Source escapes spec directory")
        if source_path not in sources:
            sources[source_path] = Source(source_path)
        for path in (src_path, part_path, source_path):
            inputs[str(path.resolve())] = sha(path)
        units = part["components"]
        if authority in ("system", "developer"):
            # The analysis granularity for these two authorities is the whole
            # authority, even when the saved partition contains multiple units.
            units = [
                {
                    "cid": "unit:01",
                    "size": len(part["nodes"]),
                    "members": [node["id"] for node in part["nodes"]],
                    "provenance": {
                        "method": "single_group_per_authority",
                        "source_components": [unit["cid"] for unit in part["components"]],
                    },
                }
            ]
        for unit in units:
            key = f"{authority}/{unit['cid']}"
            if selected and key not in selected:
                continue
            packet = build_packet(src, part, unit, sources[source_path])
            custom_id = f"{authority}-{unit['cid'].replace(':', '-')}"
            prompt = render_prompt(packet, user_template)
            request = {
                "custom_id": custom_id,
                "params": {
                    "model": args.model,
                    "max_tokens": args.max_tokens,
                    "system": system_prompt,
                    "messages": [{"role": "user", "content": prompt}],
                },
            }
            if effort is not None:
                request["params"]["output_config"] = {"effort": effort}
            requests.append(request)
            packets.append((custom_id, packet, prompt))
    if not requests or (selected - {p[1]["group_key"] for p in packets}):
        raise ValueError("No groups selected, or a requested authority/group does not exist")
    ids = [r["custom_id"] for r in requests]
    if len(ids) != len(set(ids)) or any(len(cid) > 64 for cid in ids):
        raise ValueError("Duplicate or overlong API request IDs")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
    run = (
        Path(args.output)
        if args.output
        else ROOT / "analysis" / spec.name / "group_inconsistencies" / stamp
    )
    run.mkdir(parents=True, exist_ok=False)
    (run / "prompts").mkdir()
    (run / "packets").mkdir()
    request_path = run / "requests.jsonl"
    request_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in requests), encoding="utf-8"
    )
    groups = []
    artifact_hashes = {"requests.jsonl": sha(request_path)}
    for custom_id, packet, prompt in packets:
        pp, jp = run / "prompts" / f"{custom_id}.md", run / "packets" / f"{custom_id}.json"
        pp.write_text(prompt, encoding="utf-8")
        write_json(jp, packet)
        artifact_hashes[str(pp.relative_to(run))] = sha(pp)
        artifact_hashes[str(jp.relative_to(run))] = sha(jp)
        info = {
            "custom_id": custom_id,
            "group_key": packet["group_key"],
            "rule_ids": [r["id"] for r in packet["rules"]],
            "context_count": len(packet["context"]),
            "example_count": len(packet["examples"]),
            "prompt_characters": len(prompt),
        }
        groups.append(info)
        print(
            f"{info['group_key']}: {len(info['rule_ids'])} rules, {info['context_count']} passages, {info['example_count']} examples, {len(prompt):,} prompt characters"
        )
    write_json(
        run / "manifest.json",
        {
            "schema_version": 2,
            "execution_policy": "five_independent_requests_together",
            "requests_per_group": REPEATS,
            "spec": spec.name,
            "grouping_dir": str(grouping),
            "model": args.model,
            "max_tokens": args.max_tokens,
            "effort": effort,
            "groups": groups,
            "input_sha256": inputs,
            "artifact_sha256": artifact_hashes,
            "system_prompt": system_prompt,
            "group_policy": "Existing partition groups for Root/User/Guideline; one combined authority-wide group each for System and Developer. Original rule IDs are deduplicated within each request.",
            "generator_sha256": sha(__file__),
            "context_policy": "Union of full directly owned prose of owning/referenced sections and their ancestors, explicit rule references, and shared authority/definition sections; no recursive expansion of every outgoing link. Examples are extracted in full and deduplicated by ID. Source references are deduplicated by exact passage text. Upstream speculative coverage/ambiguity notes are not model evidence.",
        },
    )
    print(
        f"Prepared {len(requests)} full-group inputs offline in {run.resolve()}; "
        f"submission will contain {len(requests) * REPEATS} independent requests. No API calls made."
    )
    return 0


def checked_manifest(run):
    manifest = read_json(run / "manifest.json")
    for relative, expected in manifest["artifact_sha256"].items():
        path = (run / relative).resolve()
        if not path.is_relative_to(run.resolve()) or sha(path) != expected:
            raise ValueError(f"Prepared artifact changed: {relative}; prepare a new run")
    return manifest


def client():
    import anthropic
    from dotenv import load_dotenv

    load_dotenv(ROOT / "scripts" / ".env")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise ValueError("ANTHROPIC_API_KEY is required for API operations, not offline prepare/reprocessing")
    return anthropic.Anthropic(timeout=600, max_retries=0)


def submit_batch(args):
    run = Path(args.run)
    if (run / "iteration_config.json").exists():
        raise ValueError("This is a legacy iterative run; preserve it and prepare a fresh run")
    manifest = checked_manifest(run)
    api = client()
    requests = [
        json.loads(line)
        for line in (run / "requests.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    if (run / "submission_started.json").exists():
        raise FileExistsError(f"Submission already started: {run}; do not blindly retry")
    preflight_capacity(run, manifest, requests, api)
    # Exclusive ledger blocks accidental repeat submissions, including ambiguous
    # network failures where the server may already have accepted a paid batch.
    with (run / "submission_started.json").open("x", encoding="utf-8") as stream:
        json.dump(
            {"manifest_sha256": sha(run / "manifest.json"), "request_count": len(requests)}, stream
        )
    print(f"Submitting {len(requests)} requests using {manifest['model']}...")
    batch = api.messages.batches.create(requests=requests)
    write_json(
        run / "submission.json",
        {"batch_id": batch.id, "manifest_sha256": sha(run / "manifest.json")},
    )
    print(f"Batch {batch.id} submitted. Use collect to retrieve results.")
    return 0


def remove_trailing_commas(text):
    """Remove only commas before } or ] outside JSON strings, never change string contents."""
    output, removed = [], 0
    in_string = escaped = False
    previous = None
    for index, char in enumerate(text):
        if in_string:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
                previous = '"'
            continue
        if char == '"':
            in_string = True
        elif char == "," and previous not in (None, "[", "{", ",", ":"):
            following = index + 1
            while following < len(text) and text[following] in " \t\r\n":
                following += 1
            if following < len(text) and text[following] in "}]":
                removed += 1
                continue
        output.append(char)
        if char not in " \t\r\n":
            previous = char
    return "".join(output), removed


def parse_response(text, allowed):
    repairs = {}
    try:
        findings = json.loads(text)
    except json.JSONDecodeError:
        repaired, removed = remove_trailing_commas(text)
        try:
            findings = json.loads(repaired)
        except json.JSONDecodeError as exc:
            raise ValueError("Model output is not a complete JSON array") from exc
        repairs = {"removed_trailing_commas": removed}
    if not isinstance(findings, list):
        raise ValueError("Model output must be a JSON array")
    for finding in findings:
        if not isinstance(finding, dict) or set(finding) != FIELDS:
            raise ValueError("Each finding must have exactly the four required fields")
        ids = finding["rule_ids"]
        if (
            not isinstance(ids, list)
            or len(ids) != 2
            or not all(isinstance(x, str) for x in ids)
            or len(set(ids)) != 2
            or not set(ids) <= set(allowed)
        ):
            raise ValueError(
                "Inconsistency endpoints must be two distinct original rule IDs from this group"
            )
        for key in FIELDS - {"rule_ids"}:
            if not isinstance(finding[key], str) or not finding[key].strip():
                raise ValueError(f"Missing or empty {key}")
    return findings, repairs


def validate_response(text, allowed):
    return parse_response(text, allowed)[0]


def process_result(raw, group):
    record = {"custom_id": group["custom_id"], "group_key": group["group_key"]}
    result = raw["result"]
    if result["type"] != "succeeded":
        return record | {"status": "failed", "error": result["type"]}
    message = result["message"]
    if message.get("stop_reason") != "end_turn":
        return record | {
            "status": "failed",
            "error": f"Incomplete/nonfinal response: {message.get('stop_reason')}",
        }
    text = "".join(b["text"] for b in message["content"] if b["type"] == "text")
    try:
        findings, repairs = parse_response(text, group["rule_ids"])
    except ValueError as exc:
        return record | {"status": "failed", "error": str(exc)}
    if repairs:
        record["format_repairs"] = repairs
    return record | {"status": "succeeded", "findings": findings, "usage": message.get("usage", {})}


def collect_batch(args):
    run = Path(args.run)
    manifest = checked_manifest(run)
    submission = read_json(run / "submission.json")
    if submission["manifest_sha256"] != sha(run / "manifest.json"):
        raise ValueError("Manifest changed after submission")
    api = client()
    while True:
        batch = api.messages.batches.retrieve(submission["batch_id"])
        print(f"Batch {batch.id}: {batch.processing_status}", flush=True)
        if batch.processing_status == "ended":
            break
        if not args.wait:
            return 0
        time.sleep(args.poll_seconds)
    for name in ("raw", "results"):
        (run / name).mkdir(exist_ok=True)
    groups = {g["custom_id"]: g for g in manifest["groups"]}
    results = {}
    for result in api.messages.batches.results(submission["batch_id"]):
        raw = result.model_dump(mode="json")
        cid = raw["custom_id"]
        if cid not in groups or cid in results:
            raise ValueError(f"Unexpected or duplicate batch result ID: {cid}")
        write_json(run / "raw" / f"{cid}.json", raw)
        results[cid] = process_result(raw, groups[cid])
    summary = save_pass_results(run, manifest, submission["batch_id"], results)
    return 1 if summary["failed_group_ids"] else 0


def save_pass_results(run, manifest, batch_id, results):
    groups = {g["custom_id"]: g for g in manifest["groups"]}
    (run / "results").mkdir(exist_ok=True)
    for cid, group in groups.items():
        record = results.setdefault(
            cid,
            {
                "custom_id": cid,
                "group_key": group["group_key"],
                "status": "failed",
                "error": "Missing batch result",
            },
        )
        atomic_json(run / "results" / f"{cid}.json", record)
    summary = {
        "batch_id": batch_id,
        "groups": [results[cid] for cid in groups],
        "findings_count": sum(len(r.get("findings", [])) for r in results.values()),
        "failed_group_ids": [cid for cid in groups if results[cid]["status"] != "succeeded"],
        "note": "Findings are retained per group, including distinct witnesses for overlapping pairs. Processing failures are not empty successful findings; no automatic resubmission is performed.",
    }
    atomic_json(run / "summary.json", summary)
    print(
        f"Saved {summary['findings_count']} findings; {len(summary['failed_group_ids'])} failed groups in {run.resolve()}"
    )
    return summary


def reprocess_pass(run):
    """Rebuild derived results from saved raw responses; never edit raw data or call an API."""
    manifest = checked_manifest(run)
    submission = read_json(run / "submission.json")
    if submission["manifest_sha256"] != sha(run / "manifest.json"):
        raise ValueError(f"Manifest changed after submission: {run}")
    results = {}
    for group in manifest["groups"]:
        cid = group["custom_id"]
        path = run / "raw" / f"{cid}.json"
        if not path.exists():
            continue
        raw = read_json(path)
        if raw["custom_id"] != cid:
            raise ValueError(f"Raw result ID does not match filename: {path}")
        results[cid] = process_result(raw, group)
    return save_pass_results(run, manifest, submission["batch_id"], results)


def atomic_json(path, value):
    """Publish derived state without leaving a partially written JSON file."""
    path = Path(path)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def finding_key(finding):
    """Exact textual deduplication, ignoring pair order and whitespace only."""
    return (
        tuple(sorted(finding["rule_ids"])),
        *(" ".join(finding[k].split()) for k in ("witness", "unsat_reason", "context_resolution")),
    )


def preflight_capacity(run, manifest, requests, api):
    """Check native model limits and count exact request payloads before paid submission."""
    models = {}
    for model in sorted({r["params"]["model"] for r in requests}):
        info = api.models.retrieve(model).model_dump(mode="json")
        fallback = MODEL_LIMITS.get(model, MODEL_LIMITS.get(info.get("id"), {}))
        context_window = info.get("max_input_tokens") or fallback.get("context_window")
        max_output = info.get("max_tokens") or fallback.get("max_output_tokens")
        if (
            type(context_window) is not int
            or context_window <= 0
            or type(max_output) is not int
            or max_output <= 0
        ):
            raise ValueError(
                f"Cannot determine token limits for {model}; refusing unchecked submission"
            )
        models[model] = {"context_window": context_window, "max_output_tokens": max_output}
    payloads, request_keys = {}, {}
    for request in requests:
        params = request["params"]
        payload = {
            k: params[k]
            for k in ("model", "messages", "system", "thinking", "tools", "tool_choice")
            if k in params
        }
        key = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        payloads.setdefault(key, payload)
        request_keys[request["custom_id"]] = key

    def count(item):
        key, payload = item
        count = api.messages.count_tokens(**payload).input_tokens
        if type(count) is not int or count < 0:
            raise ValueError("Token-count API returned an invalid count")
        return key, count

    # Five identical independent requests share one token-count check per group.
    with ThreadPoolExecutor(max_workers=4) as pool:
        counts = dict(pool.map(count, payloads.items()))
    checks = []
    for request in requests:
        cid, params = request["custom_id"], request["params"]
        limits = models[params["model"]]
        input_tokens = counts[request_keys[cid]]
        output = params["max_tokens"]
        headroom = max(TOKEN_HEADROOM, (input_tokens + 99) // 100)
        remaining = limits["context_window"] - input_tokens - output - headroom
        checks.append(
            {
                "custom_id": cid,
                "input_tokens": input_tokens,
                "max_tokens": output,
                "headroom_tokens": headroom,
                "remaining_context_tokens": remaining,
                "fits": 0 < output <= limits["max_output_tokens"] and remaining >= 0,
            }
        )
    report = {
        "manifest_sha256": sha(run / "manifest.json"),
        "models": models,
        "checks": checks,
        "unique_payloads_counted": len(counts),
        "all_fit": all(c["fits"] for c in checks),
        "note": "Input token counts plus the full requested output allowance and safety headroom must fit. No input is truncated or group split. A native output ceiling cannot guarantee that generation will finish before reaching it.",
    }
    atomic_json(run / "token_checks.json", report)
    failed = [c["custom_id"] for c in checks if not c["fits"]]
    if failed:
        raise ValueError(
            f"Token capacity check failed for {failed}; see {run / 'token_checks.json'}. No batch submitted."
        )
    print(
        f"Capacity checked: {len(checks)} requests, {len(counts)} distinct group prompts; "
        f"largest input {max(c['input_tokens'] for c in checks):,} tokens; "
        f"minimum remaining context {min(c['remaining_context_tokens'] for c in checks):,}.",
        flush=True,
    )
    return report


def prepare_parallel_batch(run):
    """Materialize all five complete, independent requests per group before any API call."""
    manifest = checked_manifest(run)
    if (
        manifest.get("execution_policy") != "five_independent_requests_together"
        or manifest.get("requests_per_group") != REPEATS
        or (run / "iteration_config.json").exists()
    ):
        raise ValueError(
            "This is an older single/iterative run; preserve it and prepare a fresh five-request run"
        )
    destination = run / "batch"
    if destination.exists():
        saved = checked_manifest(destination)
        if saved.get("parent_manifest_sha256") != sha(run / "manifest.json"):
            raise ValueError("Parent manifest changed after batch preparation")
        return destination
    addition = ""
    # Previously prepared runs carry a hashed suffix snapshot. Honor that saved
    # input when resuming them; new runs already contain the full user prompt.
    if "pass_prompt_template.md" in manifest["artifact_sha256"]:
        template = Template((run / "pass_prompt_template.md").read_text(encoding="utf-8"))
        if template.get_identifiers():
            raise ValueError(
                "Pass template must be independent of pass numbers or prior findings; prepare a fresh run"
            )
        addition = template.substitute()
    bases = [
        json.loads(line)
        for line in (run / "requests.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    groups = {g["custom_id"]: g for g in manifest["groups"]}
    if len(bases) != len(groups) or {r["custom_id"] for r in bases} != set(groups):
        raise ValueError("Base requests do not match group inventory")
    requests, records = [], []
    for base in bases:
        group = groups[base["custom_id"]]
        params = copy.deepcopy(base["params"])
        if addition:
            params["messages"][0]["content"] += "\n\n" + addition
        for number in range(1, REPEATS + 1):
            cid = f"{base['custom_id']}-pass-{number:03d}"
            if len(cid) > 64:
                raise ValueError(f"API request ID too long: {cid}")
            requests.append({"custom_id": cid, "params": copy.deepcopy(params)})
            records.append(
                group
                | {
                    "custom_id": cid,
                    "group_custom_id": base["custom_id"],
                    "pass_number": number,
                    "prompt_characters": len(params["messages"][0]["content"]),
                }
            )
    with tempfile.TemporaryDirectory(prefix=".preparing-batch-", dir=run) as temporary:
        folder = Path(temporary) / "batch"
        folder.mkdir()
        (folder / "prompts").mkdir()
        path = folder / "requests.jsonl"
        path.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in requests), encoding="utf-8"
        )
        hashes = {"requests.jsonl": sha(path)}
        for request in requests:
            path = folder / "prompts" / f"{request['custom_id']}.md"
            path.write_text(request["params"]["messages"][0]["content"], encoding="utf-8")
            hashes[str(path.relative_to(folder))] = sha(path)
        write_json(
            folder / "manifest.json",
            {
                "schema_version": 2,
                "model": manifest["model"],
                "max_tokens": manifest["max_tokens"],
                **({"effort": manifest["effort"]} if "effort" in manifest else {}),
                "groups": records,
                "requests_per_group": REPEATS,
                "mode": "independent_parallel",
                "parent_manifest_sha256": sha(run / "manifest.json"),
                "artifact_sha256": hashes,
            },
        )
        folder.rename(destination)
    print(
        f"Prepared {len(requests)} independent requests for one batch "
        f"({REPEATS} per complete group).",
        flush=True,
    )
    return destination


def set_request_effort(params, effort):
    if effort is None:
        return
    if effort not in ("low", "medium", "high", "xhigh", "max"):
        raise ValueError(f"Unsupported effort: {effort}")
    params["output_config"] = {"effort": effort}


def prepare_extra_passes(args):
    """Prepare additional independent pass numbers from an existing base run."""
    parent = Path(args.run)
    manifest = checked_manifest(parent)
    if (
        manifest.get("execution_policy") != "five_independent_requests_together"
        or manifest.get("requests_per_group") != REPEATS
        or (parent / "iteration_config.json").exists()
    ):
        raise ValueError("Extra passes require a prepared five-request parent run")
    if args.start_pass <= REPEATS:
        raise ValueError(f"Extra pass numbering must start after the existing {REPEATS} passes")
    if args.count <= 0:
        raise ValueError("count must be positive")
    pass_numbers = list(range(args.start_pass, args.start_pass + args.count))
    destination = (
        Path(args.output)
        if args.output
        else parent
        / (
            f"extra_passes_{pass_numbers[0]:03d}_{pass_numbers[-1]:03d}"
            + (f"_{args.effort}" if args.effort else "")
        )
    )
    destination = destination.resolve()
    if destination.exists():
        raise FileExistsError(f"Output already exists: {destination}")
    bases = [
        json.loads(line)
        for line in (parent / "requests.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    groups = {g["custom_id"]: g for g in manifest["groups"]}
    if len(bases) != len(groups) or {r["custom_id"] for r in bases} != set(groups):
        raise ValueError("Base requests do not match group inventory")
    requests, records = [], []
    for base in bases:
        group = groups[base["custom_id"]]
        params = copy.deepcopy(base["params"])
        set_request_effort(params, args.effort)
        for number in pass_numbers:
            cid = f"{base['custom_id']}-pass-{number:03d}"
            if len(cid) > 64:
                raise ValueError(f"API request ID too long: {cid}")
            requests.append({"custom_id": cid, "params": copy.deepcopy(params)})
            records.append(
                group
                | {
                    "custom_id": cid,
                    "group_custom_id": base["custom_id"],
                    "pass_number": number,
                    "prompt_characters": len(params["messages"][0]["content"]),
                }
            )
    destination.mkdir(parents=True)
    (destination / "prompts").mkdir()
    request_path = destination / "requests.jsonl"
    request_path.write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in requests), encoding="utf-8"
    )
    hashes = {"requests.jsonl": sha(request_path)}
    for request in requests:
        path = destination / "prompts" / f"{request['custom_id']}.md"
        path.write_text(request["params"]["messages"][0]["content"], encoding="utf-8")
        hashes[str(path.relative_to(destination))] = sha(path)
    write_json(
        destination / "manifest.json",
        {
            "schema_version": 2,
            "model": manifest["model"],
            "max_tokens": manifest["max_tokens"],
            **({"effort": args.effort} if args.effort else {}),
            "groups": records,
            "requests_per_group": len(pass_numbers),
            "pass_numbers": pass_numbers,
            "mode": "extra_independent_parallel",
            "parent_run": str(parent.resolve()),
            "parent_manifest_sha256": sha(parent / "manifest.json"),
            "artifact_sha256": hashes,
            "note": "Additional independent full-group requests prepared from the parent run's base prompts for saturation checking.",
        },
    )
    print(
        f"Prepared {len(requests)} extra independent requests in {destination} "
        f"({len(pass_numbers)} per complete group: "
        f"{', '.join(str(n) for n in pass_numbers)}). No API calls made.",
        flush=True,
    )
    return 0


def is_direct_batch_run(run):
    try:
        manifest = read_json(Path(run) / "manifest.json")
    except (OSError, json.JSONDecodeError):
        return False
    return manifest.get("mode") in DIRECT_BATCH_MODES


def aggregate_parallel_results(run, folder):
    manifest = checked_manifest(run)
    batch_manifest = checked_manifest(folder)
    submission = read_json(folder / "submission.json")
    batch_summary = read_json(folder / "summary.json")
    if (
        submission["manifest_sha256"] != sha(folder / "manifest.json")
        or batch_summary["batch_id"] != submission["batch_id"]
    ):
        raise ValueError("Batch submission provenance changed")
    results = {r["custom_id"]: r for r in batch_summary["groups"]}
    if len(results) != len(batch_summary["groups"]) or set(results) != {
        r["custom_id"] for r in batch_manifest["groups"]
    }:
        raise ValueError("Result IDs do not match the five-request batch")
    grouped = defaultdict(list)
    for request in batch_manifest["groups"]:
        grouped[request["group_custom_id"]].append((request, results[request["custom_id"]]))
    summaries = []
    (run / "results").mkdir(exist_ok=True)
    for group in manifest["groups"]:
        entries = sorted(grouped[group["custom_id"]], key=lambda x: x[0]["pass_number"])
        if [r["pass_number"] for r, _ in entries] != list(range(1, REPEATS + 1)):
            raise ValueError("Each group must have exactly five result records")
        findings, keys, pairs, passes = [], set(), set(), []
        for request, result in entries:
            pass_info = {
                "pass": request["pass_number"],
                "custom_id": request["custom_id"],
                "status": result["status"],
            }
            if result["status"] == "succeeded":
                new_pairs, new_findings = set(), 0
                for finding in result["findings"]:
                    pair, key = tuple(sorted(finding["rule_ids"])), finding_key(finding)
                    if pair not in pairs:
                        new_pairs.add(pair)
                    if key not in keys:
                        findings.append(finding)
                        keys.add(key)
                        new_findings += 1
                pairs.update(new_pairs)
                pass_info.update(
                    returned_findings=len(result["findings"]),
                    new_pairs=len(new_pairs),
                    new_finding_variants=new_findings,
                )
                if result.get("format_repairs"):
                    pass_info["format_repairs"] = result["format_repairs"]
            else:
                pass_info["error"] = result["error"]
            passes.append(pass_info)
        failures = sum(p["status"] != "succeeded" for p in passes)
        summary = {
            "custom_id": group["custom_id"],
            "group_key": group["group_key"],
            "status": "completed_with_failures" if failures else "completed",
            "attempted_requests": REPEATS,
            "successful_requests": REPEATS - failures,
            "failed_requests": failures,
            "unique_pair_count": len(pairs),
            "findings": findings,
            "passes": passes,
        }
        atomic_json(run / "results" / f"{group['custom_id']}.json", summary)
        summaries.append(summary)
    aggregate = {
        "batch_id": submission["batch_id"],
        "complete": True,
        "groups": summaries,
        "requests_per_group": REPEATS,
        "failed_group_ids": [s["custom_id"] for s in summaries if s["failed_requests"]],
        "inconsistent_pairs_count": sum(s["unique_pair_count"] for s in summaries),
        "finding_variants_count": sum(len(s["findings"]) for s in summaries),
        "note": "Exactly five independent full-group requests were submitted together. No saturation rule, iterative scheduling, or prior findings in prompts. Failures do not cancel other requests. Findings are LLM claims, not solver proofs; five searches do not establish exhaustive coverage. Counts and deduplication are per group; textual variants may include paraphrases.",
    }
    atomic_json(run / "summary.json", aggregate)
    print(
        f"Collected all five requests per group: {aggregate['inconsistent_pairs_count']} inconsistent "
        f"pairs; {len(aggregate['failed_group_ids'])} groups with failed requests.",
        flush=True,
    )
    return 1 if aggregate["failed_group_ids"] else 0


def parallel_action(args, action):
    """One locked, resumable batch; never create another paid batch for the same run."""
    import fcntl

    run = Path(args.run)
    checked_manifest(run)
    with (run / "parallel.lock").open("a", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Another runner is already using this directory") from exc
        folder = prepare_parallel_batch(run)
        if action == "check-tokens":
            manifest = checked_manifest(folder)
            requests = [
                json.loads(line)
                for line in (folder / "requests.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            preflight_capacity(folder, manifest, requests, client())
            return 0
        if action == "submit":
            return submit_batch(argparse.Namespace(run=str(folder)))
        if getattr(args, "reprocess_only", False):
            if not (folder / "summary.json").exists():
                raise ValueError("No completed batch is available for offline reprocessing")
            reprocess_pass(folder)
            return aggregate_parallel_results(run, folder)
        if action == "run" and not (folder / "submission.json").exists():
            if (folder / "submission_started.json").exists():
                raise ValueError(
                    "Submission outcome unresolved; reconcile the provider batch ID before resuming. Do not blindly retry."
                )
            submit_batch(argparse.Namespace(run=str(folder)))
        if (folder / "summary.json").exists():
            reprocess_pass(folder)
        else:
            collect_batch(
                argparse.Namespace(
                    run=str(folder),
                    wait=action == "run" or getattr(args, "wait", False),
                    poll_seconds=args.poll_seconds,
                )
            )
        if not (folder / "summary.json").exists():
            return 0
        return aggregate_parallel_results(run, folder)


def submit(args):
    if is_direct_batch_run(args.run):
        return submit_batch(args)
    return parallel_action(args, "submit")


def collect(args):
    if is_direct_batch_run(args.run):
        return collect_batch(args)
    return parallel_action(args, "collect")


def run_parallel(args):
    if is_direct_batch_run(args.run):
        run = Path(args.run)
        if not (run / "submission.json").exists():
            submit_batch(argparse.Namespace(run=str(run)))
        return collect_batch(args)
    return parallel_action(args, "run")


def check_tokens(args):
    if is_direct_batch_run(args.run):
        run = Path(args.run)
        manifest = checked_manifest(run)
        requests = [
            json.loads(line)
            for line in (run / "requests.jsonl").read_text(encoding="utf-8").splitlines()
        ]
        preflight_capacity(run, manifest, requests, client())
        return 0
    return parallel_action(args, "check-tokens")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    prep = sub.add_parser(
        "prepare", help="Prepare complete group inputs offline; no API key needed"
    )
    prep.add_argument("spec", help="Spec directory or name")
    prep.add_argument(
        "--grouping-dir",
        help="Directory containing grouped_rules_by_authority and grouped_rules_partitioned "
        "(relative to the working directory; defaults to the spec directory). "
        "Source Markdown is still resolved from the spec directory.",
    )
    prep.add_argument("--model", required=True, help="Anthropic model ID")
    prep.add_argument(
        "--effort", choices=("low", "medium", "high", "xhigh", "max"),
        help="Reasoning effort (default: xhigh for claude-opus-5; API default for other models)",
    )
    prep.add_argument(
        "--max-tokens",
        type=int,
        default=DEFAULT_MAX_TOKENS,
        help="Output allowance, including thinking (default: 128000, Opus 5 maximum)",
    )
    prep.add_argument("--authorities", nargs="+", choices=AUTHORITIES, default=list(AUTHORITIES))
    prep.add_argument("--groups", nargs="+", help="Optional exact group keys such as root/unit:01")
    prep.add_argument(
        "--output", help="New run directory; existing directories are never overwritten"
    )
    extra = sub.add_parser(
        "prepare-extra-passes",
        help="Prepare additional independent pass numbers from an existing parent run",
    )
    extra.add_argument("run", help="Parent run prepared with five independent requests")
    extra.add_argument("--start-pass", type=int, default=REPEATS + 1)
    extra.add_argument("--count", type=int, default=2)
    extra.add_argument("--effort", choices=("low", "medium", "high", "xhigh", "max"))
    extra.add_argument("--output", help="New prepared batch directory")
    sub.add_parser(
        "submit", help="Capacity-check and submit all five requests per group together"
    ).add_argument("run")
    sub.add_parser(
        "check-tokens", help="Check native limits and input tokens; no response generation"
    ).add_argument("run")
    for command in ("run", "collect"):
        child = sub.add_parser(
            command,
            help="Submit and collect one five-request-per-group batch"
            if command == "run"
            else "Collect an already submitted batch",
        )
        child.add_argument("run")
        child.add_argument(
            "--reprocess-only",
            action="store_true",
            help="Rebuild results from saved raw responses offline",
        )
        child.add_argument(
            "--poll-seconds", type=int, choices=range(5, 61), default=30, metavar="5..60"
        )
        if command == "collect":
            child.add_argument("--wait", action="store_true")
    args = parser.parse_args()
    if args.command == "prepare" and (
        args.max_tokens <= 0 or len(set(args.authorities)) != len(args.authorities)
    ):
        parser.error("max-tokens must be positive and authorities must be unique")
    try:
        return {
            "prepare": prepare,
            "prepare-extra-passes": prepare_extra_passes,
            "submit": submit,
            "collect": collect,
            "run": run_parallel,
            "check-tokens": check_tokens,
        }[args.command](args)
    except (ValueError, OSError, KeyError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
