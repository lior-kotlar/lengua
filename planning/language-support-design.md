# Language support — curated list + custom fallback (issue #95, Option B)

**Status: DECIDED 2026-07-09 (Ben) — ready to implement via `/next-task #95`.**
Design-alignment outcome for
[issue #95](https://github.com/lior-kotlar/lengua/issues/95); this file is the implementation
spec. **Frontend-only** — no API, schema, or migration changes; legacy Streamlit untouched.

## Decision

**Option B — curated list with a free-form fallback**, folding in Option A's code→metadata lookup
for the custom path.

Why B (short version):

- Every pain point in #95 is a **metadata** problem (RTL, vowel-marks discoverability, blank/dup
  codes), not a coverage problem — picking "Arabic" from a list sets `code=ar`, RTL, and the
  vowel-marks default in one gesture.
- Option A hangs the fix on the ISO-code field, which #95 itself notes users forget to fill.
- Option C (LLM-assisted metadata) adds latency, cost, and non-determinism to a config action,
  routes a config write through the LLM cost guard, and pokes a hole in the zero-real-LLM-calls
  CI/E2E contract. Language facts are static; a lookup table doesn't rot.
- The free-form fallback keeps today's behavior reachable, so **existing rows need no migration**
  and polyglots lose nothing.

Sub-decisions (from #95's "questions to resolve"):

1. **Weak/unknown languages:** passthrough with expectation-setting (a "custom / experimental"
   label), never block.
2. **RTL + vowel marks:** auto-set from the curated entry (or, on the custom path, derived from the
   code exactly as today via `directionForCode`); user-overridable.
3. **`script` tag:** carried in the client-side table for future font/spacing decisions; **not**
   persisted (no DB column until something consumes it).
4. **Resolution stays independent of the backend:** generation keeps receiving the language `name`
   verbatim; nothing server-side changes.

## Design

### 1. Curated table — `apps/web/src/lib/curated-languages.ts` (new)

A typed readonly const, single source of truth for the picker:

```ts
export interface CuratedLanguage {
  /** English name — what is stored as the language `name` and interpolated into prompts. */
  name: string;
  /** Endonym, shown as secondary text in its own script (also hints the writing system). */
  nativeName: string;
  /** Lowercase primary subtag, e.g. "es". Drives direction/font via lib/language-text.ts. */
  code: string;
  /** Writing system tag for future font/spacing work (NOT persisted). */
  script:
    | 'Latin' | 'Cyrillic' | 'Greek' | 'Arabic' | 'Hebrew' | 'Devanagari'
    | 'Bengali' | 'Han' | 'Japanese' | 'Hangul' | 'Thai';
  /** Language uses optional vowel diacritics (harakat/nikkud) worth toggling. */
  vowelizable: boolean;
}
```

**Do not duplicate `rtl`** — direction and script font are already derived from `code` by
[`language-text.ts`](../apps/web/src/lib/language-text.ts) (`directionForCode`,
`scriptFontClass`); a table test asserts consistency instead.

The list (~44 — the CEFR-taught European canon + the major world languages Gemini handles
confidently). `vowelizable: true` only for **Arabic, Hebrew, Persian** (matches the existing
S14 hint in the add form):

| name | nativeName | code | script | vowelizable |
| --- | --- | --- | --- | --- |
| Arabic | العربية | ar | Arabic | ✓ |
| Bengali | বাংলা | bn | Bengali | |
| Bulgarian | Български | bg | Cyrillic | |
| Catalan | Català | ca | Latin | |
| Chinese (Mandarin) | 中文 | zh | Han | |
| Croatian | Hrvatski | hr | Latin | |
| Czech | Čeština | cs | Latin | |
| Danish | Dansk | da | Latin | |
| Dutch | Nederlands | nl | Latin | |
| English | English | en | Latin | |
| Estonian | Eesti | et | Latin | |
| Filipino (Tagalog) | Filipino | fil | Latin | |
| Finnish | Suomi | fi | Latin | |
| French | Français | fr | Latin | |
| German | Deutsch | de | Latin | |
| Greek | Ελληνικά | el | Greek | |
| Hebrew | עברית | he | Hebrew | ✓ |
| Hindi | हिन्दी | hi | Devanagari | |
| Hungarian | Magyar | hu | Latin | |
| Icelandic | Íslenska | is | Latin | |
| Indonesian | Bahasa Indonesia | id | Latin | |
| Italian | Italiano | it | Latin | |
| Japanese | 日本語 | ja | Japanese | |
| Korean | 한국어 | ko | Hangul | |
| Latvian | Latviešu | lv | Latin | |
| Lithuanian | Lietuvių | lt | Latin | |
| Malay | Bahasa Melayu | ms | Latin | |
| Norwegian | Norsk | no | Latin | |
| Persian (Farsi) | فارسی | fa | Arabic | ✓ |
| Polish | Polski | pl | Latin | |
| Portuguese | Português | pt | Latin | |
| Romanian | Română | ro | Latin | |
| Russian | Русский | ru | Cyrillic | |
| Serbian | Српски | sr | Cyrillic | |
| Slovak | Slovenčina | sk | Latin | |
| Slovenian | Slovenščina | sl | Latin | |
| Spanish | Español | es | Latin | |
| Swahili | Kiswahili | sw | Latin | |
| Swedish | Svenska | sv | Latin | |
| Thai | ไทย | th | Thai | |
| Turkish | Türkçe | tr | Latin | |
| Ukrainian | Українська | uk | Cyrillic | |
| Urdu | اردو | ur | Arabic | |
| Vietnamese | Tiếng Việt | vi | Latin | |

Helpers exported next to the table: `findCurated(name)` (case-insensitive, trimmed match on
`name`) and `findCuratedByCode(code)` (primary-subtag match, for the custom-path smart defaults).

### 2. UX — add-language flow (`add-language-form.tsx` rework)

The free-text **Name/Code fields stop being the primary entry**. New flow, in the existing card
on the Languages page, using the design system's input/popover primitives:

- **Searchable picker (ARIA combobox).** A single search input; below it a listbox of curated
  languages, alphabetical by English name. Each option: `Spanish` (text-body) with `Español` as
  secondary text (text-subhead, muted) rendered in its own script + `scriptFontClass` — the
  endonym doubles as a script preview. Filter = case-insensitive substring over `name`,
  `nativeName`, and `code`. Full list on empty query; list capped to a scrollable max-height.
  Keyboard: ↑/↓ move, Enter selects, Esc closes; proper `role="combobox"` /
  `aria-expanded` / `aria-activedescendant` wiring (the advisory axe e2e covers this page).
- **Curated selection → no Name/Code inputs at all.** The selection renders as a filled chip/row
  (with a change affordance). Below it: the existing **Starting level** select, and — **only when
  `vowelizable`** — the vowel-marks toggle, **defaulted ON** (fixes #95 pain point 3: a beginner
  adding Arabic gets harakat without knowing to opt in; advanced users untick). Non-vowelizable
  languages never see the toggle. Submit posts `{name, code, vowelized}` exactly as today —
  the S14 "code required when vowelized" rule is satisfied by construction.
- **Custom path (Option A folded in).** The last row of the listbox is always
  `Add "<query>" as a custom language…` (the only row when nothing matches). Choosing it switches
  the form to today's fields — Name (prefilled with the query) + Code (optional) + level +
  vowel-marks checkbox with the existing S14 validation — under a **"Custom (experimental)"**
  heading with the footnote: *"Not on the curated list — sentence quality depends on the AI
  model's coverage of this language. Text direction and vowel marks are derived from the code."*
  Typing a code whose primary subtag matches a curated entry (`findCuratedByCode`) pre-sets the
  vowel-marks default; RTL/font stay derived from the code as today. A back affordance returns to
  the picker.
- **Soft duplicate warning (custom path only, non-blocking):** if another of the user's languages
  shares the code's primary subtag, show an inline hint ("You already have a language with code
  `es`"); submission stays allowed (the server's idempotent-by-name behavior is unchanged).
- **"Experimental" badge.** In the Languages list (and anywhere the language name is prominent, at
  the implementer's judgment), a small muted badge on languages whose `name` has **no**
  case-insensitive curated match (`findCurated`). Name-based on purpose: generation interpolates
  the *name*, so the name is what predicts quality. Derived client-side — existing rows need no
  backfill; e.g. an old `Spanish`/`es` row simply matches and shows no badge.
- **Analytics (optional nice-to-have):** extend `trackLanguageAdded` with a non-PII
  `curated: boolean` property.

### 3. Explicitly out of scope

No backend/API/schema change; no server-side validation or blocklist; no per-language prompt
overrides (see the [#80](https://github.com/lior-kotlar/lengua/issues/80) store's future `scope`
column for that); no persistence of `script`; legacy Streamlit keeps its own free-form UI.

## Implementation outline (one PR)

1. `apps/web/src/lib/curated-languages.ts` + `curated-languages.test.ts` — table + helpers;
   invariant tests (codes/names unique + lowercase codes; `vowelizable` ⊆ {ar, he, fa}; every
   Arabic/Hebrew-script entry is RTL per `directionForCode`; every entry has a `script`).
2. `apps/web/src/components/language-combobox.tsx` (+ test) — the ARIA combobox over the table
   (search, keyboard nav, custom-row emission). Presentational; callback-driven.
3. Rework `apps/web/src/components/add-language-form.tsx` (+ tests) — picker-first flow, curated
   submit path, conditional defaulted-ON vowel toggle, custom path with S14 validation + code
   smart-defaults + duplicate hint.
4. Badge in `apps/web/src/pages/Languages.tsx` (+ test).
5. Sweep e2e specs that drive the add-language form (FakeLLM harness) for the new selectors; specs
   that seed via the API are unaffected.
6. Docs: README "add a language" usage section; CHANGELOG entry; tick #95 off
   [`outstanding-work.md`](outstanding-work.md); close #95 via the PR.

**Verify:** `corepack pnpm --filter web lint` / `format:check` / `tsc` / `vitest` (≥80% coverage
held); FakeLLM e2e in CI. **Mode: auto-merge** when green — frontend-only, no
migrations/security surface (pause only if scope creeps into the API).

## Acceptance criteria

- Picking a curated language never shows Name/Code inputs and lands correct code + direction +
  script font + vowel-marks default (ON for ar/he/fa, hidden otherwise) without user knowledge.
- A custom language remains addable exactly as today (S14 validation intact), labeled
  experimental, with smart defaults when a known code is typed.
- Existing languages keep working untouched; non-curated ones show the badge; curated-named ones
  don't.
- Combobox is keyboard- and screen-reader-operable; the advisory axe run stays clean on
  `/languages`.
- Zero backend diff (`apps/api` untouched); web coverage ≥80%; FakeLLM e2e green.

## As-built deviations (PR #145)

- **Always-open listbox instead of "Esc closes".** The design bullet above says "Esc closes", but
  the built picker is an **inline, always-open** filterable listbox inside the Languages card (not a
  popover), so `aria-expanded` is permanently `true` and there is nothing to collapse. Escape is
  repurposed to **clear the query** (keyboard nav is ↑/↓ move, Enter selects, Esc clears). This is a
  coherent combobox pattern for an in-card picker (cf. always-open command palettes) and keeps the
  listbox — the whole point of the picker — visible at all times. Keyboard handling additionally
  guards IME composition (a CJK candidate-commit Enter / candidate-list arrows never leak into
  option navigation), and per-option ids are keyed by the language code so `aria-activedescendant`
  changes as filtering re-targets the active row (screen-reader announcements stay correct).
