#!/usr/bin/env python3
"""Verify anonymized_annotated.md is anonymized.md with only ADDED tags.

Usage: check_annotation.py specs/<X>

A spec's anonymized_annotated.md is the anonymized spec with extra tags
added so that every rule/principle is annotated and every example block
is uniquely identifiable. The only things the annotated file may do are:

  (a) Insert focus-area markers of the form [^wxyz] (caret + exactly
      four word characters) after rule/principle clauses.
  (b) Tag every `**Example**` label as `**Example[^egNNN]**` where NNN
      is a zero-padded 3-digit counter.

The two tag families are regex-disjoint (4 word chars vs `eg` + 3
digits). No other text may change, no existing marker may be moved or
removed.

The check compares the two files **word by word**: each file is split
on whitespace into a list of words; tag insertion never adds whitespace,
so the two word lists line up one-to-one. For each aligned pair the
bare words (with all tags stripped) must be equal, and every marker
already on the anonymized word must still be present on the annotated
word.

Side integrity checks on the annotated file:
  - All rule-marker ids are unique.
  - All example-tag ids are unique.
  - The example-tag count equals the number of `**Example**` labels in
    `anonymized.md` (every example tagged exactly once).

Specs without an anonymized_annotated.md are skipped (not yet annotated).
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

RULE = re.compile(r"\[\^\w{4}\]")
EG = re.compile(r"\[\^eg\d{3}\]")
TAG = re.compile(r"\[\^(?:\w{4}|eg\d{3})\]")
EXAMPLE_LABEL = re.compile(r"\*\*Example\*\*")
TAGGED_EXAMPLE = re.compile(r"\*\*Example\[\^eg\d{3}\]\*\*")


def _rule_ids(text: str) -> list[str]:
    return [m for m in RULE.findall(text) if not EG.fullmatch(m)]


def bare(word: str) -> str:
    return TAG.sub("", word)


def keeps_originals(a: str, b: str) -> bool:
    """True if word b retains (a superset of) word a's tags."""
    bm = Counter(TAG.findall(b))
    return all(bm[m] >= c for m, c in Counter(TAG.findall(a)).items())


def check(spec_dir: Path) -> int:
    spec_name = spec_dir.name
    anon_path = spec_dir / "anonymized.md"
    annotated_path = spec_dir / "anonymized_annotated.md"

    if not annotated_path.exists():
        print(f"SKIP {spec_name}: no anonymized_annotated.md")
        return 0
    if not anon_path.exists():
        sys.exit(f"missing anonymized.md under {spec_dir}")

    anon_text = anon_path.read_text()
    annotated_text = annotated_path.read_text()

    A = anon_text.split()
    B = annotated_text.split()

    i = j = 0
    while i < len(A) and j < len(B):
        a, b = A[i], B[j]
        if a == b:
            i += 1
            j += 1
            continue
        if bare(a) == bare(b) and keeps_originals(a, b):
            i += 1
            j += 1
            continue
        if TAG.fullmatch(b):
            j += 1
            continue
        print(f"FAIL {spec_name}: word mismatch at anonymized #{i + 1} / annotated #{j + 1}")
        print(f"  anonymized:  {a!r}")
        print(f"  annotated:   {b!r}")
        return 1

    while j < len(B):
        if TAG.fullmatch(B[j]):
            j += 1
        else:
            print(f"FAIL {spec_name}: extra annotated word {B[j]!r} (not an added tag)")
            return 1

    if i < len(A):
        print(f"FAIL {spec_name}: annotated file is missing word {A[i]!r} and beyond")
        return 1

    rule_ids = _rule_ids(annotated_text)
    rule_dupes = sorted(m for m, c in Counter(rule_ids).items() if c > 1)
    if rule_dupes:
        print(f"FAIL {spec_name}: duplicate rule-marker ids: {', '.join(rule_dupes)}")
        return 1

    eg_ids = EG.findall(annotated_text)
    eg_dupes = sorted(m for m, c in Counter(eg_ids).items() if c > 1)
    if eg_dupes:
        print(f"FAIL {spec_name}: duplicate example tags: {', '.join(eg_dupes)}")
        return 1

    expected_examples = len(EXAMPLE_LABEL.findall(anon_text))
    tagged_examples = len(TAGGED_EXAMPLE.findall(annotated_text))
    bare_examples = len(EXAMPLE_LABEL.findall(annotated_text)) - tagged_examples
    if expected_examples and tagged_examples != expected_examples:
        print(
            f"FAIL {spec_name}: example-tag coverage: "
            f"{tagged_examples} tagged / {expected_examples} expected "
            f"({bare_examples} untagged **Example** label(s) remain)."
        )
        return 1

    before_rules = len(_rule_ids(anon_text))
    print(
        f"OK {spec_name}: rule markers {before_rules} -> {len(rule_ids)} "
        f"(+{len(rule_ids) - before_rules}); example tags 0 -> {len(eg_ids)} "
        f"(covers all {expected_examples} **Example** labels); "
        f"words match with only added tags."
    )
    return 0


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit("usage: check_annotation.py specs/<X>")
    spec_dir = Path(sys.argv[1]).resolve()
    if not spec_dir.is_dir():
        sys.exit(f"not a directory: {spec_dir}")
    return check(spec_dir)


if __name__ == "__main__":
    sys.exit(main())
