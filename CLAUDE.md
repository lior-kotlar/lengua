# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Project

Lengua is a personal language-learning app (Streamlit + Gemini). You enter vocabulary
words; Gemini writes natural example sentences using them; each sentence becomes two
FSRS-scheduled flashcards (recognition + production). Each language has a CEFR level that
shapes generation and adapts from review answers. See [README.md](README.md) for the full
overview and [`lengua/`](lengua/) for the modules.

## Maintenance rules

- **Keep the README current.** Whenever a change adds or alters something significant to how
  the app is *used* — a new page or workflow, a new user-facing feature, a change to how
  review/generation behaves, a new setting or env var, or a new module worth listing in the
  project layout — update [README.md](README.md) in the same change so it always reflects
  current behavior. Purely internal refactors that don't change usage don't require a README
  edit.
