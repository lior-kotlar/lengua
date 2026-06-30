# Auth flow — register / login / logout, Supabase wiring, and staging test-user provisioning

Research note for staging-validation. Sources (all repo-relative):
`apps/web/src/lib/auth.ts`, `apps/web/src/lib/supabase.ts`, `apps/web/src/lib/api-client.ts`,
`apps/web/src/pages/Login.tsx`, `apps/web/src/pages/Signup.tsx`, `apps/web/src/components/user-menu.tsx`,
`apps/web/src/components/form-field.tsx`, `apps/web/src/App.tsx`,
`apps/web/e2e/auth.spec.ts`, `apps/web/e2e-staging/{auth.spec.ts,fixtures.ts}`,
`apps/web/playwright.staging.config.ts`,
`apps/api/app/auth.py`, `apps/api/app/quota.py`, `apps/api/tests/{auth_helpers.py,supabase_auth.py}`,
`apps/api/scripts/{seed_e2e.py,seed_dev_user.py}`,
`.github/workflows/{seed-staging.yml,deploy-staging.yml}`, `supabase/config.toml`.

---

## ★ CRITICAL VERDICT — does a brand-new staging user need email confirmation before login?

**YES — a brand-new sign-up through the normal web flow REQUIRES email confirmation before login
works.** `supabase/config.toml` sets `[auth.email] enable_confirmations = true` (lines ~251–254,
explicitly "Lengua requires email confirmation (task 2.1.1)"). Consequences:

- `signUpWithEmail()` (`apps/web/src/lib/auth.ts`) returns **no session** for a fresh sign-up; the
  Signup page then renders a **"Check your email"** notice screen (`Signup.tsx` lines 54–77) and the
  user stays unauthenticated.
- A subsequent login attempt before clicking the email link fails with GoTrue code
  **`email_not_confirmed`**; `Login.tsx` surfaces "Please verify your email address before signing in."
  plus a **"Resend verification email"** button (`resendVerificationEmail`, type `signup`).
- Even if a token were somehow obtained, the backend cost guard blocks LLM actions for an unverified
  user: `app/quota.py` raises **403 `{"code":"email_unverified"}`** (the first gate in the chain) when
  the verified JWT's `email_verified` is false. So `email_verified` matters end-to-end, not just at login.

**Therefore an automated test CANNOT self-register a usable user via the public sign-up form on
staging** — there is no inbox to click, and `enable_confirmations` is on. It must get a
**pre-confirmed** user instead (options below).

### ✅ The good news: a pre-confirmed test user ALREADY EXISTS on staging

The demo/reviewer account **`demo@lengua.test` / `demo-password-123`** is already provisioned on the
staging Supabase project (`rydclyotzdwcbbeyitcx`), created **pre-confirmed** (`email_confirm=true`)
via the Auth Admin API, with seeded data (≈12 Spanish + 6 Hebrew/RTL due cards). It is what every
staging suite logs in as. So in most cases an automated test does **not** need to create a user at
all — just log in with these credentials. Confirmed seeded per
`planning/go-live-activation.md` (§A3), `planning/outstanding-work.md` (§A3),
`planning/staging-fix-handoff.md` (S4), and `docs/streamlit-parity.md`.

---

## Every viable way an automated test can obtain a usable logged-in test user on staging

Ranked best→fallback. All "create" paths use the **Supabase Auth Admin API**, which bypasses email
confirmation by passing `email_confirm: true` — this is the supported mechanism, no config change needed.

1. **Use the existing pre-confirmed demo account (default, zero setup).**
   Log in with `demo@lengua.test` / `demo-password-123`. This is what `e2e-staging/fixtures.ts`,
   `apps/api/scripts/staging_smoke.py`, and the verification runs already do. Credentials are
   env-overridable (`DEMO_EMAIL` / `DEMO_PASSWORD`). No service-role key required for the login itself
   (login uses the anon key). **Recommended for almost all tests.**

2. **Admin-create a fresh pre-confirmed user via the Auth Admin API** (needs the staging
   **service-role** key). `POST {SUPABASE_URL}/auth/v1/admin/users` with headers
   `apikey` + `Authorization: Bearer <service_role_key>` and body
   `{"email": ..., "password": ..., "email_confirm": true}` → the user can log in immediately, and the
   `handle_new_user`/`on_auth_user_created` trigger inserts the matching `profiles` row. Reusable repo
   helper: `apps/api/tests/supabase_auth.py::create_confirmed_user()` (and `seed_e2e.py::ensure_demo_user`,
   `seed_dev_user.py::ensure_dev_auth_user` which can also pin a fixed UUID via an explicit `id`).
   Cleanup with `delete_user()` (`DELETE /auth/v1/admin/users/{id}`) so test users don't leak into
   `auth.users` (the conftest never truncates that table). **Service-role key is a SECRET** —
   `SUPABASE_STAGING_SERVICE_ROLE_KEY` in GitHub Actions secrets (not committed). Needed only if a test
   requires an *isolated*/fresh user rather than the shared demo account.

3. **Re-run the existing staging seed workflow** to (idempotently) re-provision the demo account +
   decks: `.github/workflows/seed-staging.yml` (`name: seed-staging`, manual `workflow_dispatch` only,
   independent of `DEPLOY_ENABLED`). It maps `SUPABASE_STAGING_*` secrets → the env `seed_e2e.py` reads
   and runs `uv run python scripts/seed_e2e.py`. Idempotent: finds the existing demo user by email,
   `ON CONFLICT`/existence checks for language+cards. Use if the demo deck got wiped.

4. **Mint a real Supabase JWT directly (skip the UI), then drive the API.**
   Password-grant against GoTrue: `POST {SUPABASE_URL}/auth/v1/token?grant_type=password` with
   `apikey: <anon_key>` + JSON `{email, password}` → returns `access_token` (a real ES256 JWT the
   staging API verifies via JWKS). Helper: `tests/supabase_auth.py::login()`. The web `e2e-staging`
   suite supports a pre-minted `STAGING_BEARER_TOKEN` to skip the GoTrue login round-trip. Good for
   pure API tests; does **not** give a browser session by itself (would need to inject the session into
   `localStorage` — see session handling below).

5. **(Not available / not recommended) Disable confirmation on staging.** There is **no** existing
   toggle/env for this; it would require editing `supabase/config.toml` (`enable_confirmations = false`)
   and applying it to the hosted project — a config change with security implications, and unnecessary
   because the Admin-API `email_confirm:true` path already gives confirmed users. **Magic-link / email
   OTP is also a dead end for automation** (still needs inbox access; no programmatic capture in repo).

**Bottom line for the validation workflow:** prefer option 1 (demo account, no secret). If you need an
isolated user, use option 2 with `SUPABASE_STAGING_SERVICE_ROLE_KEY`. Never attempt public sign-up +
login on staging — it will dead-end on the unconfirmed-email gate.

---

## Auth routes (React Router, `apps/web/src/App.tsx`)

Public routes are wrapped in `<RedirectIfAuthed>` (already-signed-in visitors get bounced into the app);
app routes are wrapped in `<RequireAuth>` (unauthenticated visitors → `/login`).

| Path | Screen | Guard |
|---|---|---|
| `/login` | `Login` | RedirectIfAuthed |
| `/signup` | `Signup` | RedirectIfAuthed |
| `/forgot-password` | `ForgotPassword` (`requestPasswordReset`) | RedirectIfAuthed |
| `/reset-password` | `ResetPassword` (`updatePassword`; consumes recovery redirect) | public |
| `/auth/callback` | `AuthCallback` (consumes email-verification + OAuth redirect) | public |
| `/` | `Dashboard` (heading "Dashboard") | RequireAuth |
| `/generate` `/review` `/discover` `/languages` `/settings` `/account` | app screens | RequireAuth |

- Constants: `AUTH_CALLBACK_PATH = '/auth/callback'`, `RESET_PASSWORD_PATH = '/reset-password'`
  (`lib/auth.ts`). Redirect URLs are built from `window.location.origin` so they work on
  dev :5173 / preview :4173 / staging / prod. Allowed redirect origins are whitelisted in
  `supabase/config.toml` `additional_redirect_urls` (includes `https://lengua-staging.vercel.app/**`
  and `https://lengua-*.vercel.app/**` previews).
- **Logged-out visit to `/` → 302/redirect to `/login`** (RequireAuth). The env-less build still
  renders this redirect (AuthProvider degrades to signed-out when Supabase env is absent).

## Form field selectors & submit controls (exact, used by the Playwright suites)

Labels are bound via `htmlFor`/`id` (`components/form-field.tsx`), so `getByLabel` works.

**Login (`/login`):**
- Email: `getByLabel('Email')` — input `id="email"`, `type="email"`, `autoComplete="email"`.
- Password: `getByLabel('Password', { exact: true })` — input `id="password"`, `type="password"`,
  `autoComplete="current-password"` (raw `<Input>` + sibling `<label htmlFor="password">`, not FormField,
  because the row also carries the "Forgot password?" link → use `exact: true`).
- Submit: `getByRole('button', { name: 'Log in' })` (label flips to "Logging in…" while submitting).
- Error region: `role="alert"`; unverified path adds a `button` "Resend verification email".
- "Forgot password?" → `/forgot-password`; "Sign up" → `/signup`.

**Signup (`/signup`):**
- Email: `getByLabel('Email')` (`id="email"`).
- Password: `getByLabel('Password', { exact: true })` (`id="password"`, `autoComplete="new-password"`).
- Confirm: `getByLabel('Confirm password')` (`id="confirm-password"`).
- Submit: `getByRole('button', { name: /create account/i })` ("Creating account…" while busy).
- Success (confirmation required): heading **"Check your email"** + the submitted email echoed.
- Client-side validation mirrors the server policy (≥8 chars, mixed case + digit) before the call.

**Logout control (`components/user-menu.tsx`, in the app shell header):**
- `getByRole('button', { name: /sign out/i })` — a ghost button with a `LogOut` icon + text "Sign out".
- Calls `signOut()` (network/global GoTrue logout). No manual navigation: the resulting `SIGNED_OUT`
  auth event makes `AuthProvider` reset the TanStack Query cache and flips the context to signed-out,
  so `RequireAuth` redirects to `/login`. (`signOutLocal()` — `scope:'local'`, no network — is used
  only right after account deletion.)

**OAuth (alternative):** `OAuthButtons` renders "Continue with Google" (enabled by default) and
"Continue with Apple" (disabled by default; Apple isn't configured in Supabase → finding S2). OAuth
redirects to `/auth/callback`. Not usable for headless automation (real provider redirect).

## Session / cookie / JWT / localStorage handling

- **Supabase client** (`lib/supabase.ts`): `createClient(supabaseUrl, supabaseAnonKey, { auth: {
  persistSession: true, autoRefreshToken: true, detectSessionInUrl: true } })`. Created lazily on first
  use from `VITE_SUPABASE_URL` + `VITE_SUPABASE_ANON_KEY` (client-safe; on staging these are the
  `SUPABASE_STAGING_URL` / `SUPABASE_STAGING_ANON_KEY` secrets wired in `deploy-staging.yml`).
- **Storage = browser `localStorage`** (supabase-js default; **not** cookies). Key shape
  `sb-<project-ref>-auth-token` (project ref `rydclyotzdwcbbeyitcx` on staging) holding the JSON
  session `{ access_token, refresh_token, expires_at, user, ... }`. `detectSessionInUrl:true` means the
  email-verification / OAuth redirect hash is consumed automatically on `/auth/callback`. To inject a
  session for a test you'd write that key (e.g. via Playwright `addInitScript` / storageState) from a
  password-grant login response — but the simplest path is just driving the real login form.
- **Tokens are JWTs** (Supabase ES256/asymmetric on the hosted project). The web app treats Supabase as
  **AUTH ONLY**; all app data goes through the FastAPI API.
- **API auth injection** (`lib/api-client.ts`): a request middleware reads the **current** session's
  `access_token` fresh per call and sets `Authorization: Bearer <token>` (never cached/logged/persisted).
  Also injects a W3C `traceparent` per request. On a **401**, a single deduped `refreshSession()` runs
  and the request is retried once with the new token; if refresh fails it signs out (cache reset + guard
  redirect). Bursts of 401s share one in-flight refresh (no refresh storm).

## Backend wiring (FastAPI, `apps/api`)

- **JWT verification** (`app/auth.py::decode_supabase_jwt`): validates signature + `exp` + `aud`
  (`authenticated`), returns a frozen `CurrentUser{ id (UUID from `sub`), email, email_verified }`. The
  accepted algorithms are fixed by **config**, never read from the token header (rejects `alg:none` and
  HS/RS confusion). Two modes: **JWKS/asymmetric** when `SUPABASE_JWKS_URL` is set (the staging/prod
  reality — Supabase signs with ES256), else **HS256 shared secret** (`SUPABASE_JWT_SECRET`, local/CI).
  On staging the deploy sets `SUPABASE_JWKS_URL=<url>/auth/v1/.well-known/jwks.json` — **required**, or
  the API 401s every real user token. Any failure → single `AuthError` → HTTP **401** (no leak).
- **`email_verified` gate** (`app/quota.py`): first gate in the LLM cost-guard chain
  (email-verified → rate-limit → daily-cap → global-budget); unverified → **403 `email_unverified`**.
- **Account deletion** (`DELETE /account`) uses `SUPABASE_SERVICE_ROLE_KEY` to hard-delete the auth user
  via the Auth Admin API; cascades to `profiles` (the S1 FK migration, now merged in #91).

## How the suites authenticate (reference)

- **Live-staging Playwright** (`e2e-staging/`, `playwright.staging.config.ts`, run via
  `cd apps/web && PLAYWRIGHT_TEST_BASE_URL=https://lengua-staging.vercel.app pnpm test:e2e-staging`):
  not in CI, no `webServer`, hits the live origin, 1 retry, 90s timeout. `fixtures.ts::login(page)`
  fills `Email` + `Password (exact)` with `DEMO_EMAIL`/`DEMO_PASSWORD` and waits for the "Dashboard"
  heading. The consent banner is pre-dismissed via `localStorage['lengua.analytics-consent']='denied'`
  in an init script. Structure-only (never clicks Generate → zero LLM spend).
- **Local FakeLLM E2E** (`e2e/auth.spec.ts`): the route-gating smoke runs anywhere; the real
  sign-up/login/logout flows are gated on `E2E_STACK=1` against the ephemeral Supabase + API stack
  seeded by `seed_e2e.py`. The sign-up test asserts the **"Check your email"** notice (proving
  confirmation is required); the login test uses the seeded demo account.
- **Backend integration** (`tests/supabase_auth.py`): `create_confirmed_user` (admin, pre-confirmed),
  `login` (password grant → real JWT), `signup` (public path, stays unconfirmed), `delete_user`/`get_user`.
  `tests/auth_helpers.py` mints HS256 Supabase-shaped JWTs for pure-unit auth (no live GoTrue).
