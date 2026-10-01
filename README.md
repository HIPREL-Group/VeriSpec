# VeriSpec

VeriSpec detects internal inconsistencies in model specifications. Given a
specification in Markdown, it finds pairs of same-authority rules that
prescribe incompatible behavior in some concrete situation.

VeriSpec has three stages, preceded by anonymization:

0. **Anonymization.** Replace provider and model names with neutral
   placeholders so that the specification can be analyzed without
   triggering refusals.
1. **Context-aware rule extraction.** Mark every rule and example in the specification,
   then turn each marked rule into a structured record.
2. **Graph-based rule clustering.** Label rules with behavioral topics, connect
   related rules, and partition each authority level into analysis units.
3. **LLM-as-verifier detection.** For each analysis unit, ask the verifier to
   report rule pairs with a concrete witness situation, an argument that the
   two rules cannot both be satisfied, and an argument that the surrounding
   context does not resolve the conflict.

Stages that require judgment are written as agent skills (`skills/`), run
with a coding agent such as Claude Code. Deterministic steps and all integrity
checks are Python scripts (`scripts/`).

## Layout

```
skills/
  prepare-spec/        stage 0: anonymize raw.md
  annotate-spec/       stage 1a: mark every rule [^wxyz] and example [^egNNN]
  extract-rules/       stage 1b: build rules.json from the marked spec
  group-rules/         stage 2: topic taxonomy, rule graph, groups
scripts/
  check_anonymization.py      stage 0 check
  check_annotation.py         stage 1a check
  resolve_crossrefs.py        stage 1a: prompt-ready copy with resolved links
  rule_authority.py           shared: authority resolution for unlabelled rules
  build_rule_index.py         stage 1b: mechanical fields per marker
  build_rules.py              stage 1b: merge into rules.json
  check_rules.py              stage 1b check
  build_rule_graph.py         stage 2: mechanical edges and context
  prepare_grouping_jobs.py    stage 2: agent packets, semantic pass A
  prepare_dimension_jobs.py   stage 2: agent packets, semantic pass B
  build_groups.py             stage 2: merge into grouped_rules.json
  check_grouped.py            stage 2 check (graph and groups)
  check_taxonomy.py           stage 2 check (topic taxonomy)
  build_authority_views.py    stage 2: per-authority views of grouped_rules.json
  partition_authority_graphs.py  stage 2: per-authority analysis units
  detect_group_inconsistencies.py  stage 3: verifier batch runner
  prompts/detect_group_inconsistencies_{system,user}.md
  sample.env
examples/              example artifacts from our experiments
requirements.txt
```

## Setup

Python 3.9 or later.

```bash
pip install -r requirements.txt
cp scripts/sample.env scripts/.env   # then set ANTHROPIC_API_KEY
```

The API key is needed only for the stage 3 commands `check-tokens`,
`submit`, `collect`, and `run`. All other scripts run offline.

The skills in `skills/` are not loaded automatically. Place them where your
agent looks for skills. For Claude Code, that is `.claude/skills/` in this
directory:

```bash
mkdir -p .claude && cp -r skills .claude/skills
```

Run the agent from this directory, because the skills call scripts by
relative paths such as `scripts/check_rules.py`.

## Input

Place the specification under `specs/<X>/raw.md`, where `<X>` is a
lowercase, underscore-separated name. `raw.md` is never modified. All
commands below are run from this directory.

## Stage 0: Anonymization

Run the `prepare-spec` skill on `specs/<X>`. It writes
`specs/<X>/anonymized.md`, replacing provider and model identifiers with
`Lumen Labs`, `Lumo`, and `lumenlabs.example`. Then verify that every changed
line is a brand substitution:

```bash
python3 scripts/check_anonymization.py specs/<X>
```

## Stage 1: Context-aware rule extraction

**1a. Annotate.** Run the `annotate-spec` skill. It writes
`specs/<X>/anonymized_annotated.md`, a copy of `anonymized.md` whose only
changes are added `[^wxyz]` rule markers and `**Example[^egNNN]**` tags.
Verify, then generate the prompt-ready copy used by stages 2 and 3:

```bash
python3 scripts/check_annotation.py specs/<X>
python3 scripts/resolve_crossrefs.py specs/<X>/anonymized_annotated.md
# -> specs/<X>/anonymized_annotated_resolved.md
```

**1b. Extract.** Run the `extract-rules` skill. It runs
`build_rule_index.py`, fans out one subagent per section to fill in each
rule's `trigger`, `behavior`, `modality`, and `examples`, and merges the
results with `build_rules.py`. Rules under a heading with no declared
authority are resolved individually in `specs/<X>/authority_overrides.json`.
Verify:

```bash
python3 scripts/check_rules.py specs/<X>
```

Output: `specs/<X>/rules.json`, one record per rule marker.

## Stage 2: Graph-based rule clustering

Run the `group-rules` skill. It derives a two-level topic taxonomy
(`dimensions.json`, with provenance in `dimensions_derivation.json`), labels
every rule with one or more topics, and builds a typed relatedness graph. The
skill drives these scripts:

```bash
python3 scripts/build_rule_graph.py specs/<X>        # mechanical edges and context
python3 scripts/prepare_grouping_jobs.py specs/<X>   # packets for semantic pass A
python3 scripts/prepare_dimension_jobs.py specs/<X>  # packets for semantic pass B
python3 scripts/build_groups.py specs/<X>            # -> grouped_rules.json
python3 scripts/check_grouped.py specs/<X>
python3 scripts/check_taxonomy.py specs/<X>
```

Then derive the per-authority views that partitioning and detection read:

```bash
python3 scripts/build_authority_views.py specs/<X>
# -> specs/<X>/grouped_rules_semantic_only.json
# -> specs/<X>/grouped_rules_by_authority/<authority>.json
```

The semantic-only view removes every `sec:<path>` group and every
`same_section` edge. Each per-authority view is the subgraph of the
semantic-only view induced by one authority's rules, so it keeps only
same-authority edges.

Finally, partition each authority graph into analysis units:

```bash
python3 scripts/partition_authority_graphs.py <grouping_dir>
# -> <grouping_dir>/grouped_rules_partitioned/<authority>.json
```

Rules with several topics are split into one copy per topic. Each resulting
topic component becomes a unit. Units smaller than `--floor` (default 12) are
merged by affinity, up to `--cap` (default 28) rule copies.

`<grouping_dir>` is `specs/<X>`, or any directory holding
`grouped_rules_by_authority/`. Stage 3 reads both
`grouped_rules_by_authority/` and `grouped_rules_partitioned/` from it.

## Stage 3: LLM-as-verifier detection

Each Root, User, and Guideline analysis unit is one verifier request. System
and Developer each form a single authority-wide request. Every request is
sent five times independently. Each request contains the unit's rules and
their context: the full prose of the owning, referenced, and ancestor
sections; explicitly referenced rules; the shared authority and definition
sections; and full example bodies. A finding must name the two rule IDs and
give a witness, an unsatisfiability argument, and a context-resolution
argument.

```bash
# offline: build prompts, packets, and requests.jsonl (no API key needed)
python3 scripts/detect_group_inconsistencies.py prepare specs/<X> \
    --grouping-dir <grouping_dir> --model claude-opus-5 --effort high

# optional: check context and output limits without generating responses
python3 scripts/detect_group_inconsistencies.py check-tokens <run_dir>

# paid: submit all requests as one batch, wait, and collect (resumable)
python3 scripts/detect_group_inconsistencies.py run <run_dir>
```

`prepare` writes a new run directory under
`analysis/<X>/group_inconsistencies/<timestamp>-<id>/` (or `--output`) and prints
its path. Existing directories are never overwritten. `submit` and `collect --wait`
split `run` into separate steps. `collect --reprocess-only` rebuilds results
from saved raw responses without calling the API. Per-group findings are
written to `results/` and aggregated in `summary.json`. The aggregated rule
pairs are the candidate inconsistencies passed to manual review.
