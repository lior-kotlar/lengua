# Lengua 🗣️

A personal language-learning app. You type the vocabulary words you want to learn, and
Lengua asks Gemini for natural example sentences that use them — then turns those
sentences into flashcards and schedules a smart daily review batch.

It replaces the manual workflow of pasting words + a long "rules" prompt into a chat UI:
the rules, the generation instruction, and your active language are attached
automatically on every request, so you only ever supply the words.

## How it works

1. **Pick a language** in the sidebar (e.g. Spanish, Arabic). It's saved and stays active
   across pages and restarts. You can learn several languages and switch between them.
2. **Generate** — paste vocabulary words (one per line or comma-separated). Lengua sends
   them to Gemini with your fixed rules prompt and gets back, for each item:
   - the **sentence** in your target language,
   - a natural **English translation**,
   - the **vocabulary words** it used.
3. **Save as flashcards** — each sentence becomes a card (front = target language,
   back = English) stored in a local SQLite deck.
4. **Review** — Lengua shows the cards due today, you reveal the translation and rate your
   recall (*Again / Hard / Good / Easy*). [FSRS](https://github.com/open-spaced-repetition/py-fsrs)
   reschedules each card, so the daily batch stays fresh on its own — no cron needed.

## Setup

The Gemini API key is read from a `.env` file in the project root:

```
GEMINI_API_KEY=your_key_here
```

Install dependencies (a virtualenv is recommended):

```
pip install -r requirements.txt
```

## Run

```
python -m streamlit run app.py
```

This opens the app in your browser. Data is stored locally in `data/lengua.db`
(created automatically, git-ignored).

## Customizing the sentence rules

The rules that govern *how* sentences are written live in
[`lengua/prompts.py`](lengua/prompts.py) as an editable `RULES` list. To add or change a
rule, edit one entry — the prompt text is reassembled automatically. The output shape
(sentence / translation / used_words) is enforced by the schema in
[`lengua/gemini.py`](lengua/gemini.py), so the rules only affect writing style, not format.

## Project layout

```
app.py               Streamlit entry point / home page
pages/
  1_Generate.py      words in -> sentences out
  2_Review.py        daily flashcard review (FSRS)
lengua/
  config.py          loads .env, model name, paths, daily limits
  db.py              SQLite connection + schema
  models.py          GeneratedCard (sentence / translation / used_words)
  prompts.py         the editable rules + output-format prompt
  gemini.py          Gemini wrapper: words -> structured cards
  languages.py       learned languages + active-language setting
  flashcards.py      persist generated cards into the deck
  scheduler.py       FSRS: new-card state, due batch, grading
  ui.py              shared sidebar (always-present language selector)
```

## Configuration knobs

Optional environment variables (see [`lengua/config.py`](lengua/config.py)):

| Variable | Default | Meaning |
| --- | --- | --- |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model used for generation |
| `LENGUA_DB_PATH` | `data/lengua.db` | SQLite database location |
| `LENGUA_DAILY_NEW_LIMIT` | `10` | Max brand-new cards per day |
| `LENGUA_DAILY_TOTAL_LIMIT` | `50` | Max cards in a daily review batch |
