#!/usr/bin/env python3
"""Build .rule_graph.json: mechanical relatedness edges + mechanical context.

Stage 2 (rule grouping) reads the resolved specification
``specs/<X>/anonymized_annotated_resolved.md`` -- the canonical text for this
stage, in which cross-reference titles are resolved -- together with
``rules.json`` and ``authority_overrides.json``, and emits the deterministic
half of the relatedness graph defined by the ``group-rules`` skill.

Per rule it emits:

  mechanical edges
    same_sentence    markers sharing one source sentence
    same_section     rules owned by the same innermost section
    shares_example   rules whose ``examples`` lists intersect
    cross_reference  a ``[...](#anchor)`` occurring in the rule's own sentence
                     or in its owning section, resolved to the rules directly
                     owned by the referenced section, with the citing sentence
                     captured verbatim so that subtype classification needs no
                     further context

  mechanical context
    stem / framing        introductory sentence and preceding paragraph for
                          list-item rules (framing frequently pre-acknowledges
                          a tradeoff and is absent from rules.json ``text``)
    ancestor_guards       preamble prose of every ancestor section
    commentary            ``!!! meta "Commentary"`` blocks in scope
    examples              example tags with GOOD/OK/BAD[#anchor] verdicts
    section_references    outgoing anchors that resolve to no directly-owned
                          rule (container references, retained as context)
    authority_provenance  section header, or the override reason

Parsing is code-fence aware (heading-like lines occur inside example blocks)
and all output is sorted, so repeated executions are byte-identical.

Usage: build_rule_graph.py specs/<X> [--max-quote-words N]

Writes specs/<X>/.rule_graph.json.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

RESOLVED = "anonymized_annotated_resolved.md"
OUT_NAME = ".rule_graph.json"

RULE_MARKER = re.compile(r"\[\^(\w{4})\]")  # 4-char ids; eg tags are 5 chars
EG_MARKER = re.compile(r"\[\^(eg\d{3})\]")
HEADER = re.compile(r"^(#{1,6})\s+(.*?)\s*(?:\{(.+?)\})?\s*$")
ATTR_ANCHOR = re.compile(r"#([\w_]+)")
ATTR_KV = re.compile(r"(\w+)=(\S+)")
MD_LINK = re.compile(r"\[[^\]]*\]\(#([\w-]+)\)")
COMMENTARY = re.compile(r'^\s*!!!\s+meta\s+"Commentary"')
EXAMPLE_HEAD = re.compile(r"^\*\*Example\[\^(eg\d{3})\]\*\*:?\s*(.*)$")
VERDICT = re.compile(r"<!--\s*(GOOD|OK|BAD)(?:\[#([\w_]+)\])?\s*:?\s*(.*?)\s*-->")
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")

# Sentence boundary: a terminal mark followed by whitespace and an opening
# character, excluding common abbreviations. Each lookbehind is fixed width,
# as Python's re module requires.
_ABBR = (
    r"(?<!\be\.g\.)(?<!\bi\.e\.)(?<!\betc\.)(?<!\bvs\.)(?<!\bcf\.)(?<!\bal\.)"
    r"(?<!\bDr\.)(?<!\bMr\.)(?<!\bMs\.)(?<!\bSt\.)(?<!\bNo\.)(?<!\bU\.S\.)(?<!\bapprox\.)"
)
SENT_BOUNDARY = re.compile(_ABBR + r"(?<=[.!?])[\"'\)\]]*\s+(?=[A-Z\(\[\"'*`])")


# ---------------------------------------------------------------------------
# Text utilities
# ---------------------------------------------------------------------------


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")


def parse_attrs(block: str | None) -> tuple[str | None, dict[str, str]]:
    anchor = None
    kvs: dict[str, str] = {}
    if not block:
        return anchor, kvs
    m = ATTR_ANCHOR.search(block)
    if m:
        anchor = m.group(1)
    for k, v in ATTR_KV.findall(block):
        kvs[k] = v.rstrip("}")
    return anchor, kvs


def sentence_spans(text: str) -> list[tuple[int, int]]:
    """Return (start, end) spans of the sentences of a single line."""
    spans: list[tuple[int, int]] = []
    start = 0
    for m in SENT_BOUNDARY.finditer(text):
        spans.append((start, m.end()))
        start = m.end()
    spans.append((start, len(text)))
    return [(a, b) for a, b in spans if text[a:b].strip()]


def sentence_at(text: str, pos: int) -> tuple[int, str]:
    """Return (sentence index, sentence text) containing character ``pos``."""
    for idx, (a, b) in enumerate(sentence_spans(text)):
        if a <= pos < b:
            return idx, text[a:b].strip()
    return 0, text.strip()


def clip(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]) + " [...]"


# ---------------------------------------------------------------------------
# Document model
# ---------------------------------------------------------------------------


class Document:
    """Fence-aware section/marker model of the resolved specification."""

    def __init__(self, lines: list[str]):
        self.lines = lines
        self.fenced = self._scan_fences(lines)
        self.sections: list[dict] = []
        self.line_section: list[int | None] = [None] * (len(lines) + 1)
        self._scan_sections()
        self.blocks: list[str] = []
        self.block_of: dict[int, tuple[int, int]] = {}
        self._scan_blocks()

    def _scan_blocks(self) -> None:
        """Join wrapped continuation lines into logical blocks.

        The specification wraps some paragraphs across source lines, so a
        sentence -- and therefore the ``same_sentence`` relation -- cannot be
        recovered from a single line. A block starts at a blank line, header,
        fence, or list marker, and absorbs subsequent continuation lines.
        """
        cur: list[str] = []
        cur_lines: list[int] = []

        def flush() -> None:
            if not cur:
                return
            text = " ".join(cur)
            idx = len(self.blocks)
            off = 0
            for ln, piece in zip(cur_lines, cur):
                self.block_of[ln] = (idx, off)
                off += len(piece) + 1
            self.blocks.append(text)
            cur.clear()
            cur_lines.clear()

        for i, raw in enumerate(self.lines, 1):
            if self.fenced[i] or not raw.strip() or HEADER.match(raw) or COMMENTARY.match(raw):
                flush()
                continue
            if LIST_ITEM.match(raw):
                flush()
            cur.append(raw.strip())
            cur_lines.append(i)
        flush()

    def block_sentence(self, line: int, col: int) -> tuple[int, int, str]:
        """Return (block index, sentence index, sentence text) for a position."""
        entry = self.block_of.get(line)
        if entry is None:
            idx, text = -line, self.lines[line - 1]
            s_idx, s_text = sentence_at(text, col)
            return idx, s_idx, s_text
        idx, off = entry
        text = self.blocks[idx]
        s_idx, s_text = sentence_at(text, off + col)
        return idx, s_idx, s_text

    @staticmethod
    def _scan_fences(lines: list[str]) -> list[bool]:
        """True for lines inside a ``~~~`` or top-level ``` fence."""
        fenced = [False] * (len(lines) + 1)
        in_tilde = False
        in_tick = False
        for i, line in enumerate(lines, 1):
            s = line.lstrip()
            if s.startswith("~~~"):
                fenced[i] = True
                in_tilde = not in_tilde
                continue
            if not in_tilde and s.startswith("```"):
                fenced[i] = True
                in_tick = not in_tick
                continue
            fenced[i] = in_tilde or in_tick
        return fenced

    def _scan_sections(self) -> None:
        stack: list[int] = []  # indices into self.sections
        for i, line in enumerate(self.lines, 1):
            if self.fenced[i]:
                continue
            hm = HEADER.match(line)
            if not hm:
                continue
            level = len(hm.group(1))
            title = hm.group(2).strip()
            anchor, kvs = parse_attrs(hm.group(3))
            while stack and self.sections[stack[-1]]["level"] >= level:
                closed = stack.pop()
                self.sections[closed]["end_line"] = i - 1
            slug = anchor or slugify(title)
            parent = stack[-1] if stack else None
            authority = kvs.get("authority")
            tags = kvs.get("tags")
            if parent is not None:
                if authority is None:
                    authority = self.sections[parent]["authority"]
                if tags is None:
                    tags = self.sections[parent]["tags"]
            path = (self.sections[parent]["path"] if parent is not None else []) + [slug]
            self.sections.append(
                {
                    "index": len(self.sections),
                    "level": level,
                    "slug": slug,
                    "title": title,
                    "path": path,
                    "authority": authority,
                    "tags": tags,
                    "parent": parent,
                    "header_line": i,
                    "start_line": i,
                    "end_line": len(self.lines),
                    "child_start": None,
                }
            )
            stack.append(len(self.sections) - 1)
        while stack:
            self.sections[stack.pop()]["end_line"] = len(self.lines)

        for sec in self.sections:
            if sec["parent"] is not None:
                parent = self.sections[sec["parent"]]
                if parent["child_start"] is None:
                    parent["child_start"] = sec["header_line"]

        # innermost section owning each line
        for sec in self.sections:
            for ln in range(sec["header_line"], sec["end_line"] + 1):
                cur = self.line_section[ln]
                if cur is None or sec["level"] > self.sections[cur]["level"]:
                    self.line_section[ln] = sec["index"]

    def by_slug(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for sec in self.sections:
            out.setdefault(sec["slug"], sec["index"])
        return out

    def preamble_lines(self, idx: int) -> range:
        """Lines of a section before its first child section."""
        sec = self.sections[idx]
        stop = sec["child_start"] - 1 if sec["child_start"] else sec["end_line"]
        return range(sec["header_line"] + 1, stop + 1)

    def paragraphs(self, line_range, *, skip_commentary: bool = True) -> list[str]:
        """Contiguous non-fenced prose blocks within ``line_range``."""
        out: list[str] = []
        buf: list[str] = []
        in_commentary = False
        for ln in line_range:
            if ln < 1 or ln > len(self.lines):
                continue
            raw = self.lines[ln - 1]
            if self.fenced[ln]:
                continue
            if COMMENTARY.match(raw):
                in_commentary = True
                if buf:
                    out.append(" ".join(buf))
                    buf = []
                continue
            if in_commentary:
                if raw.strip() and raw.startswith("    "):
                    continue
                in_commentary = False
            if not raw.strip():
                if buf:
                    out.append(" ".join(buf))
                    buf = []
                continue
            if HEADER.match(raw):
                if buf:
                    out.append(" ".join(buf))
                    buf = []
                continue
            buf.append(raw.strip())
        if buf:
            out.append(" ".join(buf))
        return [p for p in out if p]

    def commentary_blocks(self, line_range) -> list[dict]:
        out: list[dict] = []
        collecting = False
        buf: list[str] = []
        start = 0
        for ln in line_range:
            if ln < 1 or ln > len(self.lines):
                continue
            raw = self.lines[ln - 1]
            if self.fenced[ln]:
                continue
            if COMMENTARY.match(raw):
                if collecting and buf:
                    out.append({"line": start, "text": " ".join(buf)})
                collecting, buf, start = True, [], ln
                continue
            if collecting:
                if raw.strip() and raw.startswith("    "):
                    buf.append(raw.strip())
                elif raw.strip():
                    out.append({"line": start, "text": " ".join(buf)})
                    collecting, buf = False, []
        if collecting and buf:
            out.append({"line": start, "text": " ".join(buf)})
        return out

    def examples(self, line_range) -> list[dict]:
        """Example blocks with their verdict annotations."""
        out: list[dict] = []
        current: dict | None = None
        for ln in line_range:
            if ln < 1 or ln > len(self.lines):
                continue
            raw = self.lines[ln - 1]
            em = EXAMPLE_HEAD.match(raw.strip())
            if em and not self.fenced[ln]:
                if current:
                    out.append(current)
                current = {
                    "id": em.group(1),
                    "line": ln,
                    "title": em.group(2).strip(),
                    "verdicts": [],
                }
                continue
            if current is not None:
                for vm in VERDICT.finditer(raw):
                    verdict, cause, note = vm.group(1), vm.group(2), vm.group(3)
                    current["verdicts"].append(
                        {
                            "verdict": verdict,
                            "cause_anchor": cause,
                            "note": note.strip(" :-") or None,
                        }
                    )
        if current:
            out.append(current)
        return out


# ---------------------------------------------------------------------------
# Graph construction
# ---------------------------------------------------------------------------


def build(spec_dir: Path, max_quote_words: int) -> int:
    resolved_path = spec_dir / RESOLVED
    rules_path = spec_dir / "rules.json"
    for p in (resolved_path, rules_path):
        if not p.exists():
            sys.exit(f"missing {p}")

    lines = resolved_path.read_text(encoding="utf-8").splitlines()
    doc = Document(lines)
    rules = json.loads(rules_path.read_text(encoding="utf-8"))["rules"]
    by_id = {r["id"]: r for r in rules}

    try:
        from rule_authority import load_authority_overrides

        _ = load_authority_overrides(spec_dir)  # validation side effect
    except Exception as exc:  # pragma: no cover - defensive
        sys.exit(f"invalid authority overrides: {exc}")
    overrides_path = spec_dir / "authority_overrides.json"
    override_entries: dict[str, dict] = {}
    if overrides_path.exists():
        override_entries = json.loads(overrides_path.read_text(encoding="utf-8"))["overrides"]

    # --- locate every marker in the resolved text -------------------------
    marker_pos: dict[str, tuple[int, int]] = {}
    for i, line in enumerate(lines, 1):
        if doc.fenced[i]:
            continue
        for m in RULE_MARKER.finditer(line):
            rid = m.group(1)
            if rid.startswith("eg"):
                continue
            if rid in marker_pos:
                sys.exit(f"duplicate marker {rid} at line {i}")
            marker_pos[rid] = (i, m.start())

    missing = sorted(set(by_id) - set(marker_pos))
    extra = sorted(set(marker_pos) - set(by_id))
    if missing or extra:
        sys.exit(f"marker/inventory mismatch: missing={missing} extra={extra}")

    # --- sentence assignment ---------------------------------------------
    rule_sentence: dict[str, dict] = {}
    for rid, (ln, col) in marker_pos.items():
        block, idx, text = doc.block_sentence(ln, col)
        rule_sentence[rid] = {
            "line": ln,
            "block": block,
            "sentence_index": idx,
            "text": text,
        }

    edges: dict[str, dict[tuple, dict]] = {rid: {} for rid in by_id}

    def add_edge(src: str, dst: str, relation: str, **extra_fields) -> None:
        if src == dst or dst not in by_id:
            return
        key = (dst, relation, extra_fields.get("scope"), extra_fields.get("via"))
        if key in edges[src]:
            return
        entry = {"id": dst, "relation": relation, "source": "mechanical"}
        entry.update({k: v for k, v in extra_fields.items() if v is not None})
        edges[src][key] = entry

    # same_sentence
    by_sentence: dict[tuple[int, int], list[str]] = {}
    for rid, s in rule_sentence.items():
        by_sentence.setdefault((s["block"], s["sentence_index"]), []).append(rid)
    for members in by_sentence.values():
        for a in members:
            for b in members:
                add_edge(a, b, "same_sentence")

    # same_section
    by_section: dict[str, list[str]] = {}
    for r in rules:
        by_section.setdefault("/".join(r["sections"]), []).append(r["id"])
    for members in by_section.values():
        for a in members:
            for b in members:
                add_edge(a, b, "same_section")

    # shares_example
    by_example: dict[str, list[str]] = {}
    for r in rules:
        for eg in r.get("examples") or []:
            by_example.setdefault(eg, []).append(r["id"])
    for eg, members in by_example.items():
        for a in members:
            for b in members:
                add_edge(a, b, "shares_example", via=eg)

    # cross_reference
    slug_index = doc.by_slug()
    direct_owners: dict[str, list[str]] = {}
    for r in rules:
        if r["sections"]:
            direct_owners.setdefault(r["sections"][-1], []).append(r["id"])

    section_refs: dict[str, list[dict]] = {rid: [] for rid in by_id}
    xref_links = 0
    for ln, raw in enumerate(lines, 1):
        if doc.fenced[ln]:
            continue
        links = list(MD_LINK.finditer(raw))
        if not links:
            continue
        sec_idx = doc.line_section[ln]
        if sec_idx is None:
            continue
        sec_path = "/".join(doc.sections[sec_idx]["path"])
        owner_rules = by_section.get(sec_path, [])
        for lm in links:
            anchor = lm.group(1)
            if anchor not in slug_index:
                continue
            xref_links += 1
            s_block, s_idx, s_text = doc.block_sentence(ln, lm.start())
            sentence_rules = [
                rid
                for rid, s in rule_sentence.items()
                if s["block"] == s_block and s["sentence_index"] == s_idx
            ]
            scope = "sentence" if sentence_rules else "section"
            targets = sorted(direct_owners.get(anchor, []))
            # A citation is a rule-level relation only when the rule's own
            # sentence makes it. A citation elsewhere in the section, or one
            # naming a container that owns no rule directly, is section-level
            # context and is retained as such rather than fanned out over the
            # section's members.
            if scope == "section" or not targets:
                for rid in sentence_rules or owner_rules:
                    section_refs[rid].append(
                        {
                            "anchor": anchor,
                            "scope": scope,
                            "citing_sentence": clip(s_text, max_quote_words),
                            "line": ln,
                        }
                    )
                continue
            for src in sentence_rules:
                for dst in targets:
                    add_edge(
                        src,
                        dst,
                        "cross_reference",
                        scope=scope,
                        citing_sentence=clip(s_text, max_quote_words),
                        anchor=anchor,
                    )

    # --- mechanical context ----------------------------------------------
    context: dict[str, dict] = {}
    for r in rules:
        rid = r["id"]
        ln = marker_pos[rid][0]
        sec_idx = doc.line_section[ln]
        sec = doc.sections[sec_idx] if sec_idx is not None else None

        # stem / framing for list-item rules
        stem = framing = None
        if LIST_ITEM.match(lines[ln - 1]):
            back = ln - 1
            collected: list[str] = []
            while back >= 1 and len(collected) < 4:
                raw = lines[back - 1]
                if doc.fenced[back] or HEADER.match(raw):
                    break
                if not raw.strip():
                    back -= 1
                    continue
                if LIST_ITEM.match(raw):
                    back -= 1
                    continue
                block: list[str] = []
                while back >= 1 and lines[back - 1].strip() and not doc.fenced[back]:
                    if HEADER.match(lines[back - 1]) or LIST_ITEM.match(lines[back - 1]):
                        break
                    block.insert(0, lines[back - 1].strip())
                    back -= 1
                if block:
                    collected.append(" ".join(block))
                else:
                    break
            if collected:
                stem = clip(collected[0], max_quote_words)
            # Framing is the nearest preceding block that is not itself a list
            # lead-in, so that a sibling lead-in ("Favoring longer responses:")
            # does not displace the sentence that frames the whole tradeoff.
            for block in collected[1:]:
                if not block.rstrip().endswith(":"):
                    framing = clip(block, max_quote_words)
                    break
            if framing is None and len(collected) > 1:
                framing = clip(collected[1], max_quote_words)

        guards = []
        if sec is not None:
            ancestors = []
            cur = sec["parent"]
            while cur is not None:
                ancestors.append(cur)
                cur = doc.sections[cur]["parent"]
            for anc_idx in reversed(ancestors):
                anc = doc.sections[anc_idx]
                for para in doc.paragraphs(doc.preamble_lines(anc_idx))[:3]:
                    guards.append(
                        {"where": f"#{anc['slug']}", "quote": clip(para, max_quote_words)}
                    )

        own_range = range(sec["header_line"], sec["end_line"] + 1) if sec else range(0)
        commentary = [
            {
                "where": f"#{sec['slug']}",
                "line": c["line"],
                "quote": clip(c["text"], max_quote_words),
            }
            for c in doc.commentary_blocks(own_range)
        ]
        examples = doc.examples(own_range)

        context[rid] = {
            "line": ln,
            "sentence": clip(rule_sentence[rid]["text"], max_quote_words * 2),
            "is_list_item": bool(LIST_ITEM.match(lines[ln - 1])),
            "stem": stem,
            "framing": framing,
            "section_anchor": f"#{sec['slug']}" if sec else None,
            "section_title": sec["title"] if sec else None,
            "ancestor_guards": guards,
            "commentary": commentary,
            "section_examples": examples,
            "section_references": sorted(section_refs[rid], key=lambda d: (d["line"], d["anchor"])),
            "authority_provenance": (
                {"override_reason": override_entries[rid]["reason"]}
                if rid in override_entries
                else "section_header"
            ),
        }

    # --- emit --------------------------------------------------------------
    out_rules = []
    for r in sorted(rules, key=lambda x: x["id"]):
        rid = r["id"]
        ordered = sorted(
            edges[rid].values(),
            key=lambda e: (e["relation"], e["id"], e.get("scope") or "", e.get("via") or ""),
        )
        out_rules.append({"id": rid, "edges": ordered, "context": context[rid]})

    counts: dict[str, int] = {}
    for rid in edges:
        for e in edges[rid].values():
            counts[e["relation"]] = counts.get(e["relation"], 0) + 1

    out = {
        "spec": spec_dir.name,
        "source": RESOLVED,
        "config": {
            "max_quote_words": max_quote_words,
        },
        "stats": {
            "rules": len(rules),
            "sections": len(doc.sections),
            "xref_links": xref_links,
            "edges_by_relation": dict(sorted(counts.items())),
        },
        "rules": out_rules,
    }
    out_path = spec_dir / OUT_NAME
    out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False, sort_keys=False))

    print(
        f"OK {spec_dir.name}: {len(rules)} rules, {len(doc.sections)} sections, "
        f"{sum(counts.values())} directed mechanical edges "
        f"({', '.join(f'{k}={v}' for k, v in sorted(counts.items()))}), "
        f"{xref_links} anchor links -> {out_path}"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the mechanical rule-relatedness graph.")
    ap.add_argument("spec_dir", type=Path, help="specs/<X>")
    ap.add_argument("--max-quote-words", type=int, default=40)
    args = ap.parse_args()
    spec_dir = args.spec_dir.resolve()
    if not spec_dir.is_dir():
        sys.exit(f"not a directory: {spec_dir}")
    return build(spec_dir, args.max_quote_words)


if __name__ == "__main__":
    sys.exit(main())
