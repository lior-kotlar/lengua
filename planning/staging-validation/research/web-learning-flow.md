# Lengua web (apps/web) — complete user-facing learning flow

Research note for staging validation. Maps every screen in the React web app (`apps/web`) that a
Playwright/Selenium test would drive through the full learning loop, with the concrete component
file, route, and the visible labels / ARIA roles / placeholders / `data-testid`s a selector can
target. Derived from reading the source under `apps/web/src` plus the existing E2E specs in
`apps/web/e2e/*` (which already drive these exact selectors).

All file paths below are relative to `apps/web/`. The router lives in `src/App.tsx`; the app shell
in `src/components/app-layout.tsx`; the auth shell in `src/components/auth-layout.tsx`.

---

## 0. Routing & shells (the skeleton every screen hangs off)

`src/App.tsx` (react-router v6) defines three route groups:

| Group | Guard / layout | Routes |
| --- | --- | --- |
| Public auth | `RedirectIfAuthed` → `AuthLayout` | `/login`, `/signup`, `/forgot-password` |
| Transient auth | `AuthLayout` only (NOT redirect-guarded) | `/reset-password`, `/auth/callback` |
| Authenticated app | `RequireAuth` → `AppLayout` | `/` (Dashboard), `/generate`, `/review`, `/discover`, `/languages`, `/settings`, `/account` |
| Catch-all | — | `*` → `NotFound` (`src/pages/NotFound.tsx`) |

- `RequireAuth` (`src/components/route-guards.tsx`): while the session loads it renders a spinner
  `role="status"` `aria-label="Loading"`; when signed out it `<Navigate to="/login" replace>` and
  stashes the target in router state (`from`), so a deep link survives the login round-trip.
- `RedirectIfAuthed`: a signed-in user hitting `/login` etc. is bounced into the app. The login /
  signup forms **do not navigate themselves** — establishing the Supabase session flips the auth
  context and this guard does the redirect. So a test asserts success by waiting for the Dashboard
  heading, not a URL change triggered by the form.
- App shell (`AppLayout`) wraps the authenticated routes in `ActiveLanguageProvider` +
  `VowelMarksProvider`, and renders: a header (brand link "Lengua" → `/`, the `LanguagePicker`,
  the `ThemeToggle`, the `UserMenu`), a left sidebar `<nav aria-label="Primary">` of nav links plus
  the `CefrPanel`, and a `<main>` `<Outlet/>`. The sidebar is `hidden sm:flex` — **hidden on mobile
  widths**, but the header `LanguagePicker` and `UserMenu` remain reachable everywhere.
- App-global first-run **analytics-consent banner** (`src/components/analytics-consent-banner.tsx`),
  rendered in `src/main.tsx` OUTSIDE the route tree: `role="region"` `aria-label="Analytics consent"`
  `data-testid="analytics-consent"`, a `fixed inset-x-0 bottom-0` overlay with buttons **"Decline"**
  and **"Accept"**. It can intercept clicks on bottom-anchored controls, so every E2E fixture
  pre-seeds `localStorage['lengua.analytics-consent'] = 'denied'` before boot
  (`e2e/fixtures.ts`, `e2e-staging/fixtures.ts`). A driver should do the same or dismiss it first.

---

## Per-screen table

| # | Screen | Route | Component file | Key selectors / labels | Primary user actions |
| --- | --- | --- | --- | --- | --- |
| 1 | Login | `/login` | `src/pages/Login.tsx` | `getByLabel('Email')`, `getByLabel('Password', {exact:true})`, link "Forgot password?", button "Log in" (→ "Logging in…"), OAuth buttons `aria-label="Continue with Google"` / `"Continue with Apple"` (Apple disabled, "(soon)"), link "Sign up"; error `role="alert"` | Fill email+password, click "Log in"; wait for Dashboard heading |
| 2 | Sign up | `/signup` | `src/pages/Signup.tsx` | `getByLabel('Email')`, `getByLabel('Password', {exact:true})` (id `password`), `getByLabel('Confirm password')` (id `confirm-password`), button "Create account" (→ "Creating account…"); success heading **"Check your email"**; link "Log in" | Fill 3 fields, submit; verify-email notice |
| 3 | Forgot password | `/forgot-password` | `src/pages/ForgotPassword.tsx` | heading "Reset password", `getByLabel('Email')`, button "Send reset link" (→ "Sending…"); success heading "Check your email"; link "Back to log in" | Enter email, submit |
| 3b | Reset password (token landing) | `/reset-password` | `src/pages/ResetPassword.tsx` | heading "Set a new password", `getByLabel('New password')`, `getByLabel('Confirm new password')`, button "Update password"; done heading "Password updated" + link "Continue to Lengua" → `/`; expired heading "Link expired" + link "Request a new reset link" | Set new password |
| 3c | OAuth/verify callback | `/auth/callback` | `src/pages/AuthCallback.tsx` | (transient landing; not part of the manual loop) | — |
| 4 | Dashboard (landing after login) | `/` | `src/pages/Dashboard.tsx` | heading **"Dashboard"** (via `PlaceholderScreen`), copy "Your languages and review progress will appear here."; flag-gated `WordOfTheDay` renders nothing by default | Lands here post-login; navigate via sidebar |
| 5 | Languages management | `/languages` | `src/pages/Languages.tsx` | heading "Languages"; card "Your languages" (list rows: name button + uppercase code chip + "active" tag; per-row `RemoveLanguageDialog`); card "Add a language" → `AddLanguageForm` | Switch active by clicking a row name; add/remove |
| 5a | Add-language form | `/languages` | `src/components/add-language-form.tsx` | `getByLabel('Name')` (id `language-name`, ph "Spanish"), `getByLabel('Code (optional)')`/`'Code'` (id `language-code`, ph "es", REQUIRED when vowelized), `getByLabel('Starting level')` (select id `language-band`, options A1–C2), checkbox "Include vowel marks (harakat / nikkud)", button "Add language" (→ "Adding…") | Type name/code, pick starting CEFR, optional vowel marks, submit |
| 5b | Remove-language dialog | `/languages` | `src/components/remove-language-dialog.tsx` | trigger button `aria-label="Remove <name>"` (text "Remove"); `role="dialog"` title "Remove <name>?"; buttons "Cancel" and "Remove" (→ "Removing…") | Open dialog, confirm "Remove" |
| 6 | Language picker (header, all authed screens) | n/a (in shell) | `src/components/language-picker.tsx` | `getByLabel('Active language')` native `<select>`, `<option>` per `language.name`; empty → link "Add a language" → `/languages` | `selectOption({label})` to switch active language |
| 7 | CEFR level panel (sidebar, all authed screens) | n/a (in shell) | `src/components/cefr-panel.tsx` | `getByRole('region', {name:'Proficiency level'})`; band `getByTestId('cefr-band')` (text A1…C2); progress bar `role="progressbar"` `aria-label="Progress to <next>"`/"Top level reached"; override `getByLabel('Override level')` (select id `cefr-override`, options A1–C2) | Read current band; override via select |
| 8 | Generate | `/generate` | `src/pages/Generate.tsx` | section `data-testid="generate-content"` (`dir` from code); heading "Generate"; `VowelMarksToggle`; textarea `getByLabel('Words', {exact:true})` (id `generate-words`, ph `casa\nperro\nbuenos días`); counter "N / 30 words"; `ul aria-label="Parsed entries"`; button "Generate" (→ "Generating…") | Paste words, click Generate |
| 8a | Generate — review & save | `/generate` | `src/pages/Generate.tsx` (`ResultsPanel`) | heading "Review & save"; checkbox "Select all" (`aria-label="Select all sentences"`); per-sentence checkbox `aria-label="Save this card — <translation>"`; button "Save N sentence(s)" (→ "Saving…"); button "Start over"; toast "Cards saved" | Toggle selection, "Save N sentences" |
| 8b | Generate — saved confirmation | `/generate` | `src/pages/Generate.tsx` (`SavedConfirmation`) | heading "Saved N card(s)"; button "Generate more"; link "Review now" → `/review` | Continue to review or generate more |
| 9 | Review (study session) | `/review` | `src/pages/Review.tsx` | section `data-testid="review-content"` (`dir` from code); heading "Review"; counts `getByTestId('review-counts')` ("N new · N due", "Card X of Y"); `role="progressbar" aria-label="Review progress"` | Walk cards: reveal → rate |
| 9a | Review card — front/reveal | `/review` | `src/pages/Review.tsx` (`ReviewCard`) | prompt label "Read and understand" (recognition) / "Build the sentence in <Lang>" (production); reveal button "Show translation" (recognition) / "Show answer" (production); hint "or press space" | Click reveal OR press Space/Enter |
| 9b | Review card — answer + rating | `/review` | `src/pages/Review.tsx` (`RatingButtons`) | `getByTestId('card-answer')`; `role="group" aria-label="Rate this card"`; 4 buttons **Again/Hard/Good/Easy** (`data-rating="1..4"`, locked red/orange/blue/green); production answer is tap-a-word | Click a rating OR press 1–4 → advances to next card |
| 9c | Review — tap-a-word popover (production) | `/review` | `src/components/tappable-sentence.tsx` | word buttons `button[aria-haspopup="dialog"]` (`aria-expanded`); popover `getByTestId('word-popover')` (`role="dialog"` `aria-label="Explanation of <word>"`); close button `aria-label="Close explanation"` | Tap/click a word → explanation popover |
| 9d | Review — all caught up | `/review` | `src/pages/Review.tsx` (`AllCaughtUp`) | `data-testid="empty-state"`, heading "You're all caught up"; button/link "Generate sentences" → `/generate` | Nav to generate |
| 9e | Review — session complete | `/review` | `src/pages/Review.tsx` (`SessionComplete`) | heading "Done for today"; button "Check for more" (refetch); link "Generate more" → `/generate` | Re-check or generate |
| 10 | Discover | `/discover` | `src/pages/Discover.tsx` | section `data-testid="discover-content"`; heading "Discover"; `getByLabel('How many words')` (id `discover-count`, number); `getByLabel('Topic (optional)')` (id `discover-topic`, ph "e.g. food, travel, work"); button "Discover" (→ "Finding words…") | Set count/topic, click Discover |
| 10a | Discover — suggestions | `/discover` | `src/pages/Discover.tsx` (`SuggestionsPanel`) | heading "Suggested words"; `ul getByTestId('discover-suggestions')` (`aria-label="Suggested words"`); button "Use these words" → navigates `/generate`; button "Try different words" (reroll); button "Start over" | Accept → hands words to Generate; or reroll |
| 11 | Settings | `/settings` | `src/pages/Settings.tsx` | heading "Settings"; `getByLabel('Daily new cards')` (id `daily_new_limit`, 1–100), `getByLabel('Daily total cards')` (id `daily_total_limit`, 1–500), `getByLabel('Discover word count')` (id `discover_count`); button "Save settings" (→ "Saving…"); `AnalyticsConsentToggle` below | Edit limits, "Save settings" |
| 12 | Account | `/account` | `src/pages/Account.tsx` | heading "Account"; email `getByTestId('account-email')`; button "Sign out" (→ "Signing out…"); button "Export my data" (→ "Preparing…"); `DeleteAccountDialog` | Sign out, export JSON, delete account |
| 12a | Delete-account dialog | `/account` | `src/components/delete-account-dialog.tsx` | trigger button "Delete account"; `role="dialog"` title "Delete your account?"; `getByLabel(/Type .* to confirm/)` (id `delete-confirm`); confirm button "Delete account" disabled until typed phrase **`delete my account`**; "Cancel" | Type phrase, confirm |
| 13 | User menu / sign out (header) | n/a (in shell) | `src/components/user-menu.tsx` | email span (`title=<email>`, `sm:inline`); button "Sign out" | Sign out from anywhere |

---

## The complete numbered learning flow (an automated browser test could drive this verbatim)

This is the end-to-end happy path. Step labels/selectors are exactly what the existing
`e2e/full-loop.spec.ts`, `e2e/languages.spec.ts`, and `e2e/rtl.spec.ts` use. Pre-seed the consent
banner to "denied" before navigation (see §0).

1. **Landing / auth.** Navigate to `/` while signed out → `RequireAuth` redirects to `/login`
   (`AuthLayout` shell, brand "Lengua" + `ThemeToggle`).
2. **Log in.** On `/login`: `getByLabel('Email').fill(email)`,
   `getByLabel('Password', {exact:true}).fill(pw)`, `getByRole('button', {name:'Log in'}).click()`.
   Assert success by waiting for `getByRole('heading', {name:'Dashboard'})` (the form does not
   navigate; the session flip + `RedirectIfAuthed` does). New users instead go via `/signup`
   ("Create account" → "Check your email" verify state) then log in.
3. **Open Languages.** Click sidebar `getByRole('navigation', {name:'Primary'}).getByRole('link',
   {name:'Languages'})`; wait for heading "Languages".
4. **Add a NEW language + choose its CEFR starting level.** In the "Add a language" card:
   `getByLabel('Name').fill('Spanish')`; optionally `getByLabel('Code (optional)').fill('es')`
   (the code drives RTL direction + script font, and is REQUIRED once "Include vowel marks" is
   checked); `getByLabel('Starting level').selectOption('B1')`; `getByRole('button',
   {name:'Add language'}).click()`. On success it toasts "Language added", the row appears with a
   `aria-label="Remove <name>"` control, AND the new language is **auto-selected as active** (it
   shows up in the header picker). A non-default starting band issues a follow-up
   `PUT /proficiency/{id}` (see `useAddLanguage`).
5. **See / confirm the CEFR level.** The sidebar `getByRole('region', {name:'Proficiency level'})`
   now shows `getByTestId('cefr-band')` = the chosen band (e.g. "B1") with a colored progress bar.
6. **Switch BETWEEN 2+ languages (the multi-language pivot).** The header
   `getByLabel('Active language')` `<select>` lists every language by name.
   `picker.selectOption({label:'Spanish'})` re-scopes EVERY language-scoped screen (Generate /
   Review / Discover / CEFR panel) by changing the active id, which re-keys the TanStack queries.
   The CEFR band updates to that language's own band (e.g. Spanish A1 vs. the new language's B1).
   Selection is persisted per-user in `localStorage` (key `activeLanguageStorageKey(userId)`).
7. **Change the CEFR level manually (optional).** `getByLabel('Override level').selectOption('C1')`
   in the sidebar panel → `getByTestId('cefr-band')` becomes "C1" (PUTs the new band, re-levels
   future generation).
8. **Enter vocabulary words.** Sidebar → "Generate" (heading "Generate", section
   `data-testid="generate-content"`). Fill `getByLabel('Words', {exact:true})` with one
   word/phrase per line or comma-separated (placeholder shows `casa / perro / buenos días`). The
   counter reads "N / 30 words" (`WORDS_PER_REQUEST_CAP`, from the OpenAPI schema); over-cap blocks
   with a `role="alert"`. The "Generate" button is disabled until ≥1 word and not over cap.
9. **Generate example sentences.** Click `getByRole('button', {name:'Generate'})` → "Generating…".
   `POST /generate` returns a recognition+production card pair per sentence.
10. **Review & save (creates the flashcards).** The `ResultsPanel` (heading "Review & save",
    subtitle "Each becomes two flashcards (reading + writing)") lists each sentence + its English
    translation + used-word chips, all selected by default. Toggle via "Select all"
    (`aria-label="Select all sentences"`) or per-sentence `aria-label="Save this card — <translation>"`.
    Click "Save N sentence(s)" → `POST /cards/save` persists BOTH directions (recognition +
    production) per sentence. Toast "Cards saved"; the panel becomes "Saved N cards" with
    "Generate more" + link "Review now".
11. **Study / review the cards.** Sidebar → "Review" (section `data-testid="review-content"`).
    `getByTestId('review-counts')` shows "N new · N due" and "Card X of Y"; a
    `role="progressbar" aria-label="Review progress"` tracks position. The due batch is **due-first,
    then new** — a client-side snapshot the session walks (grading does NOT refetch mid-session).
    Saved cards are immediately due (the save invalidates the `['review']` cache).
12. **"Continue"/reveal during the session.** Each card shows its prompt (front). The reveal button
    is "Show translation" (recognition) or "Show answer" (production) — or press **Space/Enter**.
    Revealing shows `getByTestId('card-answer')` (production answers are tap-a-word; recognition
    answers are plain English).
13. **Rate → advance to the NEXT card.** After reveal, the `role="group" aria-label="Rate this card"`
    exposes four buttons **Again / Hard / Good / Easy** (`data-rating="1".."4"`, locked
    red/orange/blue/green) — or press **1–4**. Clicking/keying one POSTs the FSRS grade and
    **advances to the next card** (the "continue/next" action). There is no explicit per-card "Back"
    button; the session is a forward walk (Space=reveal, 1–4=grade-and-advance). "Back" navigation
    in practice = the browser/back-button or re-selecting a sidebar item; at session end
    `SessionComplete` offers "Check for more" (refetch the batch) and "Generate more".
14. **Tap-a-word (production cards).** In a revealed production answer, each word is a
    `button[aria-haspopup="dialog"]`; tap/click opens `getByTestId('word-popover')`
    (`role="dialog" aria-label="Explanation of <word>"`) via `POST /explain` (cached per word).
    Tapping another word switches; the close button is `aria-label="Close explanation"`; Escape or
    an outside click dismisses.
15. **End of batch.** When the snapshot is exhausted → "Done for today" (`SessionComplete`); an
    empty batch → "You're all caught up" (`AllCaughtUp`, `data-testid="empty-state"`, link
    "Generate sentences").
16. **Discover new vocabulary.** Sidebar → "Discover" (section `data-testid="discover-content"`).
    `getByLabel('How many words')` (defaults to the user's `discover_count` setting),
    `getByLabel('Topic (optional)')`. Click "Discover" → "Finding words…" → `POST /discover` returns
    words the learner doesn't know yet, listed in `ul getByTestId('discover-suggestions')`. "Use
    these words" hands them off to Generate (`navigate('/generate')`, the word form is pre-filled —
    the Generate UI is NOT duplicated here); "Try different words" rerolls (cache-bypassed);
    "Start over" returns to the form.
17. **Settings.** Sidebar → "Settings": edit "Daily new cards" (1–100), "Daily total cards"
    (1–500, must be ≥ daily new), "Discover word count" (schema bounds); "Save settings" →
    `PUT /settings`, toast "Settings saved". Plus the analytics-consent toggle.
18. **Account.** Sidebar → "Account": email shown in `getByTestId('account-email')`; "Export my
    data" downloads `lengua-export.json` (`GET /account/export`); "Sign out"; and the guarded
    `DeleteAccountDialog` (type **`delete my account`** to enable the irreversible "Delete account",
    `DELETE /account`).

---

## Switching between 2+ languages — detail (the requested focus)

- **Where:** the single source of truth is the header `LanguagePicker`
  (`getByLabel('Active language')`, a native `<select>` — chosen over a Radix combobox precisely
  because it's trivial to drive in tests and accessible). Available on every authed screen (incl.
  mobile, where the sidebar is hidden). The Languages page list rows are a SECOND way to switch:
  each row name is a `<button>` that calls `setActiveLanguageId`.
- **State:** `ActiveLanguageProvider` (`src/components/active-language-provider.tsx`) owns the
  active id, persists it per-user in `localStorage` (`activeLanguageStorageKey(userId)`), and
  reconciles it against `GET /languages` (an invalid/removed selection falls back to the first
  language; empty account → `null`).
- **Effect of a switch:** language-scoped queries (`useDueQuery`, proficiency, generate/discover
  drafts) are keyed by the active id, so switching changes the keys and TanStack Query refetches.
  The Generate/Review/Discover workspaces are **re-mounted per language** (`key={activeLanguageId}`)
  so drafts and walk-position never leak across a switch.
- **No language yet:** the picker degrades to a link "Add a language" → `/languages`; Generate/
  Review/Discover render an `EmptyState` "Add a language first" with a button to `/languages`; the
  CEFR panel shows "Add a language to track your level."
- **Proven by `e2e/languages.spec.ts`:** it adds a throwaway language at band B1, asserts it appears
  in both the management list and the picker and is auto-active at B1, switches the picker
  Spanish↔throwaway and asserts `cefr-band` flips A1↔B1, overrides to C1, then removes it.

## CEFR level — display & change

- **Display:** `CefrPanel` → `cefr-band` testid (A1…C2) + a tier-colored progress bar
  (`cefr.ts`: A1 red, A2 orange, B1/B2 blue, C1/C2 green) toward the next band, read from
  `GET /proficiency/{language_id}`. Bands: `['A1','A2','B1','B2','C1','C2']` (`src/lib/cefr.ts`,
  mirrors backend `config.CEFR_BANDS`).
- **Set at creation:** "Starting level" select in `AddLanguageForm` (defaults A1; a non-default band
  triggers `PUT /proficiency/{id}` after create; A1 is skipped since it maps to the zero score).
- **Change later:** "Override level" select in the sidebar panel (`PUT`s the band, invalidates the
  proficiency query). It also adapts automatically from review answers ("Auto-adjusts as you
  review; override it if it's off.").

## RTL + diacritics handling

- **Direction is DERIVED from the language `code`** (no manual direction field) —
  `src/lib/language-text.ts` `directionForCode()` (RTL for `ar`/`he`/`fa`/`ur`/… subtags). The
  Generate / Review / Discover `<section>`s set `dir={directionForCode(code)}`, so the whole content
  region mirrors RTL. E2E asserts `getByTestId('review-content')` has `dir="rtl"` for Hebrew.
- **Script fonts:** `scriptFontClass()` → `font-arabic` (Noto Naskh Arabic) / `font-hebrew`
  (Noto Sans Hebrew), self-hosted/bundled in `src/main.tsx` (mobile-webview-safe, no CDN), mapped in
  `tailwind.config.ts`. E2E checks `document.fonts.check('16px "Noto Sans Hebrew"')` and that
  rendered text carries nikkud and a `.font-hebrew` class.
- **Vowel marks (harakat / nikkud) toggle:** `src/components/vowel-marks-toggle.tsx` —
  `getByRole('switch', {name:'Show vowel marks'})`, label "Vowel marks". **Self-gating:** renders
  ONLY when the active language is `vowelized` (so it never appears on Latin screens). Preference
  persisted device-wide via `VowelMarksProvider`. Off → `stripDiacritics()` removes the marks from
  displayed glyphs (the looked-up word for tap-a-word stays the canonical WITH-marks form so the
  explanation cache still hits). To enable: add a language with code `he`/`ar`/`fa` AND check
  "Include vowel marks" (the form REQUIRES a code when vowel marks are on — finding S14).
- **`LanguageText`** (`src/components/language-text.tsx`) applies dir + font + strip for
  non-interactive target text (generated sentences, used-word chips, discover suggestions,
  recognition prompts). `TappableSentence` does the same per word for interactive production answers.
- **Recognition card subtlety:** a recognition card's revealed ANSWER is English, rendered as plain
  text (NOT through `LanguageText`) so an RTL deck doesn't force the English answer into the script
  font / `dir=rtl` (which had hidden it). The recognition PROMPT (target text) keeps `LanguageText`.

---

## Concrete selectors / endpoints a test can target (quick reference)

- **Nav:** `getByRole('navigation', {name:'Primary'}).getByRole('link', {name:<Screen>})` where
  `<Screen>` ∈ Dashboard, Generate, Review, Discover, Languages, Settings, Account; then
  `getByRole('heading', {name:<Screen>})`.
- **Auth:** `getByLabel('Email')`, `getByLabel('Password', {exact:true})`,
  buttons "Log in" / "Create account" / "Send reset link" / "Update password".
- **Language switch:** `getByLabel('Active language').selectOption({label})`.
- **CEFR:** `getByRole('region', {name:'Proficiency level'})`, `getByTestId('cefr-band')`,
  `getByLabel('Override level')`, `getByLabel('Starting level')`.
- **Generate:** `getByTestId('generate-content')`, `getByLabel('Words', {exact:true})`,
  button "Generate", checkbox "Select all sentences", button `/save \d+ sentences?/i`,
  toast text "Cards saved" / "Saved N cards".
- **Review:** `getByTestId('review-content')`, `getByTestId('review-counts')`,
  reveal `/^Show (answer|translation)$/`, ratings `/^Again|Hard|Good|Easy/` (`data-rating`),
  `getByTestId('card-answer')`, `button[aria-haspopup="dialog"]`, `getByTestId('word-popover')`.
- **Discover:** `getByTestId('discover-content')`, `getByLabel('How many words')`,
  `getByLabel('Topic (optional)')`, button "Discover", `getByTestId('discover-suggestions')`,
  button "Use these words".
- **Settings:** `getByLabel('Daily new cards')`, `getByLabel('Daily total cards')`,
  `getByLabel('Discover word count')`, button "Save settings".
- **Account:** `getByTestId('account-email')`, button "Export my data", button "Sign out",
  button "Delete account", `getByLabel(/Type .* to confirm/)`, phrase `delete my account`.
- **Empty/RTL:** `getByTestId('empty-state')`, `getByRole('switch', {name:'Show vowel marks'})`,
  `.font-hebrew` / `.font-arabic`.
- **REST endpoints behind the flow:** `GET/POST/DELETE /languages`, `PUT /proficiency/{id}`,
  `GET /proficiency/{id}`, `POST /generate`, `POST /cards/save`, `GET /review/due`,
  `POST /review/{card_id}/grade`, `POST /explain`, `POST /discover`, `GET/PUT /settings`,
  `GET /account/export`, `DELETE /account`.
