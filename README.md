# Lengua 🗣️

A personal language-learning app. You type the vocabulary words you want to learn, and
Lengua asks Gemini for natural example sentences that use them — then turns those
sentences into flashcards and schedules a smart daily review batch.

It replaces the manual workflow of pasting words + a long "rules" prompt into a chat UI:
the rules, the generation instruction, and your active language are attached
automatically on every request, so you only ever supply the words.

## Repository layout & how to run each app

Lengua is being productionized from a single Streamlit app into a monorepo (FastAPI API +
React web app + Supabase + Cloud Run). The full plan lives in [`planning/`](planning/) — start
at [`planning/tasks/task-tracker.md`](planning/tasks/task-tracker.md).

```
apps/
  api/        FastAPI service (uv) — scaffolded in Phase 0 group 0.2
  web/        React + TS + Vite app (pnpm, Tailwind + shadcn/ui) — group 0.3
packages/     shared packages, e.g. api-types (OpenAPI-generated TS client) — Phase 1+
infra/        infra & CI/CD docs (the CI gate lives in .github/workflows/)
docs/         privacy policy, runbook, legal — group 0.8
planning/     productionization plan & per-phase task files
supabase/     Supabase CLI config, initial migration, seed
```

| App | Location | How to run | Status |
| --- | --- | --- | --- |
| API | `apps/api/` | `cd apps/api && uv sync && uv run uvicorn app.main:app` (serves `GET /health`); verify with `uv run python scripts/verify.py` | runnable now |
| Web | `apps/web/` | `cd apps/web && pnpm install && pnpm dev` (placeholder home); verify with `pnpm verify`; E2E via `pnpm exec playwright test` | runnable now |
| Legacy Streamlit | `apps/api/legacy_streamlit/` | `cd apps/api && streamlit run legacy_streamlit/app.py` | runnable now |

### One-command verify (local quality gate)

Run the whole monorepo's lint + type-check + tests (+ web build) in one command — it fans out
to the **api** verify (`uv run python scripts/verify.py` in `apps/api`) and the **web** verify
(`pnpm verify` in `apps/web`) and exits non-zero if either fails:

```bash
make verify          # runs apps/api + apps/web gates; targets: verify-api, verify-web
```

No `make` (e.g. on **Windows**)? Run the identical cross-platform engine — it does the same
fan-out and is what CI/local gates call:

```bash
python scripts/verify.py
```

`pnpm` is invoked via `corepack pnpm` when `pnpm` isn't on your `PATH` (corepack ships with
Node and honors the `packageManager` pin in `apps/web/package.json`).

The sections below document the **legacy Streamlit app**, which stays runnable throughout the
migration.

## How it works

1. **Pick a language** in the sidebar (e.g. Spanish, Arabic). It's saved and stays active
   across pages and restarts. You can learn several languages and switch between them. For
   scripts with optional diacritics (Arabic, Hebrew) a per-language **vowel marks** toggle
   asks Gemini to fully vocalize the generated sentences.
2. **Generate** — paste vocabulary words (one per line or comma-separated). Lengua sends
   them to Gemini with your fixed rules prompt and your current level, and gets back, for
   each item:
   - the **sentence** in your target language,
   - a natural **English translation**,
   - the **vocabulary words** it used.
3. **Discover** — no input needed. Lengua looks at all the vocabulary you already know,
   then asks Gemini to pick new words at your current CEFR level that you haven't seen yet.
   You can optionally set a topic (e.g. "food", "travel") to guide the selection, set a
   count, review the suggested words, and either accept them or ask for a different set
   before sentences are written.
4. **Save as flashcards** — each sentence becomes **two** independently-scheduled cards in
   your local SQLite deck: a *recognition* card (read the target sentence, recall the
   English) and a *production* card (read the English, build the target sentence). On the
   production card you can tap any word for a quick explanation.
5. **Review** — Lengua shows the cards due today, you reveal the answer and rate your recall
   (*Again / Hard / Good / Easy*). [FSRS](https://github.com/open-spaced-repetition/py-fsrs)
   reschedules each card, so the daily batch stays fresh on its own — no cron needed. Your
   answers also nudge your level (see below).

## Your level

Each language has a level on the **CEFR scale (A1 → C2)** that tunes how long and complex
the generated sentences are. It's shown in the sidebar (with progress to the next band) and
on the Generate and Review pages.

- **It adapts as you review.** Answering *Easy* nudges your level up; *Again* / *Hard* nudge
  it down; *Good* holds roughly steady — so sentences track your real ability over time.
- **Production counts more.** Because building a sentence (English → target) is harder than
  reading one, success on production cards raises your level faster, and struggling on them
  is penalized less.
- **Only current-level cards move it.** Each card remembers the level it was generated at, so
  a backlog of old/easy cards can't inflate your level.
- **You can override it.** Use *Adjust level* in the sidebar to set your band manually (handy
  when starting a language you already partly know); it keeps adapting from there.

The nudge sizes and weighting are tunable constants in
[`apps/api/lengua_core/config.py`](apps/api/lengua_core/config.py) (`LEVEL_DELTAS`,
`PROD_POS_WEIGHT`, `PROD_NEG_WEIGHT`, `LEVEL_WINDOW`).

## Setup

The Gemini API key is read from a `.env` file in the project root:

```
GEMINI_API_KEY=your_key_here
```

Install dependencies (a virtualenv is recommended). `requirements.txt` stays at the
repo root for the legacy app:

```
pip install -r requirements.txt
```

## Run

The legacy Streamlit app now lives under `apps/api/legacy_streamlit/`. Run it from
`apps/api/` so the `lengua_core` package is importable:

```
cd apps/api
streamlit run legacy_streamlit/app.py
```

This opens the app in your browser. Data is stored locally in `apps/api/data/lengua.db`
(created automatically relative to the working directory, git-ignored).

## Customizing the sentence rules

The rules that govern *how* sentences are written live in
[`apps/api/lengua_core/prompts.py`](apps/api/lengua_core/prompts.py) as an editable `RULES`
list. To add or change a rule, edit one entry — the prompt text is reassembled
automatically. The output shape (sentence / translation / used_words) is enforced by the
schema in [`apps/api/lengua_core/gemini.py`](apps/api/lengua_core/gemini.py), so the rules
only affect writing style, not format.

## Project layout

The legacy Streamlit app and its domain package now live under `apps/api/`:

```
apps/api/
  legacy_streamlit/
    app.py             Streamlit entry point / home page
    pages/
      1_Generate.py    words in -> sentences out
      2_Review.py      daily flashcard review (FSRS)
      3_Discover.py    auto-pick new vocab at your level -> sentences out
      4_Settings.py    app-wide settings
  lengua_core/
    config.py          loads .env, model name, paths, daily limits, level tuning
    db.py              SQLite connection + schema (+ idempotent migrations)
    models.py          GeneratedCard (sentence / translation / used_words / word_notes)
    prompts.py         the editable rules + output-format + level prompt
    gemini.py          Gemini wrapper: words -> structured cards; tap-a-word explanations
    languages.py       learned languages + active-language setting
    flashcards.py      persist generated cards (recognition + production) into the deck
    scheduler.py       FSRS: new-card state, due batch, grading
    proficiency.py     per-language CEFR level: scoring, review-driven updates, override
    ui.py              shared sidebar (language selector + level)
```

## Configuration knobs

Optional environment variables (see
[`apps/api/lengua_core/config.py`](apps/api/lengua_core/config.py)):

| Variable | Default | Meaning |
| --- | --- | --- |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model used for generation |
| `LENGUA_DB_PATH` | `data/lengua.db` | SQLite database location (relative to CWD) |
| `LENGUA_DAILY_NEW_LIMIT` | `10` | Max brand-new cards per day |
| `LENGUA_DAILY_TOTAL_LIMIT` | `50` | Max cards in a daily review batch |
