---
name: extract-rules
description: Extract and validate `rules.json` from an annotated model spec, including semantic rule fields and explicit resolution of markers under unlabelled authority containers. Use after `annotate-spec` changes rule markers or when the structured inventory may be stale.
---

# extract-rules

Push-button: produce `specs/<X>/rules.json` from
`specs/<X>/anonymized_annotated.md`. One record per rule marker
`[^wxyz]`, with mechanical fields filled deterministically and the
semantic fields authored by per-section subagents.

An optional committed `specs/<X>/authority_overrides.json` resolves the
authority of individual markers that are directly owned by unlabelled
container sections. It is part of the mechanical input to extraction.

## Output schema (`specs/<X>/rules.json`)

```json
{
  "spec": "<X>",
  "rules": [
    {
      "id": "8ep1",
      "authority": "root",
      "system_flags": [],
      "sections": ["the_chain_of_command", "follow_all_applicable_instructions"],
      "text": "<source line containing the marker, verbatim>",
      "trigger": "<brief NL situation>",
      "behavior": "<brief NL prescription; polarity (do/don't) lives here>",
      "modality": "must",
      "examples": ["eg003"]
    }
  ]
}
```

`modality ∈ {must, should}`. Hard obligations and prohibitions →
`must`; overridable defaults and permissions → `should`. `examples` is
the list of `eg` tags whose `**Example[^egNNN]**` blocks illustrate
this rule (`[]` if none).

## Resolve authority 

The indexer first inherits `authority=...` from the nearest labelled ancestor.
An unlabelled container may contain children with different authorities, so do
not globally interpret missing authority as root.

If indexing reports `authority=null`, inspect each affected rule individually:

- use the rule's wording, the authority discussion in the spec, and the nearest
  operative subsections;
- distinguish a container-wide rule from a summary of one immediately following
  policy;
- record the decision and a non-empty reason in
  `specs/<X>/authority_overrides.json`; and
- rerun the indexer so the resolution is included in mechanical output.

Use this shape:

```json
{
  "overrides": {
    "wxyz": {
      "authority": "root",
      "reason": "Concise source-based justification."
    }
  }
}
```

The helper rejects unknown marker IDs, invalid authorities, empty reasons, and
overrides of markers that already inherit an explicit authority. Do not proceed
to rule grouping while any rule remains `authority=null`, because later stages
group and analyze rules by authority.

## Procedure

1. **Index.** Run

   ```
   python3 scripts/build_rule_index.py specs/<X>
   ```

   It writes `specs/<X>/.rule_index.json` with the mechanical fields
   for every marker plus `jobs[]` — one entry per innermost section
   that owns ≥1 marker. Resolve and re-index any `authority=null`
   warning before continuing.

2. **Fan out.** Run one subagent per job, in parallel. Each subagent:

   - is given its `section_path`, its `marker_ids`, and the slice of
     `specs/<X>/anonymized_annotated.md` covering that section (its
     header through the next sibling/parent header). Rule markers and
     `eg` tags are visible inline in that slice.
   - returns a JSON fragment listing one record per owned id with
     **only the four semantic fields**: `trigger`, `behavior`,
     `modality`, `examples`. Use structured output with a fixed
     schema where the agent supports it, so coverage is enforced.

   Fragments are written to
   `specs/<X>/.rules_fragments/<sanitized_section_path>.json`.

3. **Merge.** Run

   ```
   python3 scripts/build_rules.py specs/<X>
   ```

   It joins the mechanical index and the fragments into
   `specs/<X>/rules.json` and validates the result.

## Subagent prompt (template)

> You are extracting structured fields for rules in section
> `<section_path>` of an anonymized model spec.
>
> You will receive a verbatim slice of the spec for that section (rule
> markers `[^wxyz]` and example tags `[^egNNN]` are visible inline).
>
> Return a JSON object `{ "records": [ { id, trigger, behavior,
> modality, examples }, ... ] }` covering **exactly** these marker ids:
> `<marker_ids>` — no more, no less.
>
> For each marker, write a brief natural-language `trigger` (≤ 20
> words; the situation that activates the rule) and `behavior`
> (≤ 25 words; what the assistant should/shouldn't do — polarity stays
> in this text, not in modality). Pick `modality = "must"` for hard
> obligations and prohibitions, `"should"` for overridable defaults
> and permissions. List the `eg` tags of the example block(s) that
> illustrate this specific rule (`[]` if none).

## Self-check

- `build_rule_index.py` completes without an `authority=null` warning.
- `build_rules.py` reports the same record count as the indexer's marker count.
- `python3 scripts/check_rules.py specs/<X>` returns `OK`.
- `python3 scripts/check_annotation.py specs/<X>` still returns `OK`.

Report counts (markers, records, jobs, and maximum job size), the authority
resolution decisions applied, and confirmation that no rule remains with null authority.
