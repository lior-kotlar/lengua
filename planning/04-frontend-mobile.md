# 04 — Frontend (React) & Mobile (Capacitor)

One React + TypeScript codebase serves the website and, wrapped by **Capacitor**, the iOS and
Android apps. No separate mobile codebase.

## Web stack

| Concern | Choice | Why |
| --- | --- | --- |
| Build/dev | **Vite + React + TypeScript** | Fast, standard, Capacitor-friendly static output. |
| Routing | **react-router** | Standard SPA routing. |
| Server state | **TanStack Query** | Caching, retries, and the seam for offline later. |
| Auth client | **supabase-js** | Login/signup/OAuth + token refresh on-device. |
| API client | **OpenAPI-generated** from `packages/api-types` | Types stay in sync with FastAPI. |
| UI | **Tailwind CSS + shadcn/ui** + theming | Customizable, copy-in components, strong RTL support. |
| Testing | Vitest (unit) + **Playwright** (E2E) | Cover the core loop. |

## Screens (port from Streamlit `pages/`)

- **Auth**: sign up, log in, email verification notice, password reset, Google + Apple buttons.
- **Home / language picker**: choose active language; add/remove languages; vowel-marks toggle.
- **Generate**: paste words → list of generated sentences (sentence / translation / used
  words) → save selected as flashcards.
- **Review**: due batch (new vs due counts), reveal answer, rate **Again / Hard / Good / Easy**
  (keep the red/orange/blue/green colors), **tap-a-word** explanation popover on production cards.
- **Discover**: optional topic + count → preview suggested new words → accept or reroll → sentences.
- **Level**: CEFR band + progress to next band + manual override (the old sidebar).
- **Settings**: per-user daily new/total limits, discover count.
- **Account**: profile, data export, **delete account**, sign out.
- Cross-cutting: loading/empty/error states; a clear, friendly **429 "daily limit reached"**
  state tied to the Gemini quota; a first-run **analytics consent** prompt (PostHog loads only
  after opt-in).

## RTL & complex scripts (don't lose this)

- Per-language direction: set `dir="rtl"` for Arabic/Hebrew, `ltr` otherwise; mirror layout.
- Choose fonts that render **diacritics/harakat/nikkud** correctly; verify the vowel-marks
  toggle output renders cleanly on web *and* in the mobile webview.
- Tap-a-word must work with touch (mobile) and click (web) and respect RTL word boundaries.
- This is a key reason Capacitor was chosen — the web text engine handles shaping well.

## Capacitor packaging

- Add `@capacitor/core` + CLI; `npx cap add ios` / `android` to generate native projects in
  `apps/web/ios` and `apps/web/android`.
- `capacitor.config.ts`: app id (e.g. `com.lengua.app`), name, the prod API base URL, splash
  + status bar config, deep-link scheme.
- Build flow: `vite build` → `npx cap sync` → open in Xcode / Android Studio (or Fastlane) to
  archive, sign, and upload.
- **Native plugins for v1:**
  - **Local Notifications** — a **daily review reminder** scheduled on-device when cards are due
    (ask permission once; works offline, no server/FCM/APNs). Reminders are a v1 feature.
  - **Preferences / secure storage** — persist Supabase tokens safely on device.
  - **Network** — detect offline to show appropriate UI / disable generation.
  - **App** — deep links + OAuth redirect handling.
- **OAuth in the webview**: configure Supabase redirect URLs for the app scheme; handle the
  Google/Apple round-trip inside Capacitor. Apple sign-in is mandatory on iOS if Google is
  offered (see [07-security-compliance.md](07-security-compliance.md)).
- **OTA updates**: integrate a web-bundle live-update service (e.g. **Capgo**, OSS/free) so
  JS/UI/CSS fixes reach users without a store review cycle; native/plugin changes still ship
  through the stores. Use separate channels per environment. (Store-policy notes in
  [07-security-compliance.md](07-security-compliance.md).)
- **Onboarding**: **signup is required** (no guest mode); ship a seeded **demo account** so
  store reviewers can exercise the full loop.

## Offline strategy

- **v1: online-first.** Review and generation require connectivity; show a clean offline state.
- **Fast-follow (post-launch):** cache the due batch and **queue review grades** offline
  (TanStack Query persistence + background flush), so review works on the subway. Generation
  stays online (needs the server + Gemini). Flagged as backlog, not a launch blocker.

## Store assets (needed for Phase 8)

- App icon (all required sizes) + adaptive icon (Android) + splash screens.
- Screenshots per required device size (iPhone, iPad if supported, Android phone/tablet) +
  web preview images.
- Listing copy: title, subtitle, description, keywords, category, support URL, privacy URL.
- Demo account credentials for reviewers (a seeded account that shows the full loop).

## Notes

- Keep the **legacy Streamlit app** runnable until the React app reaches parity, so you can
  dogfood without regressions, then retire it.
- Generation can be slow (Gemini latency) — design optimistic/streamed UI and clear progress,
  and make the 429/quota and timeout paths first-class, not afterthoughts.
