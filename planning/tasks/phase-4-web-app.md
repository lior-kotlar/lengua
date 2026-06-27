# Phase 4 — React web app (parity with Streamlit)

> **Effort:** L  ·  **Depends on:** Phases 1–3 complete (API core, auth/multi-tenancy, quota gate)  ·  **Unlocks:** Phase 7 (Capacitor mobile wraps this web build)
> **Source:** roadmap Phase 4 (../02-roadmap.md) · deep dive (../04-frontend-mobile.md)
> The per-PR quality gate (../09-testing-quality.md) applies to EVERY task below: each lands via a PR that is 100% green + ≥80% coverage (backend & frontend) + Playwright E2E. A task is not done until its tests keep coverage ≥80%.

**Goal:** a signed-in browser user can do everything the legacy Streamlit app did — generate, save, review, discover, manage languages, see/override their CEFR level, and manage their account — entirely against the FastAPI backend.

**Status legend:** [ ] todo · [~] in progress · [x] done · [!] blocked

---

## 4.1 — App shell & foundations  ·  M

_Context: the Vite/React/TS skeleton, routing, server-state, Supabase client, styling, and theming that every screen builds on. Everything here is mobile-webview-safe so Capacitor (Phase 7) can wrap it unchanged._

- [x] **4.1.1** Scaffold `apps/web` with Vite + React + TypeScript; strict `tsconfig`, ESLint + Prettier, `pnpm dev`/`build`/`preview` scripts; commit a placeholder route that renders.
      verify: `pnpm --filter web build` succeeds and `pnpm --filter web tsc --noEmit` reports zero errors in CI.
- [x] **4.1.2** Add Tailwind CSS + shadcn/ui; wire the Tailwind config, base layer, and `cn` helper; install Button/Card/Input/Dialog/Toast primitives used downstream.
      verify: a shadcn `<Button>` renders in a Vitest + Testing Library smoke test (`pnpm --filter web test`) and Tailwind utility classes appear in the built CSS.
- [x] **4.1.3** Configure light/dark theming with a `ThemeProvider` + CSS variables (shadcn tokens) and a persisted user toggle.
      verify: vitest test toggles theme and asserts `document.documentElement` gains the `dark` class and the choice survives a remount (localStorage read).
- [x] **4.1.4** Set up `react-router` with the route tree (auth routes vs. authenticated app routes) and a shared app layout (header/sidebar/content slots).
      verify: vitest renders the router at `/login` and `/` (memory router) and asserts the correct screen mounts for each path.
- [x] **4.1.5** Add TanStack Query with a configured `QueryClient` (retry/staleTime defaults), `QueryClientProvider`, and React Query Devtools in dev only.
      verify: vitest renders a component using `useQuery` against a mocked fetch and asserts it transitions loading → success.
- [x] **4.1.6** Initialize `supabase-js` client from `VITE_SUPABASE_URL` / `VITE_SUPABASE_ANON_KEY` env vars; document required env in `apps/web/.env.example`.
      verify: app boots with the example env and `pnpm --filter web build` fails fast with a clear error when a required `VITE_*` var is missing (tested via a config unit test). _(Reconciliation: Vite statically inlines build-time env, and the CI build/E2E jobs intentionally build env-less so the home smoke renders — so the fail-fast is enforced at config-load / first Supabase use via `readEnv()` (clear error naming the missing var), proven by the `env.test.ts` config unit test, rather than by literally failing `vite build`.)_

## 4.2 — Typed API client  ·  S

_Context: the OpenAPI-generated client from `packages/api-types` is the single typed seam between web and FastAPI; everything calls the backend through it (Supabase is auth-only)._

- [x] **4.2.1** Wire `packages/api-types` codegen into the web build: a `pnpm gen:api` script that regenerates the TS client from the backend OpenAPI schema, plus a CI check that the committed types are up to date.
      verify: `pnpm gen:api` produces no git diff in CI when run against the current `apps/api` OpenAPI schema (drift check fails the PR if stale).
- [x] **4.2.2** Build a thin typed `apiClient` wrapper around the generated client that injects `Authorization: Bearer <token>`, sets the API base URL from env, and parses typed responses/errors.
      verify: vitest asserts the wrapper attaches the bearer header from the current session and surfaces a typed error object for a non-2xx response.

## 4.3 — Auth screens & session handling  ·  M

_Context: signup is required (no guest mode); email verification, password reset, and Google + Apple OAuth must all work, with token refresh and 401-retry handled centrally so screens never deal with raw tokens._

- [x] **4.3.1** Sign-up screen (email + password) calling supabase-js, with validation and an "check your email to verify" confirmation state.
      verify: vitest mocks `supabase.auth.signUp`, submits the form, and asserts the verification-notice state renders; Playwright (LLM-stubbed ephemeral stack) signs up a fresh email and lands on the verify-notice screen.
- [x] **4.3.2** Log-in screen (email + password) with error states for bad credentials and unverified email, plus a "forgot password?" link.
      verify: Playwright logs in the seeded demo account against the ephemeral stack and reaches the authenticated home route; vitest asserts a bad-credentials error message renders.
- [x] **4.3.3** Email-verification landing route that consumes the Supabase verification redirect and routes the user into the app (or shows a resend action on failure).
      verify: vitest renders the route with a mocked verified session and asserts redirect to home; with an error token it asserts the resend-verification CTA appears.
- [x] **4.3.4** Password-reset flow: request-reset screen + reset-with-token screen, both via supabase-js.
      verify: vitest mocks `resetPasswordForEmail` and `updateUser`, drives both screens, and asserts success/error states; Playwright walks the request step and asserts the confirmation copy.
- [x] **4.3.5** Google + Apple OAuth buttons wired to `supabase.auth.signInWithOAuth` with correct redirect URLs (web origin), shown on both sign-up and log-in.
      verify: vitest asserts each button calls `signInWithOAuth` with the right provider and redirect URL; Playwright asserts both buttons are present and enabled on the login screen.
- [x] **4.3.6** Session bootstrap + auth context: read the existing Supabase session on load, expose `useAuth()` (user/session/loading), and gate authenticated routes (redirect unauthenticated users to `/login`).
      verify: Playwright visiting `/` while logged out redirects to `/login`; vitest asserts protected routes redirect when `session` is null.
- [x] **4.3.7** Central token refresh + 401-retry: a TanStack Query / fetch interceptor that, on a 401, refreshes via supabase-js once and retries the request; sign out + redirect if refresh fails.
      verify: vitest simulates a 401 → refresh → retry-success path and asserts the second call carries the new token; a forced refresh failure logs the user out and redirects to `/login`.
- [x] **4.3.8** Sign-out action (header/account menu) that clears the Supabase session and resets the Query cache.
      verify: Playwright clicks sign out and is redirected to `/login`; revisiting `/` redirects back to login (session cleared).

## 4.4 — Language management & CEFR level UI  ·  M

_Context: ports the Streamlit sidebar — pick the active language, add/remove languages, and the CEFR band with progress + manual override. Per-user, RLS-isolated via the API._

- [x] **4.4.1** Active-language picker in the app shell: list the user's languages from the API and persist the current selection (per user/session) so all screens scope to it.
      verify: Playwright selects a language and asserts Generate/Review reflect that language; vitest asserts switching selection refetches language-scoped queries.
- [x] **4.4.2** Add-language flow (name + CEFR starting level/direction) calling the API; new language appears in the picker.
      verify: Playwright adds a language and sees it in the picker; vitest asserts the create mutation invalidates the languages query and the empty-state disappears.
      _Reconciliation: `POST /languages` accepts name/code/vowelized ONLY (no CEFR/direction); a non-default starting band is applied with a follow-up `PUT /proficiency/{id}`, and text direction is DERIVED from the language code (group 4.9), so there is no manual "direction" field._
- [x] **4.4.3** Remove-language flow with a confirm dialog (cascade warning) calling the delete endpoint.
      verify: Playwright removes a throwaway language and confirms it leaves the picker; vitest asserts the confirm dialog gates the delete mutation.
- [x] **4.4.4** CEFR level panel in the sidebar: show the current band and progress-to-next-band for the active language (read from the `proficiency` endpoint), with red/orange/blue/green-neutral progress styling.
      verify: vitest renders the panel against a mocked proficiency payload and asserts the band label + progress percentage; Playwright asserts the band is visible for the demo account.
- [x] **4.4.5** Manual CEFR override control (set the band explicitly) that calls the API and updates generation level.
      verify: Playwright overrides the band and asserts the panel reflects the new band; vitest asserts the override mutation invalidates the proficiency query.

## 4.5 — Generate screen  ·  M

_Context: paste words → API generates natural sentences → review the list (sentence / translation / used words) → save selected as flashcards. Generation is slow and quota-bounded, so progress and the 429 path are first-class here._

- [ ] **4.5.1** Word-input form (textarea/chips) for the active language with client-side validation (non-empty, word count cap matching the server limit).
      verify: vitest asserts the form blocks an empty submit and warns past the per-request word cap; Playwright types words and the Generate button enables.
- [ ] **4.5.2** Call `POST /generate` via the typed client with an explicit in-progress/streamed state (spinner + "generating…" copy), and render the returned sentences as cards (sentence, translation, used words).
      verify: Playwright (LLM stubbed to deterministic output) generates and asserts the stubbed sentences render with their translations and used-word chips.
- [ ] **4.5.3** Select-and-save: per-sentence selection (default all) → save chosen sentences as flashcards via the API, with success toast and a saved/again-to-generate reset.
      verify: Playwright selects a subset, saves, and asserts a success toast + the saved cards become reviewable in Review; vitest asserts the save mutation sends only selected sentences.
- [ ] **4.5.4** First-class 429 daily-limit state on Generate: catch the friendly quota 429 and render a dedicated "daily limit reached, try again tomorrow" panel (not a generic error), keeping typed words intact.
      verify: Playwright with the API stubbed to return the quota 429 asserts the daily-limit panel renders and the entered words are preserved; vitest asserts a 429 maps to the quota state, not the generic error state.

## 4.6 — Review screen  ·  M

_Context: ports the core FSRS loop — due batch with new vs. due counts, reveal answer, rate Again/Hard/Good/Easy keeping the existing red/orange/blue/green colors, and tap-a-word explanations on production cards._

- [ ] **4.6.1** Load the due batch for the active language (new vs. due counts header) and render the first card front; clean empty state when nothing is due.
      verify: Playwright opens Review for the demo account and asserts the new/due counts header and first card render; vitest asserts the "all caught up" empty state when the batch is empty.
- [ ] **4.6.2** Reveal interaction: show answer (recognition + production variants) on reveal, then surface the four rating buttons.
      verify: vitest asserts the answer is hidden until reveal and the rating buttons appear only after reveal; Playwright reveals a card and sees all four buttons.
- [ ] **4.6.3** Rate Again/Hard/Good/Easy buttons in the locked **red / orange / blue / green** colors, posting the grade to the review endpoint and advancing to the next card.
      verify: vitest asserts each button's resolved color matches the spec (red/orange/blue/green) and submits the correct grade; Playwright grades a card and the next card (or empty state) appears.
- [ ] **4.6.4** Tap-a-word explanation popover on production cards: tapping/clicking a word fetches its explanation via the API and shows a popover; correct word boundaries on both touch and click.
      verify: Playwright clicks a word on a production card and asserts the explanation popover opens with stubbed explanation text; vitest asserts the explain query keys by word + language.
- [ ] **4.6.5** Keyboard shortcuts for review (space/enter to reveal, 1–4 to rate) for fast desktop review.
      verify: vitest fires keydown events and asserts reveal + each grade map to the right action; Playwright reveals and grades a card using only the keyboard.

## 4.7 — Discover screen  ·  S

_Context: ports Discover — optional topic + count → preview suggested new words → accept or reroll → generate sentences from accepted words. Shares the quota/429 path with Generate._

- [ ] **4.7.1** Discover form (optional topic + count, defaulting to the user's discover-count setting) and a fetch of suggested new words preview.
      verify: Playwright (LLM stubbed) runs Discover and asserts the suggested words preview renders; vitest asserts the default count comes from settings.
- [ ] **4.7.2** Accept / reroll controls: accept the suggested words (feed into the generate flow) or reroll for a fresh set.
      verify: Playwright rerolls and asserts a new stubbed set replaces the old; accepting routes the words into the Generate flow; vitest asserts reroll refetches and accept hands off the word list.
- [ ] **4.7.3** Reuse the shared 429 daily-limit + loading/error states on Discover (no generic error for quota).
      verify: Playwright with the API stubbed to a quota 429 asserts the daily-limit panel renders on Discover too.

## 4.8 — Settings & Account screens  ·  S

_Context: ports Settings (per-user daily new/total limits, discover count) and Account (profile, data export, delete account, sign out). Delete + export are store-compliance flows backed by the Phase 2 endpoints._

- [ ] **4.8.1** Settings screen: edit per-user daily new-card limit, daily total limit, and discover count; save via the settings endpoint with validation against server bounds.
      verify: Playwright changes the daily new-card limit, saves, reloads, and asserts the value persists; vitest asserts client validation rejects values outside server bounds.
- [ ] **4.8.2** Account screen — profile + data export: trigger the JSON export endpoint and download/display the file.
      verify: Playwright clicks export and asserts a JSON download is offered (or rendered); vitest asserts the export call hits the correct endpoint and handles the returned payload.
- [ ] **4.8.3** Account screen — delete account: a confirm-typed dialog calling the hard-delete endpoint, then sign out + redirect to login.
      verify: vitest asserts the delete button is disabled until the confirmation phrase is typed and that confirming calls the delete endpoint then signs out; Playwright walks the dialog up to (mocked) deletion and asserts redirect to `/login`.

## 4.9 — RTL, diacritics & complex scripts  ·  M

_Context: a key reason Capacitor was chosen — the web text engine shapes Arabic/Hebrew well. Per-language direction, correct diacritic-rendering fonts, a vowel-marks toggle, and RTL-aware tap-a-word must all work on web and survive into the mobile webview._

- [ ] **4.9.1** Per-language direction: set `dir="rtl"` for Arabic/Hebrew (and `ltr` otherwise) on the content region and mirror layout (paddings, icons, alignment) accordingly.
      verify: vitest renders an Arabic language and asserts the content container has `dir="rtl"`; an English language asserts `ltr`; Playwright snapshot shows mirrored layout for an RTL language.
- [ ] **4.9.2** Bundle/select fonts that correctly render harakat/nikkud and Arabic/Hebrew shaping; apply them to language text regions.
      verify: Playwright renders a vowel-marked Hebrew/Arabic sentence and a visual snapshot shows diacritics positioned on base letters (no tofu/boxes); the font is confirmed loaded via `document.fonts.check`.
- [ ] **4.9.3** Vowel-marks (harakat/nikkud) toggle that strips/restores diacritics in displayed text per the user's preference.
      verify: vitest asserts toggling off removes the diacritic marks from rendered text and back on restores them; Playwright toggles and the on/off rendering differs.
- [ ] **4.9.4** RTL-aware tap-a-word: word segmentation respects RTL boundaries so tapping selects the correct word in Arabic/Hebrew on both touch and click.
      verify: Playwright taps a word mid-RTL-sentence and asserts the correct word's explanation opens (touch emulation + click); vitest asserts the segmenter returns correct word spans for an RTL string.

## 4.10 — Cross-cutting UX states & consent  ·  S

_Context: loading/empty/error states everywhere, a first-class friendly 429 daily-limit experience tied to the LLM quota, and a first-run analytics-consent prompt (PostHog loads only after opt-in)._

- [ ] **4.10.1** Shared loading + empty + error state components (skeletons, empty illustrations, retryable error cards) wired into the Generate/Review/Discover queries.
      verify: vitest asserts each screen renders the skeleton during loading, the empty component when data is empty, and a retry-able error when the query fails.
- [ ] **4.10.2** A shared, reusable 429 "daily limit reached" state component used by Generate and Discover (and any future LLM-bound call), distinct from generic errors and tied to the quota response shape.
      verify: vitest asserts the component renders only for the quota-429 error shape; Grep/usage check confirms Generate and Discover both consume this shared component (no duplicated 429 UI).
- [ ] **4.10.3** First-run analytics-consent prompt: a consent banner/modal where PostHog (or any analytics) initializes **only after** explicit opt-in; the choice is persisted and re-prompts never fire once decided.
      verify: vitest asserts no analytics init call fires before consent and that opting in triggers exactly one init; Playwright asserts the banner shows on first load and does not reappear after a decision (persisted across reload).

## 4.11 — Legacy Streamlit retirement note  ·  S

_Context: keep the Streamlit app runnable until parity, then retire it once the React app covers the full loop._

- [ ] **4.11.1** Add a parity checklist doc mapping every legacy Streamlit page/feature to its React equivalent, and mark the Streamlit app deprecated in the README once all rows are checked (do not delete code yet).
      verify: the parity doc lists each Streamlit `pages/*` feature with a ✅ React counterpart and the README "Legacy Streamlit" section is updated to "deprecated — retained for reference"; CLAUDE.md README-currency rule satisfied (README diff present in the PR).

---

## Phase 4 exit gate

Phase 4 is DONE only when all of these hold:

- [ ] A signed-in browser user can run the full core loop end-to-end against the API — generate → save → review (reveal + grade) → discover — with no Streamlit involved. — verify: a Playwright E2E spec runs the complete loop on the ephemeral stack (LLM stubbed) and passes in CI.
- [ ] Auth is complete: sign up, verify, log in, password reset, Google + Apple buttons, with token refresh + 401-retry working. — verify: Playwright auth spec covers signup→verify-notice, login, and a forced-401→refresh→retry path; all green in CI.
- [ ] Every legacy Streamlit screen has a React equivalent (Generate, Review, Discover, Settings, Language management, Account, CEFR level + override). — verify: the 4.11.1 parity checklist is fully ✅ and a reviewer can reach each screen from the app shell on the demo account.
- [ ] RTL + diacritics render correctly and tap-a-word works on touch and click for an RTL language. — verify: Playwright RTL spec (Arabic/Hebrew) passes visual + interaction assertions including a mid-sentence RTL word tap.
- [ ] The 429 daily-limit and analytics-consent experiences are first-class. — verify: vitest + Playwright assert the dedicated quota-429 panel and the consent-gated analytics init (no analytics before opt-in).
- [ ] The typed API client is generated from `packages/api-types` and stays in sync. — verify: the CI drift check (`pnpm gen:api` produces no diff) passes on the merge commit.
- [ ] every task above merged via a green PR with the quality gate held (≥80% coverage, E2E).
