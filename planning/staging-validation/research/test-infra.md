# Staging Validation — Test Infra Research: mock users, seed data, FSRS study flow

**Scope:** how to provision/clean up mock users + seed data for an end-to-end validation against
**LIVE staging**, and how FSRS scheduling shapes the review session ("study / continue / back").
**Date:** 2026-06-30. **Sources:** `apps/api/scripts/`, `apps/api/app/`, `apps/api/lengua_core/`,
`apps/api/tests/`, `apps/web/`, `.github/workflows/seed-staging.yml`, `planning/staging-validation.md`.

Staging targets (from `planning/staging-validation.md` + `staging_smoke.py`):
- Web `https://lengua-staging.vercel.app` → API `https://lengua-api-staging-cxiyhzhria-ew.a.run.app`
  (Cloud Run) → Supabase `rydclyotzdwcbbeyitcx` (`https://rydclyotzdwcbbeyitcx.supabase.co`).
- Demo account: `demo@lengua.test` / `demo-password-123` (the ONE seeded reviewer account).
- Staging secrets (GitHub): `SUPABASE_STAGING_URL`, `SUPABASE_STAGING_SERVICE_ROLE_KEY`,
  `SUPABASE_STAGING_DATABASE_URL` (session-pooler, IPv4). The `seed-staging` workflow maps these →
  `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` / `DATABASE_URL` that the seed scripts read.

---

## 1. Provisioning N test users with UNIQUE emails

**There is NO dedicated multi-user provisioning script today.** Only single, fixed accounts exist:

- `apps/api/scripts/seed_e2e.py` — creates ONE demo user `demo@lengua.test` (idempotent: looks it up
  by email first) + a Spanish deck + a Hebrew/RTL deck of due cards.
- `apps/api/scripts/seed_dev_user.py` — creates ONE dev user with a FIXED UUID
  `00000000-0000-0000-0000-000000000001` (`dev@lengua.test`).

**The user-creation mechanism** (reused everywhere) is the Supabase **Auth Admin API** with the
`service_role` key:
- `POST {SUPABASE_URL}/auth/v1/admin/users` with body `{email, password, email_confirm: true}`
  → returns `{id, ...}`. `email_confirm=true` lets the account log in immediately.
- The `handle_new_user` trigger on `auth.users` then auto-inserts the matching `profiles` row — so
  **never write `profiles` directly** (the seed scripts only `INSERT ... ON CONFLICT DO NOTHING` as a
  defensive backstop for partially-truncated states). `seed_e2e.ensure_demo_user` and
  `seed_dev_user.ensure_dev_auth_user` both show this. GoTrue honors an explicit `id` on admin-create
  (used by `seed_dev_user`) if you need deterministic ids.

**Canonical pattern for N unique-email users** (the closest existing analog — used by the integration
tests): `apps/api/tests/supabase_auth.py`:
- `create_confirmed_user(client, email=None, password="Test-pass-123")` — when `email` is omitted it
  generates `bootstrap-{uuid4().hex[:12]}@lengua.test` and admin-creates a **pre-confirmed** user,
  returning `CreatedUser(id, email, password)`. **This is exactly the loop to build N users** with
  guaranteed-unique emails.
- `login(client, email, password)` — password-grant `POST /auth/v1/token?grant_type=password` (anon
  key) → a real Supabase-signed ES256 access-token (JWT) for API calls.
- `delete_user(client, user_id)` — admin-delete (cleanup; see §4).

**To provision N validation users on staging you must build a small driver** (none exists):
1. Loop `create_confirmed_user` N times against `SUPABASE_STAGING_URL` with the staging service-role
   key → collect `(id, email, password)`.
2. Seed each user's cards (see §2) — either via the DB (`SUPABASE_STAGING_DATABASE_URL`) mirroring
   `seed_e2e._insert_due_card_pairs`, or via the real API as that logged-in user (generate→save).
3. Track the created ids so cleanup (§4) is reliable.
> Risk: this is net-new tooling. Parametrizing `seed_e2e.py` (email/count) or writing a `seed_users.py`
> loop is the natural home. The existing `seed-staging` workflow is **demo-only** and idempotent — it
> will not create extra users.

---

## 2. Seeding a user with SAVED, DUE cards (so "study" has something to review)

Two routes:

**A. Direct DB seed (deterministic, what `seed_e2e.py` does).**
`_insert_due_card_pairs(conn, user_id, language_id, sentences)` is the template. For each
`(sentence, translation, used_words)` it inserts **TWO** card rows:
- recognition: `front=sentence` (target), `back=translation` (English)
- production:  `front=translation` (English), `back=sentence` (target)

Each row is written with:
- `saved = true`
- `fsrs_state = Card().to_dict()` (a **fresh FSRS "new" state**, built from the `fsrs` package),
  serialized to JSONB
- `due = fsrs_dict["due"]` — a brand-new card is **due immediately (now)**
- `used_words` (jsonb array), `direction`, `language_id`, `user_id`.

> **CRITICAL:** `fsrs_state` must NOT be null. The grade endpoint returns **422** ("Card N has no FSRS
> state to grade") when `fsrs_state IS NULL`, which stalls the review loop. The due-candidate query
> (`CardsRepository.due_candidates`) requires `saved = true AND due IS NOT NULL`.

Languages are inserted idempotently via `UNIQUE (user_id, name)` + `ON CONFLICT DO NOTHING`
(`_ensure_language`). The demo seed adds Spanish (`code=es`) and a vowelized Hebrew (`code=he`,
`vowelized=true`) deck (3 sentences each → 6 cards each = 12 ES + 6 HE on staging per the
re-validation notes).

**B. Real-API seed (exercises the production seam).** As a logged-in user:
`POST /generate {language_id, words}` (returns previews) → `POST /cards/save {language_id, cards}`
(persists with `saved=true`, fresh FSRS state, due-now; the save service runs
`lengua_core.scheduler.new_card_state`). The full-loop spec (`apps/web/e2e/full-loop.spec.ts`) does
generate→save→review this way. On the ephemeral stack `LLM_PROVIDER=fake`; **against staging it is
real Groq** (cost-guard 429 possible — see risks).

Card-shaping logic lives in `lengua_core/cards.py`; the FSRS state in `lengua_core/scheduler.py`.

---

## 3. FSRS scheduling and the study / continue / back flow

### `GET /review/due?language_id=<id>` → `DueResponse { new: CardOut[], due: CardOut[] }`
Service `ReviewService.due_split` (`app/services/review.py`):
1. `CardsRepository.due_candidates(user, lang)` — saved cards with a non-null `due`.
2. Build scheduler views and call `lengua_core.scheduler.select_due_batch(views, new_limit, total_limit)`:
   - keep cards whose `due <= now`;
   - split into **new** (FSRS state has no `last_review`) vs **due** (has `last_review`);
   - sort each group **oldest-due-first**;
   - `batch = due + new[:new_limit]`, then capped at `total_limit`.
3. Re-split the returned batch back into `new` / `due` (by `is_new_card`).

**Limits:** `new_limit` default **10**, `total_limit` default **50**
(`lengua_core/config.py`: `DAILY_NEW_LIMIT` / `DAILY_TOTAL_LIMIT`, env-overridable). Per-user
overrides come from `user_settings` keys `daily_new_limit` / `daily_total_limit`
(`resolve_review_limits`), with fallback to the config defaults for missing/blank/non-numeric/non-
positive values (S9/S10 hardened server-side bounds + `daily_new_limit ≤ daily_total_limit`).

`is_new_card(card)` = the FSRS state has **no `last_review`** timestamp (fresh-generated/imported).

### "Continue / next" (advance) — `apps/web/src/pages/Review.tsx` + `src/lib/review.ts`
- The screen loads the batch ONCE (`useDueQuery`) and walks a **client-side snapshot**:
  `batch = [...due.data.due, ...due.data.new]` — **due first, then new** (the S6 fix; reverses the old
  new-first order so due reviews aren't buried if you quit mid-session). Legacy Streamlit
  (`legacy_streamlit/pages/2_Review.py`) uses the same due-first batch from `store.due_cards`.
- `index` starts at 0; `current = batch[index]`. Reveal (`revealed=true`) then grade.
- Grading calls `useGradeCard` → `POST /review/{card_id}/grade {rating}`; on success → `advance()`:
  `setRevealed(false); setIndex(i => i + 1)`. **Forward-only.**
- **Grading deliberately does NOT refetch** the due query (so the queue doesn't reshuffle mid-session).
  The batch refreshes only on remount or when new cards are saved (the `['review', ...]` key is
  invalidated by `useSaveCards`).
- When `index >= batch.length` → `SessionComplete` ("Done for today", reviewed count) with a "Check for
  more" button → `restart()` (`setIndex(0); setRevealed(false); due.refetch()`). Empty batch →
  `AllCaughtUp` empty-state.
- The session is **re-mounted per language** (`key={activeLanguageId}`) so walk position never leaks
  across a language switch.

### "Back" — IMPORTANT MISMATCH WITH THE BRIEF
There is **no in-session "back to a prior card"** in the current app. `index` only ever **increments**;
there is no decrement, no per-card history, no Undo. The same is true of the legacy Streamlit page
(`review_idx += 1` only). So:
- "Back" in practice = **navigating away** (Primary-nav links / browser back to leave Review), or
  **restarting** the session via "Check for more" (which resets `index=0` and refetches a fresh batch).
- A validation that expects "back returns to a prior card" cannot be satisfied by the current Review
  UI. A test can only: (a) re-enter the session (remount → index 0), or (b) use browser back to leave
  Review and return. **Flag this to whoever owns the test plan.**

### Reveal + grading buttons (FSRS states relevant to a session)
- **Card states:** *new* (fresh `Card()`, no `last_review`, due=now) · *due* (reviewed, has
  `last_review`, due ≤ now) · *not-yet-due* (due > now → excluded from the batch entirely).
- **Directions** (`lengua_core/cards.py`; `CardOut.direction`): *recognition* (prompt = target
  sentence "Read and understand", reveal "Show translation", answer = English plain text) and
  *production* (prompt = English "Build the sentence", reveal "Show answer", answer = the target
  sentence with **tap-a-word** explanations). A null/legacy `direction` is treated as recognition.
- **Ratings 1..4 = Again / Hard / Good / Easy**, LOCKED colours **red / orange / blue / green**
  (`RATINGS` in `src/lib/review.ts`; keyboard digits 1–4; `space`/`enter` reveals). Buttons carry
  `data-rating={value}` and live in a `role="group" aria-label="Rate this card"`.
- Grade endpoint `POST /review/{card_id}/grade {rating:1..4}` → FSRS reschedule + review-log row +
  proficiency nudge (one atomic commit), returns `GradeResponse {card_id, due, score, score_changed}`.
  `apply_rating` runs `fsrs.Scheduler.review_card`.
- **Non-depleting tip:** grade with **"Again"** to keep a card due (the full-loop e2e and staging
  walkthrough do this so repeated runs against the shared demo deck never deplete it). Good/Easy push
  `due` far into the future and remove the card from subsequent batches.

---

## 4. Reset / delete test users and their data (keep staging clean)

**A. `DELETE /account` (the GDPR right-to-erasure path; deletes the CALLER only).**
`app/routers/account.py` + `app/services/account.py`. Target user comes **solely from the verified JWT**
(`current_user`) — no user-id param, so a caller can only delete themselves. Two-step erasure:
1. Delete the `profiles` row on a **privileged, RLS-bypassing** session → cascades
   `languages / cards / reviews / proficiency / user_settings / llm_usage` via the
   `… → profiles(id) ON DELETE CASCADE` FKs. (Domain data erased FIRST — the S1 fix — so a later
   auth-delete failure never orphans content.)
2. Auth Admin `DELETE {SUPABASE_URL}/auth/v1/admin/users/{id}` with body
   `{should_soft_delete: false}` (explicit hard delete; revokes refresh tokens).
Idempotent (re-deleting an absent profile / gone auth user is a no-op). Returns **204** on success,
**502** on a partial failure (caller retries to completion — never a false 204). Requires the
service-role key configured server-side. After step 2 the refresh tokens are revoked and the access
token simply expires.

**B. Admin script path (no JWT; what test cleanup uses).**
`tests/supabase_auth.py::delete_user(client, user_id)` → `DELETE {SUPABASE_URL}/auth/v1/admin/users/{id}`
with the service-role key; treats 200/204/404 as success (used in `finally` so test users never leak
into `auth.users`, which conftest does NOT truncate). **Migration `0006`
(`20260630_0006_profiles_auth_users_fk.py`) added `profiles.id → auth.users(id) ON DELETE CASCADE` and
it is live + `validated=true` on staging** — so an admin **auth-delete now also cascades** all domain
data. Therefore, to clean up N created users, loop `delete_user` over the ids returned by
`create_confirmed_user`. (Belt-and-suspenders: call `DELETE /account` as each user, or admin-delete by
id — either fully erases given 0006 is live.)

**Pre-delete verification / inspection:** `GET /account/export` returns the full bundle (profile,
languages, cards, reviews, proficiency, settings) for the caller — useful to assert seed shape before a
run and emptiness conceptually after (the user is gone post-delete, so verify cascade via a DB count or
the CI erasure integration test `tests/test_account_delete.py`).

> The existing `staging_smoke.py` is **non-destructive by construction** — it never calls
> `DELETE /account` and never grades a card; its only write is a uniquely-named throwaway language
> (`zz-smoke-<ts>`) it immediately deletes. Use it as the read-only-probe model; destructive
> create/seed/delete must be a separate, explicitly-cleaned driver.

---

## Concrete selectors / endpoints a validation test can target

**API:** `GET /review/due?language_id=` · `POST /review/{card_id}/grade {rating:1..4}` ·
`POST /generate` · `POST /cards/save` · `POST /discover` · `POST /explain` · `GET /account/export` ·
`DELETE /account` · `GET /me` · `GET /languages` · `POST /languages` · `DELETE /languages/{id}` ·
`GET /settings` · `PUT /settings`.
**Supabase Auth:** `POST /auth/v1/token?grant_type=password` (login, anon key) ·
`POST /auth/v1/admin/users` (create, service_role) · `DELETE /auth/v1/admin/users/{id}` (delete) ·
`GET /auth/v1/admin/users?page=&per_page=` (lookup by email).

**Web (Playwright):** `data-testid="review-content"`; counts header `data-testid="review-counts"`
(text like `"10 new · 2 due"` and "Card N of M"); progress bar `role="progressbar"
aria-label="Review progress"`; answer block `data-testid="card-answer"`; reveal button name
`/^Show (answer|translation)$/`; rating buttons `getByRole('button', { name: /^(Again|Hard|Good|Easy)/ })`
or `[data-rating="1".."4"]` within `role="group" aria-label="Rate this card"`; empty/all-caught-up
`data-testid="empty-state"`; primary nav `getByRole('navigation', { name: 'Primary' })`; login form
labels `Email` / `Password` + button `Log in`; dashboard heading `Dashboard`. Pre-seed analytics
consent (`localStorage 'lengua.analytics-consent' = 'denied'`) to avoid the fixed banner intercepting
clicks (see `e2e-staging/fixtures.ts`).

## Key files
- `apps/api/scripts/seed_e2e.py` — demo user + due-card pairs (the seed template).
- `apps/api/scripts/seed_dev_user.py` — fixed-UUID dev user pattern.
- `apps/api/tests/supabase_auth.py` — `create_confirmed_user` (unique-email N-user pattern) + `login` + `delete_user`.
- `apps/api/lengua_core/scheduler.py` — `new_card_state`, `is_new_card`, `select_due_batch`, `apply_rating`.
- `apps/api/app/services/review.py` + `app/routers/review.py` — due_split + grade.
- `apps/api/app/services/account.py` + `app/routers/account.py` — export + two-step hard delete.
- `apps/web/src/pages/Review.tsx` + `apps/web/src/lib/review.ts` — study/advance UI (forward-only).
- `apps/api/scripts/staging_smoke.py` — non-destructive endpoint sweep (reference for safe probing).
- `apps/web/e2e/full-loop.spec.ts`, `apps/web/e2e-staging/{fixtures,screens}.spec.ts` — flow + selectors.
- `.github/workflows/seed-staging.yml` — manual demo-only staging seed (env mapping).
