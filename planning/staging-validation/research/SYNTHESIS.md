# Staging-validation synthesis — for the planner

Consolidates the six research notes in this folder (`web-learning-flow.md`, `auth.md`, `e2e.md`,
`staging-config.md`, `backend-api.md`, `test-infra.md`) into the decisions a planner needs to write
an end-to-end **live-staging** validation plan plus runnable Playwright specs. Source facts were
spot-verified against `apps/api/tests/supabase_auth.py`, `apps/web/e2e-staging/fixtures.ts`,
`apps/web/src/pages/Languages.tsx`, and `apps/web/src/components/language-picker.tsx`.

**Staging targets:** web `https://lengua-staging.vercel.app` → API
`https://lengua-api-staging-cxiyhzhria-ew.a.run.app` (Cloud Run, `--max-instances=1`) → Supabase
`rydclyotzdwcbbeyitcx`. Demo account `demo@lengua.test` / `demo-password-123` (seeded, ~12 ES + 6
HE/RTL due cards). LLM provider on staging = **Groq `llama-3.1-8b-instant` (free tier)**.

---

## THE SEVEN BLOCKERS — decisive answers

### Blocker 1 — Can an automated test register + confirm + log in a BRAND-NEW user on staging?

**Through the public sign-up form: NO.** `supabase/config.toml` has `enable_confirmations = true`.
Public sign-up (`POST /auth/v1/signup`) returns **no session**, the Signup page shows a "Check your
email" notice, and a login before the (uncatchable) email link fails with GoTrue
`email_not_confirmed`. Even if a token were obtained, the backend's first cost-guard gate returns
**403 `email_unverified`**. There is no programmatic inbox in the repo, so the public path is a hard
dead-end for automation. Do not attempt it.

**Via the Supabase Auth Admin API: YES — this is the supported mechanism.** With the staging
**service-role** key:

```
POST {SUPABASE_STAGING_URL}/auth/v1/admin/users
  headers: apikey: <service_role>, Authorization: Bearer <service_role>
  body:    {"email": "...", "password": "...", "email_confirm": true}
```

`email_confirm: true` creates a **pre-confirmed** user that can log in immediately; the
`handle_new_user` trigger auto-creates its `profiles` row (never write `profiles` directly). Then
log in with the **anon** key:

```
POST {SUPABASE_STAGING_URL}/auth/v1/token?grant_type=password
  headers: apikey: <anon>
  body:    {"email": "...", "password": "..."}   →  { access_token, refresh_token, ... }
```

**Ready-made helpers exist** — reuse, do not reinvent — in `apps/api/tests/supabase_auth.py`:
- `create_confirmed_user(client, email=None, password="Test-pass-123")` → admin-creates a
  pre-confirmed user; with `email=None` it generates a **guaranteed-unique** `bootstrap-{uuid4 hex}@lengua.test`.
  Returns `CreatedUser(id, email, password)`. **This is the exact loop to mint N validation users.**
- `login(client, email, password)` → real ES256 `access_token`.
- `delete_user(client, user_id)` → admin hard-delete (cleanup; treats 200/204/404 as success).
- `get_user(client, user_id)` → assert `email_confirmed_at`.

These wrappers read `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` / `SUPABASE_ANON_KEY` from env, so
point them at staging by exporting the `SUPABASE_STAGING_*` secret values.

**Getting that admin-created user into a *browser* session** (for Playwright UI flows): two options —
1. **Drive the real login form** (simplest, recommended): `goto('/login')`, fill `Email` +
   `Password (exact)`, click `Log in`, wait for the `Dashboard` heading. Login uses the anon key; no
   service-role needed in the browser. This is exactly what `e2e-staging/fixtures.ts::login()` does.
2. **Inject the session** via Playwright `addInitScript`/storageState by writing the
   `sb-rydclyotzdwcbbeyitcx-auth-token` localStorage key from a password-grant response (supabase-js
   stores the session in **localStorage, not cookies**; `persistSession`/`autoRefreshToken` on). More
   fragile; only worth it to skip the login round-trip for pure-API drivers.

**Recommended default & fallback hierarchy:**
- **Default for read-only / structure specs:** use the **existing pre-confirmed demo account** — zero
  setup, no secret (login is anon-key). This is what every staging suite already uses.
- **For isolated / fresh / multi-user / destructive flows:** admin-create per-test pre-confirmed
  users with `SUPABASE_STAGING_SERVICE_ROLE_KEY` (a GitHub secret — never commit), and clean them up.
- **Caveat:** building the N-user driver is **net-new tooling** — no multi-user seed script exists
  today (`seed_e2e.py` is demo-only and idempotent). The natural home is a new
  `apps/api/scripts/seed_users.py` looping `create_confirmed_user` + tracking ids for cleanup.

### Blocker 2 — Does generate cost real LLM money / hit the cost guard, and how to avoid it?

**Dollar cost on staging ≈ $0.** Provider is Groq free tier (no card on file). The *only* way to a
real bill is flipping staging to Gemini (prod-only) — don't. There is no surprise-bill path while
`LLM_PROVIDER=groq`.

**But every `POST /generate` / `/discover` / `/discover/accept` / `/explain` (cache-miss) makes a
REAL Groq call and counts against the cost guard.** Limits in effect (code defaults; `app/settings.py`,
gate order email-verified → rate-limit → daily-cap → global-budget):

| Limit | Value | Hit → |
| --- | --- | --- |
| Rate limit (per user, all LLM kinds, rolling 60s) | **10/min** | 429 `rate_limited` + `Retry-After` |
| Generate daily cap (per user) | **20/day** (default) | 429 `daily_cap_reached` kind=generate |
| **Day-0 new-account generate cap** | **5** on the signup UTC day | 429 `daily_cap_reached` |
| Discover daily cap | 10/day | 429 `daily_cap_reached` kind=discover |
| Explain daily cap | 50/day (cache-miss only) | 429 `daily_cap_reached` |
| Concurrency | **4 in-flight** | 503 `server_busy` + `Retry-After: 1` |
| **Global daily budget (ALL users)** | **1000 successful calls/day** | 429 `daily_limit_reached` until UTC rollover |
| Words per `/generate` | 30 | 422 (hard reject, pre-provider) |

Plus Groq's own free-tier ~30 RPM / ~1K RPD. Increment-on-success only (blocked/failed calls don't
burn quota). Discover/explain **cache hits are free and uncounted** (discover reuse window 300s;
explain hits the card's stored note) — send `fresh:true` (discover) or a novel word (explain) to
force a counted call.

**How to avoid paid usage / throttling in a multi-user run:**
- **Prefer LLM-free specs.** Structure/read-only assertions (form renders, deck or empty-state,
  nav/headings) trigger **zero** LLM — this is how `e2e-staging/*` stays free. Make the bulk of the
  validation LLM-free.
- **When you must generate:** keep word lists tiny (1 word), throttle to respect 10/min, honor
  `Retry-After`, distribute across **distinct** users (per-user caps), and stay under the global
  1000/day. Grade with **"Again"** so decks never deplete.
- **Treat 429/503 as expected/PASS** on LLM probes (the guard firing is correct behavior — exactly
  what `staging_smoke.py` does). Don't fail a validation because the guard worked.
- **For heavy multi-user *generation* load, do NOT use live staging** — use the FakeLLM ephemeral
  stack (the Phase-3 zero-paid-usage load test did this). You cannot swap staging's provider at runtime.
- API smoke supports `--no-llm` / `SMOKE_INCLUDE_LLM=0` to skip the real-Groq probes entirely.

### Blocker 3 — Can scenarios run in PARALLEL against the single shared staging env, and how many?

**Read-only / structure-only scenarios: YES, safely, fully parallel.** `e2e-staging` already sets
`fullyParallel: true`; all specs log in independently (separate browser contexts) as the **same**
demo user, mutate nothing, and trigger no LLM. Bounded only by Cloud Run `--concurrency=40` and
cold-start latency. Practical: a handful to a couple dozen workers is fine.

**Real-LLM scenarios: parallelize ONLY across DISTINCT users, and keep the count low.** The rate
limiter, discover cache, global-budget kill-switch, and concurrency semaphore are **per-process /
in-process** and staging is a **single instance** (`--max-instances=1`), so they are globally
accurate:
- Parallel real-LLM work **as the same user** will 429 itself on the 10/min + per-user caps.
- Parallel real-LLM work **as distinct pre-confirmed users** each gets its own per-user budget, so it
  scales — but is still capped by **concurrency 4** (5th concurrent provider call → 503) and the
  **global 1000/day** budget shared by everyone.
- **Recommendation:** for real-LLM flows run **≤3–4 concurrent users**, each issuing few generate
  calls with throttling; for read-only flows run as many workers as you like. A runaway parallel
  generate loop can trip the **project-wide** `daily_limit_reached` for all staging users until UTC
  midnight — bound total successful calls well under 1000.

### Blocker 4 — The precise, ordered end-to-end happy-path (2+ languages)

Pre-step (every run): set `localStorage['lengua.analytics-consent'] = 'denied'` via `addInitScript`
before the first navigation, so the bottom consent banner can't intercept clicks.

1. **Land signed-out.** `goto('/')` → `RequireAuth` redirects to `/login` (AuthLayout, brand
   "Lengua"). Assert URL `/login`.
2. **Log in.** `getByLabel('Email').fill(email)`; `getByLabel('Password', {exact:true}).fill(pw)`;
   `getByRole('button', {name:'Log in'}).click()`. The form does **not** navigate — assert success by
   waiting for `getByRole('heading', {name:'Dashboard'})` (session flip + `RedirectIfAuthed` lands `/`).
   (Brand-new user variant: provision via admin API first — see Blocker 1 — then log in here.)
3. **Open Languages.** Sidebar `getByRole('navigation',{name:'Primary'}).getByRole('link',
   {name:'Languages'}).click()`; wait heading "Languages".
4. **Add language A + set its CEFR starting level.** In the "Add a language" card:
   `getByLabel('Name').fill('Spanish')`; optionally `getByLabel('Code (optional)').fill('es')`;
   `getByLabel('Starting level').selectOption('B1')`; click `getByRole('button',{name:'Add language'})`.
   Result: toast "Language added", a row with `aria-label="Remove Spanish"`, and A is **auto-selected
   active**. A non-A1 band issues a follow-up `PUT /proficiency/{id}`.
5. **Confirm A's CEFR.** Sidebar `getByRole('region',{name:'Proficiency level'})` →
   `getByTestId('cefr-band')` shows the chosen band (e.g. "B1") with a colored progress bar.
6. **Enter vocabulary words.** Sidebar → "Generate" (`getByTestId('generate-content')`). Fill
   `getByLabel('Words', {exact:true})` (one word/phrase per line or comma-separated). Use **timestamp-
   unique words** so repeat runs never collide on the shared deck. Counter reads "N / 30 words".
7. **Generate.** Click `getByRole('button',{name:'Generate'})` → "Generating…" → `POST /generate`
   returns a recognition+production pair per sentence (review-&-save panel).
8. **Save the flashcards.** In the "Review & save" panel (selected by default), click `getByRole(
   'button',{name:/Save \d+ sentences?/i})` → `POST /cards/save` persists both directions, due-now.
   Toast "Cards saved"; panel becomes "Saved N cards" + "Generate more" / link "Review now".
9. **Study A — recognition card.** Sidebar → "Review" (`getByTestId('review-content')`).
   `getByTestId('review-counts')` shows "N new · N due" / "Card X of Y";
   `role="progressbar" aria-label="Review progress"`. On a recognition card, reveal via
   `getByRole('button',{name:'Show translation'})` **or press Space/Enter** → `getByTestId('card-answer')`
   (plain English). This is the "continue/reveal" action.
10. **Rate → advance (the "next" action).** `role="group" aria-label="Rate this card"` exposes
    **Again / Hard / Good / Easy** (`data-rating="1".."4"`). Click **"Again"** (or press 1) → `POST
    /review/{id}/grade` → **advances to the next card**. (Use "Again" so the deck never depletes.)
11. **Study A — production card + tap-a-word.** On a production card the prompt is "Build the sentence
    in <Lang>"; reveal "Show answer"; the revealed answer is tappable — each word is
    `button[aria-haspopup="dialog"]`; click one → `getByTestId('word-popover')`
    (`role="dialog" aria-label="Explanation of <word>"`) via `POST /explain`; close via
    `aria-label="Close explanation"` / Escape. Then rate to advance.
12. **"Back" — IMPORTANT.** There is **no in-session back-to-a-prior-card** control; Review is a
    forward-only walk (`index` only increments; legacy Streamlit too). "Back" in practice =
    **browser back / navigate away via Primary nav**, or **restart** the session at end via "Check for
    more" (`SessionComplete`, resets index 0 + refetch). The plan must NOT assert returning to a prior
    card — exercise "back" as nav-away-and-return or session restart only.
13. **End of A's batch.** Exhausted snapshot → heading "Done for today" (`SessionComplete`,
    buttons "Check for more" / "Generate more"). Empty batch → `getByTestId('empty-state')`
    "You're all caught up".
14. **Add language B.** Back to "Languages"; add a second language (e.g. Name "Hebrew", Code "he",
    Starting level "A1"; check "Include vowel marks" → the code becomes REQUIRED). B auto-becomes active.
15. **Switch BETWEEN languages (the multi-language pivot).** Header
    `getByLabel('Active language').selectOption({label:'Spanish'})` re-scopes every language-scoped
    screen (re-keys TanStack queries, re-mounts Generate/Review/Discover via `key={activeLanguageId}`).
    Assert the CEFR `getByTestId('cefr-band')` flips to A's band (e.g. B1), then switch back to B and
    assert it flips to B's band (A1). Selection persists per-user in localStorage.
16. **Study B.** With B active, repeat steps 6–11 for B (generate → save → review). For an RTL B
    (Hebrew/`he`), assert `getByTestId('review-content')` has `dir="rtl"`, the Noto Sans Hebrew font is
    loaded, and `getByRole('switch',{name:'Show vowel marks'})` toggles nikkud.
17. **(Optional) change CEFR manually.** `getByLabel('Override level').selectOption('C1')` →
    `getByTestId('cefr-band')` becomes "C1" (`PUT /proficiency`).
18. **Discover.** Sidebar → "Discover" (`getByTestId('discover-content')`). Set
    `getByLabel('How many words')` / `getByLabel('Topic (optional)')`; click "Discover" →
    `getByTestId('discover-suggestions')`. "Use these words" hands them to Generate (pre-fills the
    word form, navigates `/generate`); "Try different words" rerolls (`fresh:true`).
19. **Settings.** Sidebar → "Settings": edit `getByLabel('Daily new cards')` (1–100),
    `getByLabel('Daily total cards')` (1–500, must be ≥ daily new), `getByLabel('Discover word count')`;
    click "Save settings" → `PUT /settings`, toast "Settings saved".
20. **Account + logout.** Sidebar → "Account": `getByTestId('account-email')`; optionally "Export my
    data" (downloads `lengua-export.json`); click "Sign out" (or header `UserMenu` "Sign out") →
    `SIGNED_OUT` event → `RequireAuth` redirects to `/login`. Assert `/login`.
21. **Log back in.** Repeat step 2 with the same creds → "Dashboard" heading. (Persisted active
    language + decks survive.)
22. **(Optional, DESTRUCTIVE — throwaway users only) Delete account.** Account → "Delete account" →
    `role="dialog"` "Delete your account?"; `getByLabel(/Type .* to confirm/).fill('delete my account')`
    → confirm "Delete account" enabled → `DELETE /account` (204; 502 on partial = retryable). **Never
    run against the demo account.** After delete the user/auth row is gone (cascade via migration 0006).

### Blocker 5 — Concrete selectors that EXIST vs MISSING

**EXIST and are reliable today (all driven by the current suites):**
- **Auth:** `getByLabel('Email')`, `getByLabel('Password',{exact:true})`,
  `getByLabel('Confirm password')`, buttons `Log in` / `Create account` / `Send reset link` /
  `Update password`, heading `Check your email`, error `role="alert"`, `Resend verification email`.
- **Shell/nav:** `getByRole('navigation',{name:'Primary'}).getByRole('link',{name:<Screen>})` for
  Dashboard/Generate/Review/Discover/Languages/Settings/Account; per-screen `getByRole('heading',{name})`.
- **Language switch:** `getByLabel('Active language')` (native `<select>`) `.selectOption({label})` —
  **the robust switch path.** Header `UserMenu` "Sign out".
- **CEFR:** `getByRole('region',{name:'Proficiency level'})`, `getByTestId('cefr-band')`,
  `getByLabel('Override level')`, `getByLabel('Starting level')`.
- **Add/remove language:** `getByLabel('Name')`, `getByLabel('Code (optional)')`/`'Code'`,
  `getByLabel('Starting level')`, checkbox "Include vowel marks", button `Add language`; remove
  trigger `aria-label="Remove <name>"`, `role="dialog"` "Remove <name>?", buttons Cancel/Remove.
- **Generate:** `getByTestId('generate-content')`, `getByLabel('Words',{exact:true})`, button
  `Generate`, checkbox `aria-label="Select all sentences"`, per-sentence
  `aria-label="Save this card — <translation>"`, button `/Save \d+ sentences?/i`.
- **Review:** `getByTestId('review-content')`, `getByTestId('review-counts')`,
  `role="progressbar" aria-label="Review progress"`, reveal `/^Show (answer|translation)$/`,
  `getByTestId('card-answer')`, `role="group" aria-label="Rate this card"` + buttons
  `/^(Again|Hard|Good|Easy)/` / `[data-rating="1".."4"]`, `button[aria-haspopup="dialog"]`,
  `getByTestId('word-popover')`, `aria-label="Close explanation"`, `getByTestId('empty-state')`.
- **Discover:** `getByTestId('discover-content')`, `getByLabel('How many words')`,
  `getByLabel('Topic (optional)')`, button `Discover`, `getByTestId('discover-suggestions')`, button
  `Use these words`.
- **Settings:** `getByLabel('Daily new cards')`, `getByLabel('Daily total cards')`,
  `getByLabel('Discover word count')`, button `Save settings`.
- **Account:** `getByTestId('account-email')`, buttons `Export my data` / `Sign out` /
  `Delete account`, `getByLabel(/Type .* to confirm/)`, phrase `delete my account`.
- **RTL:** `getByRole('switch',{name:'Show vowel marks'})`, `.font-hebrew` / `.font-arabic`,
  `dir="rtl"` on the content section.

**MISSING / fragile — recommend adding to `apps/web` for robust automation (none block the plan; all
have a working role/label/text fallback today):**
1. **Languages list rows have no stable selector.** `src/pages/Languages.tsx` renders each row name as
   a bare `<button>` with text only — switching active via a row, or asserting the "active" tag,
   relies on matching the language *name string*, which also appears in the picker `<option>` and the
   page. Add `data-testid="language-row"` (or `data-language-id={id}`) on the `<li>`/button and a
   testid on the "active" marker. (Mitigation: prefer the header picker `getByLabel('Active language')`
   to switch — it is unambiguous.)
2. **Success toasts have no stable testid.** "Language added", "Cards saved", "Settings saved",
   "Saved N cards" are matched by copy, coupling tests to wording. Add a `data-testid` (or a stable
   `role="status"` named region) on the toast.
3. **No authenticated-shell marker.** Logged-in state is asserted only via the `Dashboard` heading
   (which also couples to the landing route). Add `data-testid="app-shell"` to `AppLayout` so specs
   can assert "authenticated" independent of which page renders.
4. **Per-page route markers.** Only Generate/Review/Discover expose a content-section testid;
   Dashboard/Languages/Settings/Account are identified by heading text only. Optional: a page-level
   `data-testid` per screen for resilience to copy changes.
5. Not addable/testable on staging by default: **Word-of-the-Day** is feature-flag-gated **off**
   (renders nothing) — leave it out of the happy path.

### Blocker 6 — Playwright primary; is Selenium worth it?

**Use Playwright as the primary (and only) browser driver.** It is already the entire browser-test
stack — three suites, **zero** Selenium/Cypress/Puppeteer anywhere — and a staging-ready config
exists (`apps/web/playwright.staging.config.ts`, no `webServer`, points at the live origin, 1 retry,
90s timeout for cold Cloud Run). The shared `login`/consent fixtures and the full selector vocabulary
are Playwright-native. New staging specs drop straight into `apps/web/e2e-staging/`.

**Selenium adds nothing here and should NOT be introduced.** The only argument for it would be
cross-browser coverage — but that is already a first-class Playwright capability: add `firefox` and
`webkit` entries to the `projects` array in `playwright.staging.config.ts` (currently chromium-only)
and the same specs run across all three engines. Selenium would instead duplicate the auth/consent/
selector helpers, run slower, lack trace/screenshot-on-failure, and add a second toolchain for no new
coverage. **Recommendation: stay 100% Playwright; if broader browser coverage is desired, add the
`firefox`/`webkit` projects.**

### Blocker 7 — Highest-risk areas most likely to FAIL during validation

1. **Rate limit (10/min) trips first.** A fast script hitting generate/discover/explain will
   `429 rate_limited` before any per-day cap — the single most likely false failure. Throttle and
   honor `Retry-After`.
2. **Day-0 generate cap = 5.** A *freshly admin-created* user can only generate 5 times on its signup
   UTC day → `429 daily_cap_reached`. Use the established demo user for generate-heavy flows, or
   expect/accept the cap on fresh users.
3. **Email-unverified 403.** Any attempt to use a public-signup (unconfirmed) user dead-ends on
   `403 email_unverified` at the first LLM call. Only admin-confirmed (`email_confirm:true`) or the
   seeded demo user can generate/discover/explain.
4. **Cloud Run cold start / single instance.** `--min-instances=0 --max-instances=1`: the first
   request after idle is slow and one bad request can stall the lone instance. The staging config's
   90s timeout + 1 retry exists for exactly this — keep them; don't tighten timeouts.
5. **Shared single demo deck + single process.** Parallel real-LLM work as the same user collides on
   per-user caps and the in-process rate limiter; grading **Good/Easy** pushes cards out of future
   batches (deck depletion). Always grade **"Again"** and keep parallel real-LLM to distinct users.
6. **`DELETE /account` is irreversible.** Run it ONLY against throwaway admin-created users, never the
   demo account; a partial failure is a retryable **502**, not a 204 — handle/retry, don't treat 502
   as a hard fail.
7. **Global 1000/day kill-switch is project-wide.** A runaway multi-user generate loop trips
   `daily_limit_reached` for **every** staging user until UTC rollover. Bound total successful LLM
   calls well under 1000.
8. **N-user provisioning is net-new tooling.** No multi-user seed script exists; you must build a
   small `create_confirmed_user` loop + reliable cleanup (leaked users pollute `auth.users`, which no
   conftest truncates — though migration 0006's `profiles→auth.users ON DELETE CASCADE` makes admin-
   delete fully erase domain data).
9. **JWKS/ES256 dependency.** Staging signs tokens ES256; the API needs `SUPABASE_JWKS_URL` or it
   401s every real token. Verified working, but a deploy/config regression here breaks all auth.
10. **"Back to a prior card" is impossible in Review** (forward-only). The plan must not assert it;
    model "back" as nav-away/return or session restart (see Blocker 4 step 12).
11. **Copy-coupled assertions are brittle** (toasts, button labels) — minimize asserting exact copy;
    prefer roles/labels/testids and the additions in Blocker 5.
12. **Cache hits are free & uncounted.** A repeat `/discover` (within 300s) or repeat `/explain` makes
    no provider call and no quota increment — a spec asserting a counter bump must send `fresh:true` /
    a novel word.

---

## Recommended validation shape (for the planner)

- **Two layers, both Playwright-or-Python, both against live staging:**
  1. **UI happy-path (Playwright, `apps/web/e2e-staging/`):** the Blocker-4 flow. Run the bulk
     **LLM-free / read-only** as the **demo user** (fully parallel, safe). Gate the few LLM-touching
     steps (generate/save/review/discover) behind an opt-in env (e.g. `STAGING_INCLUDE_LLM=1`),
     throttled, words timestamp-unique, grade "Again", and treat 429/503 as acceptable.
  2. **API contract sweep (Python `httpx`, extend `apps/api/scripts/staging_smoke.py` model):**
     non-destructive endpoint coverage as the demo user; LLM probes gated and 429/503-tolerant.
- **Multi-user / fresh-user / destructive scenarios:** a **separate, explicitly-cleaned driver** that
  admin-creates pre-confirmed users (`create_confirmed_user`), runs the flow, and `delete_user`s them
  in `finally`. Keep concurrent real-LLM users to ≤3–4 and total successful calls well under the
  global 1000/day. This driver requires `SUPABASE_STAGING_SERVICE_ROLE_KEY`.
- **Cross-browser (optional):** add `firefox`/`webkit` projects to `playwright.staging.config.ts`.
- **Run commands (reference):**
  `cd apps/web && PLAYWRIGHT_TEST_BASE_URL=https://lengua-staging.vercel.app pnpm test:e2e-staging`;
  `cd apps/api && STAGING_SUPABASE_ANON_KEY=<anon> uv run python scripts/staging_smoke.py`
  (`SMOKE_INCLUDE_LLM=0` to skip real-Groq probes). `DEMO_EMAIL`/`DEMO_PASSWORD` override the creds.
