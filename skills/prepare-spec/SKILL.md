---
name: prepare-spec
description: 'Preprocess a spec under specs/<X>/ for downstream analysis. Reads specs/<X>/raw.md, writes an anonymized copy at specs/<X>/anonymized.md with all company/product identifiers replaced by neutral placeholders (Lumen Labs / Lumo / lumenlabs.example), Use when the user asks to "prepare the spec at specs/<X>", "anonymize a spec", "run prepare-spec on <X>", or whenever a freshly added spec needs to be readied before annotate-spec runs.'
---

# prepare-spec

Anonymize `specs/<X>/raw.md` into `specs/<X>/anonymized.md`.

Re-running is the expected mode of operation: overwrite an existing
`anonymized.md` without prompting. Treat `raw.md` as
read-only — never modify it.

## Inputs

The user supplies a spec name `X` such that `specs/<X>/raw.md` exists.

- If they pass a path (`specs/foo/raw.md`, `specs/foo`, `specs/foo.md`,
  `foo`), normalize to the bare directory name.
- If `specs/<X>/raw.md` does not exist, list `specs/` and ask which spec
  they meant.

---

## Anonymize

Read `specs/<X>/raw.md` in full. Produce `specs/<X>/anonymized.md` with
every company- or product-identifying string replaced by neutral
placeholders. Preserve everything else (line numbers, blank lines,
ordering, code blocks, tables, image refs, footnote markers) byte-for-byte
aside from the substitutions themselves.

### Replacement table

Apply these substitutions everywhere — body prose, headings, code blocks,
link targets, link text, image alt/captions, anchor IDs (`{#...}`),
inline comments, footnotes. Substitutions are **case-preserving**: match
the casing of the source token in the replacement (e.g. `Anthropic` →
`Lumen Labs`, `anthropic` → `lumen labs`, `ANTHROPIC` → `LUMEN LABS`).

| Original                                                  | Replacement              |
|-----------------------------------------------------------|--------------------------|
| `Anthropic`, `OpenAI`                                     | `Lumen Labs`             |
| `Claude`, `GPT`, `ChatGPT`                                | `Lumo`                   |
| Model tiers: `Opus`, `Sonnet`, `Haiku`, `GPT-4`, `GPT-5`, `GPT-4o`, … | `Lumo` (drop the tier suffix) |
| `Constitutional AI`, `Claude's constitution`              | `Lumo Charter`           |
| `anthropic.com`, `openai.com`, `chat.openai.com`, `platform.openai.com`, `claude.ai` | `lumenlabs.example`      |
| `Anthropic's Acceptable Use Policy`, `OpenAI's usage policies` | `Lumen Labs' Acceptable Use Policy` |
| Author / employee names in bylines, acknowledgements, dedications | `A researcher` / `Researchers at Lumen Labs` |
| Image paths or alt text containing brand names            | strip the brand component (keep the path structure) |

### Rules

- **Case preservation.** For multi-word replacements, mirror the source
  casing pattern as best you can: `Anthropic` → `Lumen Labs`,
  `ANTHROPIC` → `LUMEN LABS`, `anthropic` → `lumen labs`.
- **Word-boundary substitution.** Don't replace `gpt` inside an unrelated
  identifier like `argpt` (unlikely but possible). Match whole tokens.
- **Possessives and contractions.** `Anthropic's` → `Lumen Labs'`,
  `Claude's` → `Lumo's`. Preserve apostrophe style.
- **Compound brand terms.** `Claude Sonnet 4.5` → `Lumo` (drop the tier
  and version). `GPT-4 Turbo` → `Lumo`. `claude-3-opus-20240229` →
  `lumo`.
- **URLs.** Replace the bare domain regardless of scheme/path:
  `https://www.anthropic.com/foo` → `https://www.lumenlabs.example/foo`.
  Preserve query strings and fragments.
- **Author lists / acknowledgements.** Don't try to anonymize each
  individual; collapse the entire list to `A researcher` (singular) or
  `Researchers at Lumen Labs` (plural). Do not invent names.
- **Do not** add or remove sections, reorder paragraphs, or reflow text.
  The line count of `anonymized.md` should equal the line count of
  `raw.md` modulo whatever shift the substitutions themselves cause
  inside individual lines.

### Self-check

After writing `anonymized.md`, run a case-insensitive grep over it for:

```
anthropic|openai|chatgpt|claude|gpt|sonnet|opus|haiku|constitutional ai|anthropic\.com|openai\.com
```

Every hit must be either (a) a clearly unrelated false positive (e.g.
the literary form "haiku" used as a generic noun in an example) — note
these in your final report — or (b) a missed substitution to fix before
reporting done. Be exhaustive: this output is consumed by other
analyses and any leak corrupts the downstream review.

Report substitution counts in your final summary
(`Anthropic→Lumen Labs: N`, etc.).

---

## Output summary (final response to the user)

Report concisely:

- **Anonymization counts** — substitution counts per source token
  (e.g. `Anthropic→Lumen Labs: 142, Claude→Lumo: 287, …`). List any
  flagged false-positive grep hits you chose to leave alone.
- **Output path** — `specs/<X>/anonymized.md`.
- **Check** — confirm `python3 scripts/check_anonymization.py specs/<X>`
  returns `OK`.
