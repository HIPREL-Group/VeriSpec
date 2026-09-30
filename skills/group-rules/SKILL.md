---
name: group-rules
description: Perform rule grouping, the second stage of the three-stage analysis pipeline (rule extraction, rule grouping, rule analysis). Constructs a typed rule-relatedness graph over specs/<X>/rules.json; augments every rule with a `neighbor` field (typed related rules, including explicit semantic-adjacency edges and textually grounded thematic edges), a `groups` field, and a `related_context` field (framing text, ancestor constraints, definitions, conflict-resolution devices, examples with verdict semantics, commentary); derives a two-level behavioral-dimension taxonomy through a protocolized multi-coder procedure with independent replication, definition-level reconciliation, reliability-gated piloting, held-out structural validation, and granularity-driven hierarchical refinement of oversized axes; and emits semantic groups at a fine (primary) and coarse (continuity) tier with structural groups (section, secondary). Stage 2 asserts relatedness only; identifying conflicts is stage 3. Invoke after extract-rules completes successfully and before any rule analysis, whenever rules.json, the annotated specification, or the dimension taxonomy changes, and whenever analysis units must be made finer without re-deriving a validated vocabulary.
---

# group-rules

This skill implements the second stage of the analysis pipeline
(extraction → **grouping** → analysis). Its inputs are
`specs/<X>/rules.json`, `specs/<X>/anonymized_annotated_resolved.md` — the
canonical text for this stage, in which cross-reference titles are
resolved — and `specs/<X>/authority_overrides.json`. Its outputs are a
committed `specs/<X>/grouped_rules.json`, in which every rule carries
`neighbor`, `groups`, and `related_context` fields; a committed dimension
registry `specs/<X>/dimensions.json`; and a committed registry-provenance
record `specs/<X>/dimensions_derivation.json`.

## Division of labor with stage 3

Stage 2 asserts **relatedness**: which rules govern the same behavior,
which qualify or specialize one another, and what context bears on each.
Stage 3 identifies **problems**: whether related rules prescribe
incompatible behavior and whether the specification resolves the
incompatibility. This stage therefore records no opposition judgments and
constructs no conflict-derived groups; a consumer finding an "opposition"
artifact of any kind in this stage's output should treat it as a defect.
Everything stage 3 needs to make those judgments — the semantic groups,
the thematic structure, and each rule's resolution devices, exceptions,
and example precedents — is supplied as context rather than as
conclusions.

## Method

Methodologically, grouping is a hybrid inductive–deductive content
analysis (Hsieh & Shannon, 2005; Krippendorff, 2018): the analytic
vocabulary — the behavioral-dimension registry — is **induced** from the
specification under a replicated, reliability-gated derivation protocol,
frozen, and then **deductively applied** by labelling and edge-authoring
passes that treat it as a closed codebook. Model judgment enters the
final artifact at exactly three audited points: registry derivation
(document-level; protocolized and validated against held-out structure),
per-rule dimension labelling (rule-level; closed-vocabulary), and
per-pair thematic assertions (pair-level; quotation-gated). Everything
downstream of those inputs is deterministic and independently
re-checkable.

Grouping is formalized as the construction of two artifacts in sequence.

**1. A typed relatedness graph.** Let `R` denote the rule set. The stage
constructs an edge-labelled multigraph `G = (R, E)` in which each edge
carries a relation type, an optional subtype, a direction, a provenance
marker (`mechanical` or `semantic`), and — where the relation makes a
claim beyond shared membership — verbatim textual evidence. Mechanical
edges (shared sentence, shared section, shared example, cross-reference)
are computed deterministically from the document. Semantic edges are of
two kinds: **semantic adjacency** (`shares_dimension`), derived
mechanically from the dimension labelling so that every rule has an
explicit edge to every rule semantically related to it, and **thematic
structure** (`thematic`), authored by parallel subagents with quoted
evidence and validated against the text before acceptance. The graph is
materialized on the rules themselves as the `neighbor` field.

**2. A two-tier covering family of groups.** The stage then emits one
group per behavioral dimension (family `dimension`, tier **primary**) and
one group per innermost document section owning at least one rule (family
`section`, tier **secondary**). Groups are **unbounded**: a dimension's
group contains its entire membership, however large. Stage 3 analyzes
groups, with the dimension tier as its principal unit of work and the
section tier as a structural complement.

Two design principles govern the graph. Semantic adjacency is **declared,
not argued**: a `shares_dimension` edge asserts only co-membership, its
grounding being the labelling itself, and so carries the shared keys
rather than a quotation. Thematic structure is **argued, not declared**:
a `thematic` edge asserts a specific relationship between two rules'
prescriptions and must quote the text that shows it.

The method maintains four verifiable properties, enforced by the
verification conditions of the final section:

- **P1 (Textual grounding).** Every quotation — thematic evidence and all
  `related_context` material — is a verbatim substring of the resolved
  specification; unverifiable support is rejected mechanically at merge
  time.
- **P2 (Symmetry).** Every edge is recorded on both endpoints with
  direction inverted and all other attributes identical.
- **P3 (Semantic completeness).** For every pair of rules sharing at
  least one dimension, a `shares_dimension` edge exists naming the shared
  keys, and the pair is co-resident in each shared dimension's group.
  Both hold by construction and are verified independently.
- **P4 (Structural completeness).** Every pair of rules owned by the same
  innermost section is co-resident in that section's group.

To these the taxonomy protocol adds two more:

- **P5 (Taxonomy validity).** The dimension taxonomy satisfies the
  registry verification conditions R1–R6: well-formed and traceable to
  text (R1, R2), pairwise distinguishable in application (R3), covering
  and non-degenerate (R4), predictive of held-out author-encoded
  structure (R5), and reliably applicable by independent coders (R6).
- **P6 (Granularity).** Every primary group is small enough to be
  analyzed as one unit: no fine axis exceeds the granularity target
  `tau_max` members, or its excess is documented as irreducible.
  Refinements additionally satisfy R8 — subsumption, exhaustiveness,
  sibling separation, and per-child reliability.

In addition, the mechanical passes are deterministic (byte-identical
reproduction on unchanged inputs).

**The design imposes no structural limits.** Groups are unbounded, a
rule's degree is uncapped, and no covering constructions exist to work
around size bounds. The only numeric conventions retained are evidence
hygiene (quotation length), which is a citation convention rather than a
structural limit, and the acceptance thresholds of the registry protocol,
which gate artifact quality rather than artifact size.

## Parameters and conventions

| Name | Default | Kind | Meaning |
|---|---|---|---|
| `max_quote_words` | 40 | citation convention | Length of any single evidence or context quotation |
| `--packets` | 12 | orchestration | Number of pass-A agent packets the section partition is coalesced into |
| `--min-members` | 2 | orchestration | Smallest dimension for which pass B authors thematic edges |
| `--coders` | 3 | registry derivation | Independent registry coders executing protocol steps D1–D2 |
| `--pilot-sample` | 40 | registry derivation | Size of the chapter-stratified rule sample on which each dimension's operational test is piloted |
| `kappa_min` | 0.6 | acceptance gate | Minimum per-dimension Cohen's κ between independent pilot labelers (the "substantial" band of Landis & Koch, 1977) |
| `--permutations` | 1000 | acceptance gate | Label permutations drawn for the held-out enrichment test |
| `enrichment_p_max` | 0.01 | acceptance gate | Maximum permutation p-value for held-out structural validation (R5) |
| `tau_max` | 30 | granularity target | Membership above which an axis is a refinement candidate (R7) |
| `--refine-labelers` | 2 | refinement | Independent labelers assigning a parent's members to its children |

There is no group-size bound and no per-rule edge cap. `tau_max` is a
**refinement trigger, not a cap**: an axis exceeding it is subdivided if a
valid refinement exists, and retained whole with a recorded justification
if none does. No group is ever truncated, split arbitrarily, or packed to
satisfy it.

## Output schema (`specs/<X>/grouped_rules.json`)

Every rule record carries all fields of its `rules.json` source record
unchanged (elided below), followed by the fields added by this stage.

```json
{
  "spec": "<X>",
  "source": "anonymized_annotated_resolved.md",
  "config": { "max_quote_words": 40 },
  "rules": [
    {
      "id": "kl21",
      "authority": "root",
      "sections": ["stay_in_bounds", "risky_situations", "do_not_facilitate_illicit_behavior"],
      "text": "…",
      "dimensions": ["clarification_and_intent_probing", "refusal_decisions_and_safe_completion"],
      "groups": ["dim:clarification_and_intent_probing",
                 "dim:refusal_decisions_and_safe_completion",
                 "sec:stay_in_bounds/risky_situations/do_not_facilitate_illicit_behavior"],
      "neighbor": [
        { "id": "0q9d", "relation": "shares_dimension", "subtype": null,
          "direction": "none", "source": "semantic",
          "via": ["refusal_decisions_and_safe_completion"],
          "evidence": null, "note": null },
        { "id": "z113", "relation": "thematic", "subtype": "conditions",
          "direction": "in", "source": "semantic",
          "evidence": { "where": "#do_not_facilitate_illicit_behavior",
                        "quote": "The assistant should refuse to help the user when they indicate illicit intent (which may be inferred from any available context, not just the literal request)" },
          "note": "z113's inferred-intent trigger bounds when kl21's comply-by-default applies." },
        { "id": "kl20", "relation": "same_section", "subtype": null,
          "direction": "none", "source": "mechanical",
          "evidence": null, "note": null }
      ],
      "related_context": { "…": "unchanged from the context schema below" }
    }
  ],
  "groups": [
    { "gid": "dim:refusal_decisions_and_safe_completion",
      "family": "dimension", "tier": "primary",
      "members": ["…"],
      "rationale": "behavioral dimension 'refusal_decisions_and_safe_completion' (Refusal, compliance, and safe completion)" },
    { "gid": "sec:stay_in_bounds/risky_situations/do_not_facilitate_illicit_behavior",
      "family": "section", "tier": "secondary",
      "members": ["…"],
      "rationale": "innermost section #do_not_facilitate_illicit_behavior (authority=root)" }
  ]
}
```

### Field semantics

**`neighbor`** (list; the field name is mandated by the pipeline design) —
all rules related to this rule, one entry per typed edge.

- `relation` ∈ {`same_sentence`, `same_section`, `shares_example`,
  `cross_reference`, `shares_dimension`, `thematic`}.
- `subtype` refines `cross_reference`
  (∈ {`defers_to`, `carves_exception_from`, `tightens`, `style_modulates`,
  `background`}) and `thematic` (∈ {`reinforces`, `conditions`,
  `specializes`}); it is `null` otherwise.
- `direction` ∈ {`out`, `in`, `none`}; `out` denotes that the relation is
  asserted from this rule toward the neighbor. Every edge is stored on
  both endpoints with `direction` inverted; relations of direction `none`
  are stored identically on both endpoints.
- `source` ∈ {`mechanical`, `semantic`}. `shares_dimension` and
  `thematic` are semantic; the remainder mechanical.
- `via` (on `shares_dimension` only) lists the shared dimension keys —
  the edge's grounding. Each listed key must appear in **both** endpoints'
  `dimensions`.
- `evidence` is required and non-null on `thematic` edges; it is `null`
  on `shares_dimension` edges, whose justification is the labelling
  itself, and on the purely structural mechanical relations.
  `cross_reference` edges carry the citing sentence as evidence.

### Relation vocabulary

| Relation | Meaning | Directed | Grounding |
|---|---|---|---|
| `same_sentence` | both markers annotate one sentence | no | document structure |
| `same_section` | same innermost section | no | document structure |
| `shares_example` | the same worked example illustrates both | no | document structure |
| `cross_reference` | one rule's own sentence cites the other's section | yes | citing sentence |
| `shares_dimension` | the rules are semantically adjacent: they share the listed dimensions | no | the labelling (`via`) |
| `thematic` | a specific relationship between the two prescriptions | yes¹ | verbatim quotation |

¹ `thematic/reinforces` is undirected; `conditions` and `specializes`
point from the narrower or qualifying rule toward the more general one.

Opposition is **deliberately absent** from this vocabulary. Determining
that two rules prescribe incompatible behavior is conflict identification
and belongs to stage 3, which performs it within the dimension groups with
the full `related_context` of each member available. Stage 2's thematic
subtypes describe structure (restatement, qualification, narrowing)
without judging compatibility.

**`related_context`** (object; the field name is mandated by the pipeline
design) — the compact per-rule context dossier:

- `sentence`: the rule's full sentence, reconstructed across source line
  wraps.
- `stem` / `framing`: the introductory sentence and framing prose when
  the rule text is a list item; framing frequently establishes that an
  apparent tension is an acknowledged tradeoff.
- `ancestor_guards`: constraining sentences from ancestor sections.
- `definitions`: the defining quotation, with anchor and boundary note,
  for every term of art in the rule's trigger or behavior.
- `meta_resolution`: the specification's conflict-resolution devices
  plausibly bearing on this rule — the authority ordering and override
  semantics; the provision that conflicting root-level principles default
  to inaction; the outcome orderings of `#do_not_lie` and
  `#express_uncertainty`; exclusivity claims; the red-line limitation on
  customization. Supplied so that stage 3 can adjudicate claimed
  conflicts; this stage makes no such claims.
- `exceptions`: carve-outs classified `hard_edge` or `judgment_delegated`.
- `facets` / `facet_specifics` / `facet_evidence`: conditional
  applicability along deployment surface, modality, user age, interaction
  setting, and conversation state.
- `examples`: inventory-linked, same-section, and **external** examples
  (examples housed in other sections whose scenarios exercise this rule),
  with verdict notes preserving `BAD[#anchor]` cause annotations.
- `commentary`: in-scope commentary blocks, marked non-normative.
- `authority_provenance`: `"section_header"`, or an object
  `{"override_reason": …}` quoting `authority_overrides.json`.

**`groups`** (list) — the identifiers of every group the rule belongs to;
an inverse index of `groups[].members`, which remains authoritative. The
two directions are verified for exact agreement.

**Group records** carry `gid`, `family` (`dimension` or `section`),
`tier` (`primary` or `secondary`), `members`, and `rationale`. Group
identifiers are fully semantic: `dim:<key>` and `sec:<section path>`.
There are no numeric part suffixes, because nothing is split.

## Dimension taxonomy (`specs/<X>/dimensions.json`)

A committed, human-reviewable registry of the specification's behavioral
dimensions — the semantic axes along which textually distant rules
regulate the same behavior. This artifact recovers the cross-document
relations that section structure cannot observe, and it is the basis of
the primary grouping tier.

The registry is a **two-level taxonomy**. Each entry is either a *root
axis* (no parent) or a *child axis* carrying `parent: <key>`; axes with no
children and root axes that were never refined are **leaves**. Leaves are
the labelling vocabulary and the primary grouping tier; a root axis with
children survives as a **coarse** group equal to the union of its
descendants, preserving continuity with the unrefined vocabulary and
giving stage 3 a fallback view when a fine unit proves too narrow. A flat
registry — every entry a childless root — is the degenerate case, so a
registry produced without refinement remains valid input.

```json
{
  "dimensions": [
    { "key": "clarification_and_intent_probing",
      "title": "Clarifying questions, stated assumptions, and intent probing",
      "definition": "The conditions under which the assistant may, must, or must not ask for clarification, confirm assumptions, or investigate user intent before acting or answering.",
      "seed_anchors": ["#ask_clarifying_questions", "#letter_and_spirit",
                        "#do_not_facilitate_illicit_behavior", "#support_programmatic_use"],
      "counter_poles": "obligations to seek confirmation versus the prohibition on intent probing and exclusions in programmatic settings" }
  ]
}
```

### Registry contract (output requirements)

Twelve to twenty dimensions; keys are stable slugs (lowercase,
underscores) that must never be renamed once committed — group
identifiers embed them, so new dimensions are appended rather than
substituted. Definitions are written as **operational tests** applicable
to a rule with a yes-or-no answer, and must be mutually distinguishable.
Every dimension lists `seed_anchors` (the sections that motivated it),
and the seed anchors of each dimension must span at least two top-level
chapters. `counter_poles` names the opposing pressures the axis
contains; it is **documentation for stage 3's attention**, recorded here
because the registry authors have just read the document, and is not used
by any stage-2 pass. The registry must be derived from the specification
under the protocol below, not imported from a generic taxonomy, so that
it constitutes independent evidence about the document.

The cardinality band governs the **root** level. For an inventory of
several hundred rules, twelve to twenty multi-label root axes are few
enough that each names a concern a reader can hold in mind, that the
pairwise distinguishability audit (R3) stays tractable, and that the
derivation itself remains a document-level judgment rather than a
cataloguing exercise. Fewer axes collapse distinct behavioral concerns
into undifferentiated groups; more root axes fragment concerns below the
granularity at which a coder can still argue for an axis from a whole
reading of the document. The band does **not** govern the leaf level:
leaves arise from refinement (below), whose cardinality is set by the
granularity target rather than by a prior count.

A root axis's membership, however, is not bounded by anything in the
derivation: a concern the document regulates heavily — refusal, for
instance — attracts a large share of the inventory, and the resulting
group may exceed what one stage-3 context can hold. This is the tension
the taxonomy resolves: root axes are sized by *conceptual* coherence,
leaves by *analytic* capacity.

### Why derivation is protocolized

The registry is the point of greatest epistemic exposure in this stage:
the primary grouping tier, the `shares_dimension` relation, the candidate
universe for thematic structure, and every downstream partition all
condition on the choice of axes, yet that choice is an act of qualitative
judgment that no verbatim-substring check can validate. A single
unscripted reading would leave the pipeline's strongest guarantees
resting on one unexamined sample of one reader. The protocol below
therefore treats registry construction as **codebook development** in
the sense of team-based qualitative analysis (MacQueen, McLellan, Kay &
Milstein, 1998): categories are induced from the corpus by open and
axial coding (Glaser & Strauss, 1967; Corbin & Strauss, 1990), refined
into a codebook with explicit inclusion tests, subjected to a
reliability-gated pilot, and only then applied deductively. The stance
throughout is that the judgment remains unscripted at the level of
insight — no procedure manufactures the right axes — but every input,
every intermediate artifact, and every acceptance decision is fixed in
advance, recorded, and independently checkable.

Large-language-model coders introduce failure modes with no exact analog
in human annotation teams, and the protocol addresses each one
structurally rather than by exhortation:

| Failure mode | Mechanism | Structural mitigation |
|---|---|---|
| Taxonomy mirrors the table of contents | section headings are the most salient organization | behavior-not-topic guardrail (G1); cross-chapter `memo_refs` (D2); span gate (R2) |
| Axes drift from behaviors to topics | content domains are lexically salient | operational-test form; two-domain applicability test (G1); facet exclusion (G5) |
| Early chapters over-represented | primacy effects and degraded mid-context attention (Liu et al., 2024) | independent coders read under permuted chapter orders (D1) |
| Idiosyncratic axes | a single derivation is one sample of one judgment | replicated derivation with definition-level reconciliation and consensus status (D3); agreement reporting per annotation-science practice (Artstein & Poesio, 2008) |
| Synonymous or nested axes | consolidation under-merges near-duplicates | pairwise distinguishability witnesses (R3); the reconciler's merger rule (D3) |
| Definitions that cannot be applied consistently | an operational test can be well-formed yet ambiguous in practice | dual-coder pilot with a chance-corrected agreement gate and ambiguity-driven revision (D4), treating LLM coders under the same reliability discipline as human coders (Gilardi, Alizadeh & Kubli, 2023; Ziems et al., 2024) |
| Missing axes | premature closure of the category set | saturation criterion (D5; Saunders et al., 2018) and the coverage residue check (R4) |
| Self-confirming validation | the validation signal is visible during authoring | link-blinded derivation corpus (D0) with the citation graph held out for convergent validation (D6; Campbell & Fiske, 1959) |

### Derivation protocol (D0–D7)

**D0 — Blinded corpus preparation.** Materialize a link-blinded variant
of the resolved specification in which every inline cross-reference
`[Title](#anchor)` is replaced by its bare `Title`, removing the link
target while leaving every sentence intact. Rule markers, example tags,
and section headings (with their own anchors) are preserved. The
document's citation graph is thereby withheld from the deriving coders
and reserved as held-out validation evidence for D6; because link titles
survive inline, the blinding is partial, and the residual leakage is
disclosed in the derivation report. The blinding transformation is
deterministic and recorded in `dimensions_derivation.json`.

**D1 — Independent open coding.** Execute `--coders` independent coder
subagents. Each receives the blinded corpus with its top-level chapters
presented in a distinct permuted order (a distinct rotation suffices),
so that no single region of the document occupies the primacy position
for all coders, and produces **open-coding memos** in the sense of
grounded theory (Glaser & Strauss, 1967): fine-grained, quotation-backed
notes recording, per contiguous run of rules, the assistant behavior
being regulated. Coders work in isolation and never see one another's
output; independent replicates with subsequent reconciliation, rather
than a single sampled judgment, is the same reliability principle that
motivates self-consistency decoding (Wang et al., 2023), applied here at
the level of a research procedure.

**D2 — Axial coding into candidate registries.** Each coder consolidates
its own memos into a candidate registry of twelve to twenty axes in the
contract's shape (axial coding around behavioral phenomena; Corbin &
Strauss, 1990), each axis carrying `memo_refs` into its supporting memos,
which must come from at least two different top-level chapters. The
genre guardrails G1–G5 below are part of the coder instructions.

**D3 — Definition-level reconciliation.** A reconciler subagent receives
the candidate registries in randomized order with coder identity
withheld, and aligns axes **by operational definition, not by name**:
two candidates align when their tests would classify the same rules the
same way. It emits the consensus registry, an alignment table assigning
every input candidate to a consensus axis (possibly as a merger) or a
rejection with reason, and a status per consensus axis ∈ {`unanimous`,
`majority`, `singleton`}. A singleton — an axis proposed by one coder
only — is admitted only if no other axis's test covers its seed
anchors, and every admitted singleton is flagged for mandatory piloting
in D4. The fraction of unanimous and majority axes is itself reported
as convergence evidence.

**D4 — Reliability-gated pilot.** Draw a chapter-stratified sample of
`--pilot-sample` rules. For every consensus axis, two independent pilot
labelers apply the axis's operational test to each sampled rule
(yes/no, with a supporting quotation), and per-axis inter-coder
agreement is computed as Cohen's κ (Cohen, 1960). An axis with
κ < `kappa_min` is not discarded but **revised**: its ambiguity notes
are used to tighten the definition, and the pilot is repeated with fresh
labeler contexts. This is the standard codebook refinement loop
(MacQueen et al., 1998), with the κ ≥ 0.6 acceptance band following
Landis & Koch (1977). The pilot measures the *definitions'* reliability,
which is the construct-validity question (Cronbach & Meehl, 1955): a
test that independent appliers cannot agree on does not measure a
construct, however plausible its prose.

**D5 — Saturation and coverage.** Sweep the full rule inventory: every
rule must be labelable with at least one axis. Rules fitting no axis
form the residue; a non-trivial residue triggers either a new appended
axis (which must itself pass D4) or an explicit documented decision that
the residue is genuinely outside every behavioral axis. Derivation is
complete when one further independent coding pass proposes no axis that
fails to align with the existing registry — the theoretical-saturation
criterion (Glaser & Strauss, 1967; Saunders et al., 2018).

**D6 — Held-out structural validation.** After pass A completes the
full labelling, compute the **citation-graph enrichment**: the
probability that a pair of rules connected by a sentence-scope
`cross_reference` edge shares at least one dimension, divided by the
same probability over all rule pairs, with significance assessed by a
permutation test that shuffles the per-rule label sets across rules
(`--permutations` draws). Because the coders derived the axes from a
link-blinded corpus (D0) and never conditioned on the citation graph,
enrichment constitutes convergent validation by an independent method
(Campbell & Fiske, 1959; triangulation in the sense of Denzin, 1978):
the induced axes recover connectivity that the specification's own
authors encoded through an entirely different channel. The gate is an
enrichment ratio above one at p ≤ `enrichment_p_max`; failure indicates
axes that organize the analyst's reading but not the document, and
returns the protocol to D2 with the diagnosis recorded.

**D7 — Freeze and provenance.** Commit `dimensions.json` and
`dimensions_derivation.json`. From this point the registry is a closed
codebook applied deductively (directed content analysis; Hsieh &
Shannon, 2005): labelling and thematic passes may select keys but never
coin, rename, or redefine them. Keys are append-only forever after;
an appended axis must traverse D4 and D6 before use.

### Genre-specific guardrails (G1–G5)

Behavioral specifications for language models are a recognizable
document genre — descended from principle-list approaches to model
governance (Bai et al., 2022) and exemplified by published model
specifications — with recurring structural properties that a derivation
protocol can exploit. The following guardrails encode that genre
knowledge; they are embedded in the coder and reconciler instructions
and enforced where mechanically checkable.

- **G1 — Behavior, not topic.** An axis names a regulated *assistant act
  type* — refusing, hedging, asking, disclosing, transforming,
  escalating — never a content domain. The test: a valid axis applies to
  rules in at least two unrelated content domains. Domains (medical,
  legal, financial) are conditions of applicability, captured as facets
  by pass A, not axes.
- **G2 — Authority invariance.** An axis must be definable without
  reference to the authority level of its rules. The genre's instruction
  hierarchy is an ordering *over* rules — already recorded per rule in
  the inventory — and a registry that mirrors it duplicates metadata
  while occluding behavior.
- **G3 — Cross-sectional reach.** Each axis's seed anchors must span at
  least two top-level chapters. An axis coextensive with one section
  restates the secondary (section) tier and adds nothing; the registry
  exists precisely to recover the relations the section tree cannot
  express.
- **G4 — Counter-pole expectation.** Documents of this genre are
  engineered around declared tensions — helpfulness against
  harm-avoidance, user autonomy against protection, candor against
  privacy — and a genuine behavioral axis normally contains rules
  pulling in both directions. A coder who can find no counter-pole for a
  proposed axis is instructed to suspect a topic in disguise (a G1
  violation) before admitting the axis without one.
- **G5 — Meta-rule exclusion.** The specification's conflict-resolution
  devices — the authority ordering, override semantics, defaults to
  inaction — are machinery *about* rules. They are captured per rule as
  `meta_resolution` context and must not surface as axes; an axis of
  "conflict resolution" would launder stage-3 subject matter into the
  stage-2 vocabulary.

Refinement adds two further guardrails, which apply to child axes only.

- **G6 — Refine by act, not by subject matter.** A refinement must
  partition a parent by the *sub-act* its rules regulate, never by the
  content domain, deployment surface, or population they apply to.
  Splitting a refusal axis into medical, legal, and sexual-content
  children is a G1 violation wearing a hierarchy: the resulting children
  duplicate facets that pass A already records per rule, and — decisively
  for this stage's purpose — they place rules that regulate *the same
  decision* in different analysis units, which is precisely the
  separation that hides inconsistencies. The admissible split of such an axis
  is by decision stage: what triggers the behavior, how absolute the bar
  is, how far partial compliance may go, how carve-outs are handled. A
  child whose membership is predictable from a rule's topic alone fails
  this guardrail.
- **G7 — Subsumption.** A child's test must entail its parent's:
  $\chi_c(v) = 1 \Rightarrow \chi_{\mathrm{parent}(c)}(v) = 1$ for every
  rule. Subsumption is what makes refinement *local*: only the parent's
  members can satisfy a child, so refining one axis cannot alter the
  membership of any other, and unrefined axes carry their validated
  memberships through unchanged.

### Granularity refinement (F1–F5)

Refinement is triggered by measured oversize, not by taste, and is
confined to the axes that trigger it.

**F1 — Candidate selection.** After a complete labelling, an axis
$\delta$ with $|V_\delta| > \texttt{tau\_max}$ is a refinement candidate.
Axes at or below the target are not touched; their memberships,
reliability results, and group identifiers pass through unchanged, so a
refinement round perturbs only what it must and leaves the rest of the
validated vocabulary bit-for-bit intact.

**F2 — Sub-axis proposal.** For each candidate, a refiner examines the
parent's registry entry and the full enriched record of **every** member
rule — not a sample, since the split must account for the whole
membership — and proposes two or more child axes in the registry
contract's shape, each carrying `parent`, its own membership test, seed
anchors drawn from the parent's members, and a counter-pole where one
exists. The refiner is bound by G1, G2, G5, G6, and G7, and by two
structural requirements: the children must be **exhaustive** over the
parent's membership (every member satisfies at least one child test) and
**separated** (for each ordered pair of siblings, some member satisfies
one and not the other). Children may overlap: a rule that genuinely
belongs to two sub-acts takes both labels, exactly as the parent
vocabulary is multi-label. G3's cross-chapter requirement does not apply to children,
which inherit their parent's cross-sectional reach by subsumption; a
child is instead required not to be coextensive with a section group,
which is what G3 exists to prevent.

**F3 — Dual labelling with reliability.** Two labelers independently
assign every member of the parent to its children, working from the child
tests alone. Per-child agreement is computed as Cohen's $\kappa$ over the
parent's **entire** membership rather than a sample — the population is
already bounded by $|V_\delta|$, so the stronger measurement is free, and
it is the more demanding test: within a parent, every negative is a
near-miss, so a child that merely renames its parent cannot score well.
A child below `kappa_min` has its test sharpened and is re-labelled. The
committed labelling is the union of the two labelers' assignments, the
inclusive choice consistent with pass A's stance on uncertain relevance;
the disagreement rate is reported alongside $\kappa$.

**F4 — Acceptance or retention.** A refinement is accepted when all its
children pass F3 and R8 holds (subsumption, exhaustiveness, separation,
reliability). A child still above `tau_max` may be refined again at the
next level. A candidate for which no valid refinement can be found — the
concern genuinely admits no behavioral subdivision — is **retained whole**
with a recorded justification: an oversized group with a documented reason
is a finding about the specification, whereas an arbitrary split is a
defect in the method.

**F5 — Downstream regeneration.** Leaves become the labelling vocabulary:
`shares_dimension` edges, the primary groups, and the vertex-splitting
contexts are all recomputed from leaf labels, while parent unions are
emitted as coarse groups. Thematic edges are **inherited** rather than
re-authored, and the inheritance is sound by G7: a within-leaf pair is a
within-parent pair, so the candidate universe of the parent-level
authoring pass strictly contains the leaf-level one, and inheritance is
conservative with respect to thematic recall. Inherited edges whose
endpoints no longer share a leaf are retained in the graph and surface as
bridges at splitting time; the report states how many. Re-authoring at
leaf granularity is permitted and expected to raise recall, but is never
required for validity.

### Registry provenance (`specs/<X>/dimensions_derivation.json`)

A committed record making the derivation auditable end to end:

```json
{
  "protocol": "D0-D7",
  "blinding": { "transform": "inline cross-reference targets elided", "residual_leakage": "…" },
  "coders": [ { "id": 1, "chapter_order": ["…"], "candidate_axes": 17 } ],
  "alignment": [ { "key": "…", "status": "unanimous|majority|singleton",
                   "from": [ { "coder": 1, "candidate": "…" } ] } ],
  "pilot": { "sample_size": 40, "kappa": { "<key>": 0.74 }, "revised": ["<key>"] },
  "saturation": { "additional_pass_new_axes": 0 },
  "enrichment": { "ratio": 0.0, "p_value": 0.0, "permutations": 1000 },
  "residue": [],
  "refinements": [ { "parent": "<key>", "parent_size": 93, "tau_max": 30,
                      "children": ["<key>", "…"],
                      "kappa": { "<key>": 0.81 }, "disagreement_rate": 0.07,
                      "exhaustive": true, "separated": true,
                      "retained_whole": false, "justification": null } ]
}
```

A registry committed before this protocol existed carries no provenance
record; it is marked `legacy`, remains subject to the retroactive gates
R1–R5, and acquires provenance incrementally as axes are appended under
the protocol.

## Procedure

0. **Preconditions.** `python3 scripts/check_rules.py specs/<X>` returns
   `OK`; no rule has null authority; the resolved specification exists and
   reproduces exactly from `scripts/resolve_crossrefs.py`. All textual
   operations read `anonymized_annotated_resolved.md`.

1. **Mechanical graph and context.** Execute

   ```
   python3 scripts/build_rule_graph.py specs/<X>
   ```

   It writes `specs/<X>/.rule_graph.json` (excluded from version control)
   containing, per rule, the mechanical edges (`same_sentence`,
   `same_section`, `shares_example`, and `cross_reference` with the citing
   sentence captured verbatim) and the mechanical context (stem and
   framing for list-item rules, ancestor-section prose, in-section
   commentary, example tags with `GOOD`/`OK`/`BAD[#anchor]` verdict
   annotations, section-level references, authority provenance). Parsing
   is code-fence-aware; sentences are reconstructed over logical blocks
   that join wrapped source lines; output ordering is deterministic.
   Cross-reference edges resolve to the rules directly owned by the cited
   anchor, without truncation.

2. **Dimension registry (protocol D0–D7).** If `specs/<X>/dimensions.json`
   does not exist, execute the derivation protocol in full: materialize
   the blinded corpus (D0); run `--coders` independent coder subagents
   under permuted chapter orders (D1–D2, fragments to
   `specs/<X>/.registry_fragments/coder_<i>.json`); reconcile (D3); pilot
   and gate every axis (D4, fragments to
   `specs/<X>/.registry_fragments/pilot/`); sweep for coverage and
   saturation (D5); and commit the registry with its provenance record
   (D7). D6 is evaluated after step 3 completes and, on failure, returns
   the procedure to this step. If the registry exists, it is append-only:
   new axes traverse D4 before use, and the retroactive gates are
   re-evaluated. In both cases run

   ```
   python3 scripts/check_taxonomy.py specs/<X>
   ```

   and present the registry difference and gate outcomes in the final
   report — the registry is a reviewable research artifact, not an
   internal cache.

2b. **Granularity refinement (protocol F1–F5).** After a complete
   labelling exists — on a first run, after step 3; on a refinement run,
   from the committed artifact — compute every axis's membership and
   select the candidates with more than `tau_max` members (F1). For each
   candidate in parallel, execute one refiner subagent over the parent's
   registry entry and the enriched records of all its members (F2,
   fragments to `specs/<X>/.registry_fragments/refine/<parent>.json`),
   then `--refine-labelers` independent labeler subagents over the same
   membership (F3, fragments to
   `.registry_fragments/refine/<parent>_label_<i>.json`). Compute
   per-child $\kappa$, sharpen and re-label any child below `kappa_min`,
   and commit the union labelling. Accept the refinement or retain the
   parent whole with justification (F4); append the children to
   `dimensions.json` with their `parent` keys — parent keys are never
   renamed or removed — and record the refinement block in the provenance
   file. Recompute leaf labels for every rule (F5): a rule's leaf labels
   are its unrefined axes plus the children assigned to it, and the
   refined parent keys are retained only as coarse-group identifiers.
   Then re-run steps 5 and 6, and re-evaluate the enrichment gate at leaf
   granularity.

3. **Semantic pass A — per-section enrichment.** Using the `jobs[]`
   partition of `specs/<X>/.rule_index.json` coalesced into `--packets`
   agent packets (`scripts/prepare_grouping_jobs.py`), execute one
   subagent per packet. Each receives its section slices of the resolved
   specification, the mechanical graph entries for its rules (including
   the citing sentence of every cross-reference edge), and the dimension
   registry; it returns, per rule: `dimensions` (multi-label, at least
   one, registry keys only), `facets` with evidence, `exceptions`,
   `definitions`, `meta_resolution` selections, external-example
   candidates found by whole-document search, and a `subtype` for every
   incident cross-reference edge. Fragments are written to
   `specs/<X>/.grouping_fragments/section/`. After the labelling is
   merged, evaluate D6 (the enrichment gate) via `check_taxonomy.py`.

4. **Semantic pass B — per-dimension thematic structure.** Using
   per-dimension packets (`scripts/prepare_dimension_jobs.py`), execute
   one subagent per dimension key. Each receives the registry entry and
   the fully enriched records of every member rule; it returns `thematic`
   edges among members — `reinforces`, `conditions`, or `specializes`,
   each with a verbatim evidence quotation and a note. A subagent may
   name a partner outside its dimension where the evidence compels it;
   such edges are marked `out_of_dimension: true` and are reported (they
   fall outside P3's guarantee). No edge budget applies. Pass B does not
   classify oppositions; where two members appear incompatible, the
   correct output is whatever thematic structure the text supports,
   with the judgment left to stage 3. Fragments are written to
   `specs/<X>/.grouping_fragments/dimension/`.

5. **Merge, symmetrization, and group construction.** Execute

   ```
   python3 scripts/build_groups.py specs/<X>
   ```

   The script joins mechanical and semantic fragments; rejects any
   thematic edge whose evidence quotation is not a verbatim substring of
   the resolved specification after typography normalization, or whose
   identifiers or anchors do not exist; **generates `shares_dimension`
   edges mechanically from the labelling** — one edge per pair of rules
   with intersecting `dimensions`, carrying the shared keys in `via`;
   mirrors every surviving edge onto both endpoints with direction
   inverted; and emits the two group families:

   - `dimension` (tier primary) — one group per registry key with at
     least one member, containing the entire membership, with
     `gid = dim:<key>`;
   - `section` (tier secondary) — one group per innermost section owning
     at least one rule, containing all rules of that section, with
     `gid = sec:<section path>`.

   No splitting, packing, or covering construction is performed; groups
   are unbounded. The script finally writes
   `specs/<X>/grouped_rules.json` containing the rules (original fields,
   `dimensions`, `groups`, `neighbor`, `related_context`) and `groups`,
   with the per-rule `groups` field mirroring `groups[].members`.

6. **Verification.** `build_groups.py` evaluates conditions V1 to V6 on
   the structures it holds in memory. That is necessary but not
   sufficient: it does not exercise the artifact that was written.
   Therefore also run

   ```
   python3 scripts/check_grouped.py specs/<X>
   python3 scripts/check_taxonomy.py specs/<X>
   ```

   which re-derive every invariant — the graph and group conditions from
   the emitted `grouped_rules.json`, the registry conditions from the
   emitted `dimensions.json` — together with the specification and the
   inventory, sharing no code with the builder. Both exit non-zero on
   any failure. Correct and re-execute the affected steps until all
   conditions hold.

## Subagent prompt (template, registry coder, D1–D2)

> You are inducing the behavioral-dimension registry of an anonymized
> model specification (pipeline stage 2: rule grouping; derivation
> protocol steps D1–D2). You receive the link-blinded resolved
> specification with its top-level chapters presented in the order
> `<permutation>`. Other coders are reading the same document in other
> orders; you will not see their output, and they will not see yours.
>
> First produce **open-coding memos**: for every contiguous run of rules
> that regulates a recognizably common assistant behavior, one memo
> `{ "behavior": imperative phrase naming the regulated act, "where":
> section anchor, "quote": verbatim, at most 40 words, "note": at most
> 25 words }`. Memo at the finest granularity that still names a
> behavior rather than a topic; over-generation is expected and correct.
>
> Second, consolidate **your own memos only** into a candidate registry
> of twelve to twenty dimensions in the registry contract's shape, each
> carrying `memo_refs` drawn from at least two different top-level
> chapters. Apply the genre guardrails: an axis names an assistant act
> type, never a content domain, and must apply to at least two unrelated
> domains (G1); it must be definable without reference to authority
> level (G2); its definition is an operational yes-or-no test applicable
> to a single rule; name its counter-pole — where the document pushes
> the same behavior in the opposite direction — and if none can be
> found, reconsider whether the axis is a topic in disguise (G4);
> conflict-resolution machinery is not an axis (G5).
>
> Grounding requirements: every quotation verbatim (at most 40 words);
> every anchor must occur in the document. Do not attempt to reconstruct
> the specification's cross-reference structure — the citation graph is
> deliberately withheld and reserved for held-out validation.

## Subagent prompt (template, registry reconciler, D3)

> You are reconciling `<k>` independently derived candidate registries
> into the consensus behavioral-dimension registry (derivation protocol
> step D3). The candidates are presented in randomized order without
> coder identity. Align axes **by operational definition, not by name**:
> two candidates align when their tests would classify the same rules
> the same way; merge aligned candidates into one consensus axis whose
> definition is the sharpest of the merged tests and whose seed anchors
> are the union.
>
> Emit `{ "dimensions": [ … contract shape … ], "alignment": [ { "key":
> consensus key, "status": "unanimous" | "majority" | "singleton",
> "from": [ { "coder": index, "candidate": key } ] } ], "rejections":
> [ { "coder": index, "candidate": key, "reason": at most 25 words } ] }`.
>
> Admit a singleton only if no other axis's test covers its seed
> anchors; flag every admitted singleton for mandatory piloting. Enforce
> the contract and guardrails on the consensus set: twelve to twenty
> axes, operational tests, mutual distinguishability, cross-chapter seed
> anchors, counter-poles, no topical or authority-defined or meta-rule
> axes.

## Subagent prompt (template, pilot labeler, D4)

> You are piloting the operational test of behavioral dimension `<key>`
> (derivation protocol step D4). You receive the registry entry and
> `<n>` rules sampled across the specification's chapters. For each rule
> return `{ "id": marker, "applies": true | false, "quote": verbatim
> support, at most 40 words }`, applying the definition exactly as
> written. Where the definition does not determine an answer for a rule,
> answer as best the text allows and add `"ambiguity": at most 20
> words` — ambiguity notes drive definition revision. Do not consider
> what other rules received; each rule is judged alone against the test.

## Subagent prompt (template, refiner, F2)

> You are subdividing the behavioral dimension `<parent>` of an
> anonymized model specification, which has `<n>` member rules — more
> than one analysis context can hold (granularity protocol step F2). You
> receive the parent's registry entry and the enriched record of every
> member rule.
>
> Propose two or more child axes that partition the parent **by the
> sub-act its rules regulate**, in the registry contract's shape plus a
> `parent` field: `{ "key", "parent": "<parent>", "title",
> "definition": an operational yes-or-no test, "seed_anchors": anchors
> drawn from the members, "counter_poles" }`.
>
> Requirements. (i) *Subsumption*: a rule satisfying a child test must
> satisfy the parent's — children carve up the parent, never reach
> outside it. (ii) *Exhaustiveness*: every member rule must satisfy at
> least one child test; state which child covers each member. (iii)
> *Separation*: for each ordered pair of children, name a member
> satisfying one and not the other. (iv) *Act, not subject matter*: split
> by decision stage — what triggers the behavior, how absolute the bar
> is, how far partial compliance may go, how carve-outs are handled —
> never by content domain, deployment surface, or population, which are
> recorded per rule as facets and would scatter rules that regulate one
> decision across different units. A child whose membership you could
> predict from a rule's topic alone is the wrong split. (v) Children may
> overlap where a rule genuinely regulates two sub-acts. (vi) Aim for
> children of at most `<tau_max>` members, but prefer a defensible split
> into uneven children over a balanced one that violates (iv).
>
> If the concern genuinely admits no behavioral subdivision, return no
> children and justify that conclusion in at most 40 words; a documented
> oversized axis is a finding, an arbitrary split is a defect.

## Subagent prompt (template, refinement labeler, F3)

> You are assigning the member rules of behavioral dimension `<parent>`
> to its child axes (granularity protocol step F3). You are one of
> several independent labelers and will not see the others' output. You
> receive the child entries — each with an operational yes-or-no test —
> and the enriched record of every member rule.
>
> For each member rule, apply each child test exactly as written and
> return every child whose test the rule satisfies:
> `{ "records": [ { "id": marker, "children": ["<key>", …] } ] }`.
> Judge each rule alone on its own marked clause; do not balance
> membership counts across children, and do not consider what other
> rules received. Every rule must receive at least one child; where no
> test clearly applies, choose the closest, set `"forced": true`, and add
> `"ambiguity"` in at most 20 words — ambiguity notes drive test
> revision.

## Subagent prompt (template, semantic pass A)

> You are enriching the rules of section `<section_path>` of an anonymized
> model specification (pipeline stage 2: rule grouping). You receive the
> verbatim section slice, the mechanical graph entries for marker
> identifiers `<marker_ids>`, and the behavioral-dimension registry.
>
> Return a JSON object `{ "records": [ … ] }` covering exactly these
> marker identifiers. For each record provide: `dimensions` (registry keys
> only; multi-label; at least one), `facets` (surface, modality, age,
> setting, state — each `applies`, `excluded`, or
> `unconditional_or_unspecified`, with a verbatim source quotation for
> every non-default value), `exceptions` (each classified `hard_edge` or
> `judgment_delegated`, with quotation), `definitions` (terms of art in
> the rule, with the defining quotation and its anchor),
> `meta_resolution` (only devices plausibly relevant to this rule),
> `external_examples` (example tags housed in other sections whose
> scenarios exercise this rule; search the entire document), and, for
> every incident cross-reference edge, a `subtype` ∈ {defers_to,
> carves_exception_from, tightens, style_modulates, background} judged
> from the captured citing sentence.
>
> Grounding requirements: every quotation must be verbatim (at most 40
> words), and every anchor, marker identifier, and example tag must occur
> in the document. Do not invent identifiers. When relevance is
> uncertain, include the item with a brief justification rather than
> omitting it.

## Subagent prompt (template, semantic pass B)

> You are authoring thematic structure among the rules of behavioral
> dimension `<key>` (pipeline stage 2: rule grouping). You receive the
> registry entry and the fully enriched records of all member rules.
>
> Return `{ "edges": [ { "a": id, "b": id, "relation": "thematic",
> "subtype": "reinforces" | "conditions" | "specializes", "direction":
> "out" | "in" | "none", "evidence": { "where": anchor-or-marker,
> "quote": verbatim, at most 40 words }, "note": at most 20 words,
> "out_of_dimension": false } ] }`.
>
> A thematic edge asserts a specific relationship between two rules'
> prescriptions: `reinforces` (mutually consistent statements of one
> requirement), `conditions` (one qualifies or constrains when the other
> applies), or `specializes` (one is a narrower case of the other). Each
> edge requires a verbatim quotation demonstrating the relationship;
> co-membership in the dimension is recorded elsewhere and is not by
> itself an edge. There is no edge budget: author every relationship the
> text supports, and do not emit near-duplicate edges for the same pair.
>
> Do not classify or label oppositions, conflicts, or inconsistencies, and do
> not withhold an edge because the two rules appear incompatible —
> incompatibility judgments belong to a later stage. Where a genuine
> relationship crosses the dimension boundary, you may name an external
> partner with `out_of_dimension: true`; such edges are reported
> separately.

## Coverage guarantee

The verification conditions enforce, and the report must state, the
completeness properties: every pair of rules sharing a dimension carries
a `shares_dimension` edge naming the shared keys and is co-resident in
each shared dimension's group (P3), and every pair of rules in one
innermost section is co-resident in that section's group (P4). Because
groups are unbounded, both hold by construction; they are nonetheless
verified independently against the written artifact. Thematic edges
marked `out_of_dimension` fall outside these guarantees and are reported
individually.

## Verification conditions

Conditions V1 to V6 are evaluated twice: by `build_groups.py` on its
in-memory structures, and independently by `check_grouped.py` on the
written artifact. Agreement between a builder and an independent reader
is the property that makes the artifact trustworthy; a condition that
only the builder can confirm establishes little.

- **V1 — Identifier closure.** Every neighbor identifier, example tag,
  dimension key, group identifier, and anchor referenced anywhere in
  `grouped_rules.json` exists in the inventory, the document, the
  registry, or the group list, respectively.
- **V2 — Quotation grounding (P1).** Every `quote` is a verbatim
  substring of `anonymized_annotated_resolved.md` after typography
  normalization. `shares_dimension` edges carry no quotation; their
  grounding is checked under V4.
- **V3 — Symmetry (P2).** Every edge appears on both endpoints with
  direction inverted and identical relation, subtype, source, and `via`.
- **V4 — Semantic completeness (P3).** For every pair of rules with
  intersecting `dimensions`, exactly one `shares_dimension` edge exists
  per endpoint, its `via` equals the intersection, and the pair is
  co-resident in each shared dimension's group. Conversely, every
  `shares_dimension` edge's `via` is non-empty and a subset of both
  endpoints' labels.
- **V5 — Structural completeness (P4).** Every innermost section owning
  at least one rule has exactly one `section` group containing exactly
  its rules, and every `same_section` edge's endpoints are co-resident
  there.
- **V6 — Rule coverage.** Every rule of `rules.json` appears in the
  output with a non-empty `related_context`, at least one dimension, and
  at least one group of each tier; the per-rule `groups` field agrees
  exactly with `groups[].members`.
- **V7 — Determinism.** Re-executing steps 1 and 5 on unchanged inputs
  reproduces `grouped_rules.json` byte-identically.
- **V8 — Inventory integrity.** `python3 scripts/check_rules.py specs/<X>`
  still returns `OK`; this skill never modifies `rules.json`.

## Registry verification conditions

Conditions R1 to R6 are evaluated by `scripts/check_taxonomy.py` on the
committed `dimensions.json`, the resolved specification, and — for the
label-dependent conditions — the emitted `grouped_rules.json`. A registry
that predates the derivation protocol is checked retroactively and
reported as `legacy`; R6 is evaluated only where pilot fragments exist.

- **R1 — Contract shape.** Twelve to twenty dimensions; every key a
  stable slug; every record carries a non-empty title, definition,
  `seed_anchors`, and `counter_poles`; definitions pairwise distinct.
- **R2 — Textual traceability.** Every seed anchor occurs as a section
  anchor of the resolved specification, and every **root** axis's seed
  anchors span at least two top-level chapters (G3). A child inherits
  that reach by subsumption and may legitimately concentrate in one
  section, so it is held to G3's purpose instead of its root-level
  proxy: a child's membership must not coincide with a section group,
  which would duplicate the secondary tier.
- **R3 — Distinguishability.** No two leaves share one extension: for
  every pair (A, B) some rule is labelled with A and not with B, or with
  B and not with A. A pair with no witness in either direction denotes
  two names for one construct and fails. A pair witnessed in exactly one
  direction is a strict nesting — admissible, since the tests differ and
  the extensions merely nest on this corpus, but reported, because a
  nesting that persists across corpora argues for consolidation.
- **R4 — Coverage and non-degeneracy.** Every rule carries at least one
  dimension label, and every dimension has at least `--min-members`
  members; the residue list is empty or documented.
- **R5 — Held-out structural validation.** The citation-graph
  enrichment ratio exceeds one with permutation p ≤ `enrichment_p_max`
  (D6). The ratio, the p-value, and the permutation count are reported.
- **R6 — Pilot reliability.** Every axis's most recent pilot achieved
  Cohen's κ ≥ `kappa_min` between independent labelers; axes revised
  during D4 report both the failing and the passing pilot.
- **R7 — Granularity.** No leaf axis has more than `tau_max` members,
  except those recorded in the provenance as retained whole with a
  justification (F4). The count of oversized leaves, before and after
  refinement, is reported.
- **R8 — Refinement validity.** For every refined parent: each child's
  membership is a subset of the parent's (subsumption, G7); the children's
  memberships cover the parent's (exhaustiveness); for each ordered pair
  of siblings some rule lies in one and not the other (separation); and
  each child's dual-labelling agreement met `kappa_min` (F3). Coarse
  groups equal the union of their descendants, and no leaf has a leaf
  parent.

## Incremental maintenance

When the specification changes while marker identifiers are preserved,
the semantic passes are re-executed only for rules whose `text` or `sections` changed, together with every
prior thematic partner of a changed or removed rule, while all other
fragments are retained. `shares_dimension` edges and both group families
are regenerated mechanically from the updated labelling at no additional
authoring cost. The dimension registry is append-only; an appended axis
traverses D4 (reliability pilot) before use and D6 is re-evaluated after
the next full labelling. The report identifies which rules were
re-derived.

## Reporting requirements

The final report states: the rule count; edge counts by relation and
provenance, with `shares_dimension` and `thematic` reported separately;
rejected-edge counts by verification reason; the dimension count and the
registry difference; the registry derivation summary — coder count and
chapter orders, per-axis consensus status, per-axis pilot κ (with
revisions), the saturation outcome, the residue, and the enrichment
ratio with its p-value; for every refinement, the parent and its size,
each child with its membership and κ, the labeler disagreement rate, and
any parent retained whole with its justification; the number of groups
above `tau_max` before and after refinement; group counts and size
distributions per tier; the list of `out_of_dimension` thematic edges;
the list of rules with no thematic edge (their existence is not an
error); whether thematic edges were inherited or re-authored at leaf
granularity, with the count of inherited edges whose endpoints no longer
share a leaf; and the outcome of every verification condition V1–V8 and
R1–R8, including explicit confirmation of semantic completeness (V4),
structural completeness (V5), and granularity (R7).

## References

- Artstein, R., & Poesio, M. (2008). Inter-coder agreement for
  computational linguistics. *Computational Linguistics*, 34(4).
- Bai, Y., et al. (2022). Constitutional AI: Harmlessness from AI
  feedback. *arXiv:2212.08073*.
- Campbell, D. T., & Fiske, D. W. (1959). Convergent and discriminant
  validation by the multitrait-multimethod matrix. *Psychological
  Bulletin*, 56(2).
- Cohen, J. (1960). A coefficient of agreement for nominal scales.
  *Educational and Psychological Measurement*, 20(1).
- Corbin, J., & Strauss, A. (1990). Grounded theory research:
  Procedures, canons, and evaluative criteria. *Qualitative Sociology*,
  13(1).
- Cronbach, L. J., & Meehl, P. E. (1955). Construct validity in
  psychological tests. *Psychological Bulletin*, 52(4).
- Denzin, N. K. (1978). *The Research Act: A Theoretical Introduction to
  Sociological Methods*. McGraw-Hill.
- Gilardi, F., Alizadeh, M., & Kubli, M. (2023). ChatGPT outperforms
  crowd workers for text-annotation tasks. *PNAS*, 120(30).
- Glaser, B. G., & Strauss, A. L. (1967). *The Discovery of Grounded
  Theory: Strategies for Qualitative Research*. Aldine.
- Hsieh, H.-F., & Shannon, S. E. (2005). Three approaches to qualitative
  content analysis. *Qualitative Health Research*, 15(9).
- Krippendorff, K. (2018). *Content Analysis: An Introduction to Its
  Methodology* (4th ed.). Sage.
- Landis, J. R., & Koch, G. G. (1977). The measurement of observer
  agreement for categorical data. *Biometrics*, 33(1).
- Liu, N. F., et al. (2024). Lost in the middle: How language models use
  long contexts. *TACL*, 12.
- MacQueen, K. M., McLellan, E., Kay, K., & Milstein, B. (1998).
  Codebook development for team-based qualitative analysis. *Cultural
  Anthropology Methods*, 10(2).
- Saunders, B., et al. (2018). Saturation in qualitative research:
  Exploring its conceptualization and operationalization. *Quality &
  Quantity*, 52.
- Wang, X., et al. (2023). Self-consistency improves chain of thought
  reasoning in language models. *ICLR 2023*.
- Ziems, C., et al. (2024). Can large language models transform
  computational social science? *Computational Linguistics*, 50(1).
