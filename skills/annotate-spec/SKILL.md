---
name: annotate-spec
description: Annotate a prepared anonymized model spec with stable markers for every assistant-directed rule and every example, verify additions-only integrity, and regenerate the resolved cross-reference copy. Use when creating or completing `anonymized_annotated.md`; do not use to edit spec prose or extract `rules.json`.
---

# Annotate a prepared spec

Produce these outputs for `specs/<X>/`:

- `anonymized_annotated.md`: `anonymized.md` with rule and example tags added.
- `anonymized_annotated_resolved.md`: a generated prompt-ready copy whose auto-labeled cross-references have visible titles.

The rule definition below is the operational definition used by this skill.

## Non-negotiable invariants

- Treat `raw.md` and `anonymized.md` as read-only inputs.
- `anonymized_annotated.md` may differ from `anonymized.md` only by inserted rule markers and example tags. Do not rewrite, remove, reorder, or reflow any source text.
- Preserve every existing marker exactly. Never move, remove, or renumber one, even when it does not fit the definition below; inherited markers record the publisher's choices.
- When completing an existing annotation, treat its established granularity as the default. Add a marker only for a clearly unrepresented policy unit; do not insert finer markers inside a coherently marked unit merely because its parts could be analyzed separately.
- Added rule markers use the reserved form `[^zNNN]`, where `NNN` is three digits. All rule-marker IDs must be unique.
- Example tags use `[^egNNN]`, where `NNN` is three digits. Every `**Example**` label must have exactly one unique example tag.
- Never hand-edit `anonymized_annotated_resolved.md`; regenerate it from the annotated source.
- Annotation does not assign authority. Record any new marker directly owned by an unlabelled heading chain so `extract-rules` can resolve its authority explicitly.

`scripts/check_annotation.py` enforces additions-only alignment, preservation of markers already present in `anonymized.md`, uniqueness of IDs within each tag family, and complete example tagging. It does **not** detect removal of a team marker from an earlier annotated copy, determine whether every rule has been found, or determine whether markers are divided into the right units. Preserve prior team markers by inspecting the before/after diff; perform the semantic checks using the definition below.

## What counts as a rule

> A **rule** is a coherent, assistant-directed policy statement that changes what the assistant is required, recommended, forbidden, or explicitly permitted to do in a given situation.

A rule is a unit of policy as the document presents it, not the smallest behavior that can be separated by logic. One rule may contain several closely related actions, alternatives, conditions, or constraints when they work together toward one policy outcome.

A passage is a rule only when it has all three properties:

1. **Normative effect:** it requires, recommends, prohibits, or explicitly permits behavior. Permissions and exceptions count when they change what the specification allows.
2. **Assistant-directed:** it governs the assistant, whether the assistant is named directly or is the understood subject of an imperative or passive construction.
3. **Operational content:** it identifies a behavior and the situation in which that behavior is governed. The situation may be unconditional. A reader must be able to judge whether an obligation, recommendation, or prohibition was followed, or identify the behavior that a permission makes allowable.

Words such as *must*, *should*, *never*, *avoid*, *may*, and *can*, and imperative phrasing, are clues rather than a definition:

- “The assistant may refuse” can grant permission and therefore be a rule.
- “The assistant may encounter errors” describes a possibility and is not a rule.
- “The assistant may only use X” is a prohibition on using anything else and is a rule.
- “We should improve the product” does not govern the assistant and is not a rule.

### Choose coherent policy units

Use the document's natural policy structure. A normative sentence or normative bullet is normally one rule, even when it contains several actions or alternatives. Split inside a sentence only when the text clearly presents separate policy statements.

A clause-level split is justified when at least one of these signals is present and the resulting clauses are each understandable as standalone instructions:

- the text changes to a new modal or imperative, especially with a different polarity or policy purpose;
- the clauses govern materially different situations and prescribe materially different responses;
- the prose explicitly enumerates separate policies rather than components of one response; or
- nearby inherited anchors consistently mark parallel items separately, and continuing that local pattern makes an otherwise unrepresented sibling citable.

Do **not** split merely because the assistant could technically perform one listed action while omitting another, or because alternative triggers can be imagined separately. Keep together:

- coordinated actions, steps, or constraints serving one policy outcome;
- lists of prohibited or recommended behaviors under one subject and modal;
- alternative triggers leading to the same governing behavior;
- a behavior with its conditions, qualifications, and `except ...` phrase; and
- examples, reasons, implementation details, or synonymous explanations of the same policy.

Separate sentences and standalone normative bullets remain separate rules by default. An explicit exception may also be a separate rule when it affirmatively permits or prescribes behavior rather than merely narrowing the preceding rule.

### Do not annotate

Exclude:

- `~~~xml ... ~~~` example blocks and prose that merely illustrates an already stated rule;
- `!!! meta "Commentary"` blocks;
- Markdown headings;
- pure definitions, facts, predictions, capability statements, and descriptions of possible situations;
- reasons or explanations that support a rule but do not independently govern behavior;
- restatements and cross-references that would count an existing rule twice; and
- statements governing Lumen Labs, developers, users, or other people rather than the assistant.

### Boundary-case codebook

Apply these decisions consistently:

- **Explicit permission:** “The assistant may still change its vocal tone...” changes what behavior is allowed, so it is a rule.
- **Descriptive possibility:** “The assistant may interact with multiple parties...” describes the setting; by itself, it does not govern behavior and is not a rule.
- **Coordinated safe response:** “provide a disclaimer,” “suggest safety precautions,” and “provide generic advice” are components of one response policy, so do not add a marker to each component.
- **Coordinated mental-health limits:** a single sentence listing unrealistic reassurance, normalization, diagnosis, and treatment advice is one policy against harmful clinical overreach. Even if each item could be violated separately, keep the list together under its shared subject, modal, and purpose.
- **Local publisher pattern:** in the information-hazard sentence, inherited anchors separately mark “illicit” and “could harm people.” Marking the parallel unrepresented “critical or large-scale harm” item separately follows that local citable-unit pattern; it is not a general instruction to split every trigger list.
- **Condition versus permission:** an `except ...` phrase that only narrows a rule stays with that rule, while a sentence beginning “However, the assistant may...” that affirmatively permits otherwise restricted behavior is a separate rule.
- **Normative umbrella versus introduction:** a standalone category-level sentence such as “Sensitive content may only be generated under specific circumstances” is a rule because it restricts assistant behavior. A section introduction that only describes desired character, motivation, or themes is not a rule when later passages supply the operative behavior.
- **Conflict-adjudication context:** a statement whose sole role is to say how conflicts among already identified rules are resolved is global audit context, not another inconsistency operand. Preserve inherited markers, but do not add a team marker solely for that role.

When a recurring boundary case is resolved, add its decision here so later annotation runs apply the same interpretation. For a one-off ambiguity, record the passage, decision, and reason in the completion report instead of silently relying on intuition.

## Marker placement and allocation

Place a rule marker at the end of the complete policy unit, before terminal punctuation and in the same style as surrounding inherited markers. Include governing conditions, exceptions, and qualifications. Exclude a trailing rationale or illustrative example when it can be separated without changing the policy's meaning.

For new team markers:

1. Inspect all existing `zNNN` IDs in `anonymized_annotated.md`, if the file exists.
2. Start at `z001` when none exist; otherwise continue after the highest existing number. Do not fill gaps or reuse an ID.
3. Assign new IDs in document order.

If `anonymized.md` itself contains an inherited `zNNN` ID, stop and report the namespace collision rather than guessing a replacement namespace.

For examples, walk the file from top to bottom. On a new annotation, the first `**Example**` becomes `**Example[^eg001]**`, followed by `eg002`, and so on. When completing an existing annotation, preserve existing tags and assign new tags after the highest existing example ID; never renumber earlier examples.

## Workflow

1. Confirm that `specs/<X>/anonymized.md` exists.
2. Read `anonymized.md` in full for document structure and context. If `anonymized_annotated.md` does not exist, create it as an exact copy. If it already exists, run the integrity checker before editing it and preserve its valid additions.
3. Tag every bare `**Example**` label.
4. Review the prose outside excluded regions in three passes:
   - find candidate rules by meaning, using modal words and imperatives only as search aids;
   - identify coherent policy units using the document's sentence, bullet, and inherited-anchor structure; and
   - review each section again for missed rules, false positives, and over-fragmented sentences.
5. Add markers only; do not alter the underlying text.
6. If an annotated file existed before this run, inspect its diff and confirm that no earlier team marker or example tag was removed, moved, or renumbered.
7. List new markers whose nearest authority-bearing ancestor is absent. Do not guess their authority or alter source headings; pass the list to `extract-rules` for individual resolution.
8. Run:

   ```bash
   python3 scripts/check_annotation.py specs/<X>
   ```

   Do not proceed until it prints `OK`.

9. Generate the prompt-ready copy:

   ```bash
   python3 scripts/resolve_crossrefs.py specs/<X>/anonymized_annotated.md
   ```

   The resolver replaces links such as `[?](#transformation_exception)` with the target heading title. It fails on duplicate heading anchors and references to missing anchors. Do not make these replacements in `anonymized_annotated.md`.

## Completion report

Before reporting completion, confirm that both commands printed `OK`. Report:

- rule-marker count before and after, including how many `zNNN` markers were added;
- example-tag count before and after;
- number of cross-references resolved;
- sections with the most new rule markers; and
- any boundary decisions, namespace problems, or markers needing authority resolution.
