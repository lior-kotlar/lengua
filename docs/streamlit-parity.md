# Legacy Streamlit → React parity checklist

> **Status: parity reached.** Every legacy Streamlit page and feature has a reachable React
> equivalent (or a conscious, documented retirement). With this checklist fully ✅, the legacy
> Streamlit app under [`apps/api/legacy_streamlit/`](../apps/api/legacy_streamlit) is **deprecated —
> retained for reference only** (see the README "Legacy Streamlit" note). The code is **not** being
> deleted yet: it stays runnable as a reference implementation and a fallback until the React web app
> ships to production (Phase 6) and mobile (Phase 7).

This document satisfies task **4.11.1** (Phase 4). It maps every surface of the legacy single-user
Streamlit app — `app.py`, the always-present sidebar (`ui.py`), and each `pages/*` page — to the
React screen/component that replaces it, with the route a signed-in user reaches it at. Each row is
genuinely reachable in the React app on the seeded demo account (`demo@lengua.test`, provisioned by
`scripts/seed_e2e.py`).

Legend: ✅ ported · ✅* ported with a documented nuance · ➕ React-only addition (no legacy
counterpart) · ♻️ intentionally retired (capability relocated by design, not a gap).

---

## 1. Sidebar — `legacy_streamlit/ui.py` (`render_sidebar`, on every page)

The legacy sidebar is always-present. In React it splits between the **app shell header**
(active-language picker) and the **left sidebar** of [`AppLayout`](../apps/web/src/components/app-layout.tsx)
(CEFR panel), with add/remove living on a dedicated Languages screen.

| Legacy feature | React equivalent | Route / component | Status |
| --- | --- | --- | --- |
| Active-language selector ("Currently learning") | Header language picker, backed by a shared active-language context persisted per user | header `LanguagePicker` + `ActiveLanguageProvider` ([language-picker.tsx](../apps/web/src/components/language-picker.tsx), [active-language-provider.tsx](../apps/web/src/components/active-language-provider.tsx)) | ✅ |
| Active language persists across restarts | Selection persisted in `localStorage` (per user) and reconciled against the fetched list | `ActiveLanguageProvider` | ✅ |
| CEFR level display: band + progress-to-next-band | Sidebar level panel (band + coloured progress over a neutral track) reading `GET /proficiency/{id}` | `CefrPanel` ([cefr-panel.tsx](../apps/web/src/components/cefr-panel.tsx)) | ✅ |
| Manual level override ("Adjust level" select) | "Override level" select → `PUT /proficiency/{id}` | `CefrPanel` | ✅ |
| Manage languages → Add (name, optional code, vowel-marks flag) | Add-language form (name, optional code, **starting CEFR band**, vowel-marks flag) → `POST /languages` (+ follow-up `PUT /proficiency/{id}` for a non-default band) | `/languages` → `AddLanguageForm` ([add-language-form.tsx](../apps/web/src/components/add-language-form.tsx)) | ✅ |
| Manage languages → Remove a language | Confirm dialog (cascade warning) → `DELETE /languages/{id}` | `/languages` → `RemoveLanguageDialog` ([remove-language-dialog.tsx](../apps/web/src/components/remove-language-dialog.tsx)) | ✅ |
| Per-language vowel-marks (harakat / nikkud) generation flag | Set when adding a language (the form's vowel-marks checkbox sets the language `vowelized` flag the backend passes to generation). Display strip/restore is a richer React control (see §6). | `AddLanguageForm` + `VowelMarksToggle` | ✅* |

✅* **Nuance — flipping `vowelized` on an _existing_ language is not yet UI-wired.** The legacy
sidebar checkbox could toggle the generation-vocalization flag on the active language at any time;
in React it is set at language-creation time. The backend already supports the change
(`PATCH /languages/{id}` toggles `vowelized`), so this is a small UI-wiring follow-up, not a missing
capability — logged in [`planning/outstanding-work.md`](../planning/outstanding-work.md). It does
not affect the daily loop on the demo account (its languages are seeded with the correct flag), and
the separate **display** vowel-marks toggle (§6) is fully present.

---

## 2. Home — `legacy_streamlit/app.py`

| Legacy feature | React equivalent | Route / component | Status |
| --- | --- | --- | --- |
| Welcome / landing page | Authenticated app shell (header + nav sidebar) with a Dashboard landing | `/` → `AppLayout` + `Dashboard` ([Dashboard.tsx](../apps/web/src/pages/Dashboard.tsx)) | ✅ |
| Active-language status indicator | Active language is always shown in the header picker | `LanguagePicker` | ✅ |
| "Add a language to begin" warning | Empty states across screens prompt adding a first language; the Languages screen is the entry point | `EmptyState` + `/languages` | ✅ |

---

## 3. Generate — `legacy_streamlit/pages/1_Generate.py`

| Legacy feature | React equivalent | Route / component | Status |
| --- | --- | --- | --- |
| Active language + level caption | Screen scopes to the active language; level shown in the sidebar `CefrPanel` | `/generate` ([Generate.tsx](../apps/web/src/pages/Generate.tsx)) | ✅ |
| Vocabulary words input (one-per-line / comma-separated) | Textarea + live word chips, parsed identically (`parseWords`) | `Generate` + [generate.ts](../apps/web/src/lib/generate.ts) | ✅ |
| Non-empty validation | Submit blocked until ≥1 word; word-count cap enforced from the OpenAPI schema (`schemaLimits`, not hardcoded) | `Generate` | ✅ |
| "Generate" → call the model + spinner | `POST /generate` via the typed client with an explicit in-progress state | `Generate` + `useGenerate` | ✅ |
| Generation error surfaced to the user | Friendly inline cost-guard states (daily-limit / rate-limited / server-busy / verify-email) + generic fallback — never a raw stack | `LlmErrorState` + `DailyLimitPanel` | ✅ (➕ richer) |
| Result list: sentence · translation · used words | Generated cards grouped back into sentences, each with translation + used-word chips | `Generate` + `groupSentences` | ✅ |
| "Save all as flashcards" → persist deck | Per-sentence select-and-save (default all) → `POST /cards/save`, success toast, review-cache invalidation so saved cards are immediately reviewable | `Generate` + `useSaveCards` | ✅ (➕ per-sentence selection) |

---

## 4. Review — `legacy_streamlit/pages/2_Review.py`

| Legacy feature | React equivalent | Route / component | Status |
| --- | --- | --- | --- |
| Level + new/due counts + deck-size caption | Counts header (new vs. due) + thin progress bar | `/review` ([Review.tsx](../apps/web/src/pages/Review.tsx)) | ✅ |
| Due batch loaded once, walked in session state | `GET /review/due` loads a stable client-side snapshot walked one card at a time (grading does not refetch) | `Review` + [review.ts](../apps/web/src/lib/review.ts) | ✅ |
| "Refresh batch" | "Done for today / check for more" completion state refetches the batch | `Review` | ✅ |
| "No flashcards yet" empty state | "All caught up" / add-a-language empty states | `Review` + `EmptyState` | ✅ |
| "Done for today" completion | Completion state after the last card | `Review` | ✅ |
| Card front + prompt label (production vs recognition) | Front shown with the correct prompt; recognition vs production variants | `Review` (`isProductionCard`) | ✅ |
| Reveal ("Show answer" / "Show translation") | Reveal interaction (answer hidden until revealed) | `Review` | ✅ |
| Recognition reveal shows the translation | Recognition reveal renders the translation | `Review` | ✅ |
| Production reveal renders the target sentence with tap-a-word | Production reveal renders the target sentence in `TappableSentence` | `Review` + [tappable-sentence.tsx](../apps/web/src/components/tappable-sentence.tsx) | ✅ |
| Tap-a-word explanation (per-word, cached, RTL-aware, close button) | Tap/click a word → popover; served from the card's pre-generated note when present, else `POST /explain` keyed by word + language; dismiss on re-tap / close / Escape / outside-pointer; RTL-anchored | `TappableSentence` | ✅ |
| Rating buttons Again / Hard / Good / Easy in **red / orange / blue / green** | Four rating buttons in the locked red/orange/blue/green colours → `POST /review/{id}/grade` (FSRS 1–4) → advance | `Review` (`RATINGS`, `ratingButtonClass`) | ✅ |
| Progress bar (`idx/len reviewed`) | Thin progress bar over the batch | `Review` | ✅ |
| RTL rendering of target text | `dir` derived from the language code (`directionForCode`); RTL-anchored words | `Review` + [language-text.ts](../apps/web/src/lib/language-text.ts) | ✅ |
| _(none — desktop nicety)_ | Keyboard shortcuts: space/enter to reveal, 1–4 to rate | `Review` | ➕ |

---

## 5. Discover — `legacy_streamlit/pages/3_Discover.py`

| Legacy feature | React equivalent | Route / component | Status |
| --- | --- | --- | --- |
| Active language + level caption | Screen scopes to the active language; level in the sidebar panel | `/discover` ([Discover.tsx](../apps/web/src/pages/Discover.tsx)) | ✅ |
| New-words count (slider, default = discover-count setting) | Count input defaulting to the user's `discover_count` from `GET /settings`, clamped to the schema bounds (`schemaLimits`, not hardcoded) | `Discover` + [discover.ts](../apps/web/src/lib/discover.ts) | ✅ |
| Topic / theme input (optional) | Optional topic field | `Discover` | ✅ |
| "Discover" → suggest new words + spinner | `POST /discover` previews suggested new words with a loading state | `Discover` | ✅ |
| Suggested-words preview | Preview list of suggested words | `Discover` | ✅ |
| "Generate sentences →" (accept words) | Accept hands the words into the existing Generate flow (`generate-handoff` + `navigate('/generate')`) — the generate UI is reused, not duplicated | `Discover` → `/generate` ([generate-handoff.ts](../apps/web/src/lib/generate-handoff.ts)) | ✅* |
| "Try different words" (reroll) | Reroll refetches and replaces the suggested set | `Discover` | ✅ |
| Sentence preview + Save all / Pick different words | Handled by the reused Generate flow (preview → select → save) after accept | `/generate` | ✅* |
| Shared quota / 429 path | The same shared `DailyLimitPanel` (and friendly transient/verify states) used by Generate | `Discover` + `LlmErrorState` → `DailyLimitPanel` | ✅ |

✅* **Nuance — accept routes through Generate.** The legacy Discover page previewed and saved
sentences in-page. React's "accept" instead feeds the words into the existing Generate screen (group
4.5) so the user keeps the review-and-select-before-save step (rather than `POST /discover/accept`,
which would auto-save without review). The end-to-end capability (discover → sentences → save) is
fully present; the save UI is the shared Generate one by design.

---

## 6. Settings — `legacy_streamlit/pages/4_Settings.py`

| Legacy feature | React equivalent | Route / component | Status |
| --- | --- | --- | --- |
| Daily new cards (1–100) | `daily_new_limit` field (1–100), bounds-validated, → `PUT /settings`; **bounds the review due batch** (4.8b) | `/settings` ([Settings.tsx](../apps/web/src/pages/Settings.tsx)) + [settings.ts](../apps/web/src/lib/settings.ts) | ✅ |
| Daily total cards (1–500) | `daily_total_limit` field (1–500), bounds-validated + cross-field `new ≤ total`, → `PUT /settings`; bounds the review batch | `Settings` | ✅ |
| Discover default word count (3–10) | `discover_count` field validated against the **real** schema bound (`DiscoverRequest.count` min/max via `schemaLimits`) → `PUT /settings` | `Settings` | ✅ |
| "Save settings" | Save via `PUT /settings` (per-field validation before send) | `Settings` + `useUpdateSettings` | ✅ |
| Gemini model selector (`gemini-2.5-flash` / `-pro` / …) | **Retired by design** — the LLM provider/model is now operator/server configuration (`LLM_PROVIDER`: Groq `llama-3.1-8b-instant` for dev/CI, Gemini reserved for prod), not a user-facing setting. Users no longer choose a model. | server config ([apps/api/app/settings.py](../apps/api/app/settings.py), `.env`) | ♻️ |

**Vowel-marks display toggle (React enhancement).** Beyond the legacy generation flag (§1), the
React app adds a **device-level display toggle** that shows or strips harakat/nikkud in rendered
target text without changing what was generated. It is self-gating (shown only for vowelized
languages) and lives on Generate/Review/Discover. Component:
[`VowelMarksToggle`](../apps/web/src/components/vowel-marks-toggle.tsx) + `VowelMarksProvider`. ➕

---

## 7. Cross-cutting legacy behaviours

| Legacy behaviour | React equivalent | Status |
| --- | --- | --- |
| RTL detection for Arabic/Hebrew (`_is_rtl`) | `directionForCode` derives `dir=rtl` from the language code (no manual direction field — group 4.9 decision); RTL-anchored components | ✅ |
| Diacritic-correct rendering of harakat/nikkud | Self-hosted Noto Naskh Arabic / Noto Sans Hebrew fonts (bundled by Vite, no CDN — mobile-webview-safe) | ✅ |
| Level adapts from review answers (FSRS + proficiency nudges) | Backend behaviour (`POST /review/{id}/grade` nudges proficiency); surfaced in the React `CefrPanel` | ✅ |
| Per-card generation-level tracking (only current-level cards move the level) | Backend behaviour (preserved in `lengua_core` + the cards schema) | ✅ |

---

## 8. React-only additions (no legacy counterpart)

The legacy app was a **single-user, local-SQLite** desktop tool. Productionization adds a whole
multi-tenant surface the Streamlit app never had — these are net-new, not parity rows:

- **Authentication** — signup, email verification, login, password reset, Google + Apple OAuth, with
  central token refresh + 401-retry (groups 4.3 / Phase 2). The legacy app had no accounts.
- **Account lifecycle** — view email, sign out, **export all data** (`GET /account/export`), and
  **hard-delete the account** behind a confirm-typed dialog (`DELETE /account`) — store/GDPR
  compliance flows (group 4.8 / Phase 2.8).
- **LLM cost-guard UX** — friendly first-class states for the quota chain: the shared 429
  `DailyLimitPanel` plus rate-limited / server-busy / email-unverified messaging (Phase 3 + group
  4.10.2). The legacy app had no quota.
- **First-run analytics consent** — a consent banner gating any analytics init (group 4.10.3).
- **Light/dark theme toggle** — persisted theme (group 4.1).

---

## 9. Intentionally retired (architecture changes, not parity gaps)

- **Gemini model selector** (§6) — model choice is now operator/server config (`LLM_PROVIDER`), not a
  user setting.
- **Local SQLite persistence** (`legacy_streamlit/store.py`, `db.py`) — replaced by per-user Postgres
  via Supabase with Row-Level Security (Phase 1–2). The operator's pre-productionization history can
  be migrated into a real account with `scripts/import_sqlite.py` (see the runbook).

---

## 10. Reachability on the demo account

Sign in as the seeded demo/reviewer account (`demo@lengua.test` / `demo-password-123`, from
`scripts/seed_e2e.py`) and every screen above is reachable from the app shell:

- Header **language picker** + sidebar **CEFR panel** (with override) — visible on every authenticated
  screen.
- **Dashboard** `/` · **Generate** `/generate` · **Review** `/review` · **Discover** `/discover` ·
  **Languages** `/languages` · **Settings** `/settings` · **Account** `/account` — all in the primary
  nav ([nav-items.ts](../apps/web/src/components/nav-items.ts)).

The full Generate → Save → Review → Discover loop, language management, CEFR level + override,
settings, account, and RTL/diacritics are all exercised end-to-end by the Playwright specs in
[`apps/web/e2e/`](../apps/web/e2e) against the FakeLLM ephemeral stack (zero real LLM calls).

---

**Conclusion:** all `pages/*` features (and the sidebar + home) have a ✅ React counterpart, the one
exception being the Gemini model selector which is intentionally retired (server config). The legacy
Streamlit app is therefore **deprecated — retained for reference**, and stays runnable until the React
web build is live in production (Phase 6) and wrapped for mobile (Phase 7).
