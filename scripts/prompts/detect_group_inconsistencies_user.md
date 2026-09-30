# Inconsistency analysis

Your task is to identify inconsistencies between rules in this group. An inconsistency occurs
when both rules apply to the same situation but their prescribed behaviors cannot
be satisfied simultaneously, even after accounting for the context.

Before analyzing the rules, review the supplied definitions, authority provisions,
and relevant examples. Look for genuine incompatibilities, not gaps or ambiguities
alone.

# Context

The following passages are the deduplicated union of the rules' contexts. Each
heading path applies to the passages beneath it until the next heading path;
these paths preserve source hierarchy and authority attributes. ctx labels identify
passages referenced by the rules. Commentary is labeled separately. Rules that
appear here but are absent from the Rules section may help interpret a candidate,
but must not be reported as inconsistency endpoints.

${context}

# Examples

Each complete example appears once under its eg label. The examples field of each
rule references these labels. Use the conversations and their GOOD/OK/BAD annotations
to understand the intended behavior and any contextual resolution.

${examples}

# Rules

Authority for all rules below: ${authority}.

Each rule is headed by its ID and explicitly lists modality, trigger, and behavior,
matching the formalization below. modality records must or should; interpret its
force using the source and the modality guidance below.
Source references locate the original wording, which governs if a summary differs.
Each rule's context C_i combines the common context below, its Source and Context
references, and its Examples. Omitted fields add no references or scope hints.
System flags and extracted scope hints, when present, help identify applicability;
verify them against the source. Analyze each original rule once.

Common context: ${common_context_refs}

${rules}

# Formalization

For distinct rules i and j in this group, let s be a concrete, feasible situation
and C_ij = C_i union C_j their combined context.

INCONSISTENCY(i, j) := exists s.
    trigger_i(s, C_ij) AND trigger_j(s, C_ij) AND
    UNSAT(behavior_i(s, C_ij), behavior_j(s, C_ij))

trigger_i means that rule i applies in s. behavior_i means its effective behavioral
requirements after interpreting authority, modality, scope, precedence, and
exceptions. UNSAT means no permitted response or course of action satisfies both
rules' effective requirements.

## Anti-patterns

Do not report a candidate when:

1. The rules apply to different situations, or the witness does not meet both triggers.
2. Context already resolves it through an authority provision, modality, exception,
   general principle, or worked example. Interpret "must" and "should" as the spec
   defines them, rather than assuming a modality difference always settles the case.
3. The evidence shows only one violating response or apparent tension. An inconsistency
   requires that no jointly compliant behavior exists, not merely that one is hard
   to find.

# Output format

Return a JSON array, possibly []. Each finding must contain exactly four fields:

```json
[
  {
    "rule_ids": ["id_i", "id_j"],
    "witness": "A concrete situation s, including why both rules apply.",
    "unsat_reason": "What each rule requires in s and why no permitted behavior satisfies both.",
    "context_resolution": "Why authority, modality, exceptions, and other relevant context do not resolve the inconsistency."
  }
]
```

Use two distinct original rule IDs. Give concise, checkable evidence in the three
explanation fields, citing relevant rule markers, ctx passages, or eg examples.
Do not add scores, summaries, unknown classifications, or verdicts for consistent
pairs. Return ONLY the JSON array. An empty array means no supported inconsistency was
found, not a proof of consistency.

# Independent whole-group search

Analyze the entire group independently, using all the rules, context, and examples above.
Do not split the group or restrict the search to a subset of rules or pairs.

This is a fresh search. No results from other passes are provided; do not assume
any pair has already been checked or any inconsistency has already been found.

Reason as a verifier and return only supported findings in the same four-field JSON
array format. Return [] if you find no supported inconsistencies. Do not claim exhaustive
coverage or consistency: a search can miss inconsistent pairs.
