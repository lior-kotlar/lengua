# Supabase Auth — OAuth & custom SMTP setup (owner runbook)

Human-facing setup steps for the Supabase Auth providers and transactional-email delivery that
**cannot be committed to git** because they depend on real secrets / paid accounts. The
version-controlled wiring lives in [`supabase/config.toml`](../../supabase/config.toml) (repo
root — the file the Supabase CLI actually reads); this doc explains what the owner must create in
the various dashboards and which environment variables / Supabase secrets to populate.

> **Status (Phase 2.1/2.2):** the config is scaffolded and the email/password flow (confirmation
> required + password policy + branded templates, tasks 2.1.1/2.1.4/2.2.3) is fully configured and
> tested. The items below are **owner-only** and intentionally left disabled/blank until the owner
> provides credentials:
>
> | Item | Task | Blocked on |
> |------|------|-----------|
> | Google OAuth | 2.1.2 | A Google Cloud OAuth client (id + secret) |
> | Apple OAuth | 2.1.3 | A **paid** Apple Developer account (Service ID + key) — also a Phase 7 concern |
> | Custom SMTP (Resend) | 2.2.1 | Resend account + API key, set in **both** Supabase projects |
> | SPF / DKIM / DMARC DNS | 2.2.2 | DNS access for the sending domain |

How `config.toml` reads secrets: every credential uses `env(NAME)` substitution, so nothing
sensitive is committed. For the **local** CLI stack, export the vars (or put them in an untracked
`.env`) before `supabase start`. For the **hosted** staging/prod projects, set the same values in
the Supabase dashboard (Authentication → Providers / Project Settings) or via
`supabase secrets set`.

---

## 1. Google OAuth (task 2.1.2)

Config block: `[auth.external.google]` (currently `enabled = true`, credentials via env). Until the
two secrets are set the provider is inert — the stack still boots, but `Sign in with Google` will
not work and the `/authorize?provider=google` 302-to-Google probe in the task's `verify:` line
cannot pass.

**Google Cloud Console steps:**

1. Create / select a project at <https://console.cloud.google.com/>.
2. **APIs & Services → OAuth consent screen**: choose **External**, set the app name (`Lengua`),
   the support email, the app logo, and the authorized domains (the prod web domain + the Supabase
   project domain `*.supabase.co`). Add the `email`, `profile`, `openid` scopes. Publish (or add
   the owner + reviewer as test users while in testing).
3. **APIs & Services → Credentials → Create credentials → OAuth client ID → Web application.**
   - **Authorized JavaScript origins:** the web origins (local `http://localhost:5173`, staging,
     prod) — match `additional_redirect_urls` in `config.toml`.
   - **Authorized redirect URIs:** the Supabase callback for each project:
     - Local CLI: `http://127.0.0.1:54321/auth/v1/callback`
     - Hosted: `https://<project-ref>.supabase.co/auth/v1/callback`
4. Copy the generated **Client ID** and **Client secret**.

**Wire the secrets:**

```bash
# Local stack (export before `supabase start`):
export SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID="<client-id>.apps.googleusercontent.com"
export SUPABASE_AUTH_EXTERNAL_GOOGLE_SECRET="<client-secret>"
```

Hosted: set the same two values in each Supabase project (dashboard → Authentication → Providers →
Google, or `supabase secrets set`).

**Verify (owner, once creds exist):**

```bash
curl -sI "http://127.0.0.1:54321/auth/v1/authorize?provider=google" | grep -i location
# → 302 Location: https://accounts.google.com/o/oauth2/v2/auth?...
```

---

## 2. Apple OAuth (task 2.1.3)

Config block: `[auth.external.apple]` (`enabled = false` — owner must flip after supplying the
secret). **Requires a paid Apple Developer Program account ($99/yr).** Apple Sign-In is mandatory
on iOS once any other third-party login (Google) is offered, so this lands with the Phase 7 mobile
work; it is scaffolded here only.

**Apple Developer steps:**

1. **Certificates, Identifiers & Profiles → Identifiers → App ID** for the app (e.g.
   `app.lengua`); enable the **Sign In with Apple** capability.
2. Create a **Services ID** (e.g. `app.lengua.signin`) — this is the OAuth `client_id`. Configure
   its **Sign In with Apple** → Web Authentication: add the web domain and the return URL
   `https://<project-ref>.supabase.co/auth/v1/callback`.
3. **Keys → +**: create a key with **Sign In with Apple** enabled; download the `.p8` private key
   and note the **Key ID**. Note your 10-character **Team ID**.
4. Generate the **client-secret JWT** (ES256, signed with the `.p8`, `iss = Team ID`,
   `sub = Service ID`, `aud = https://appleid.apple.com`, max 6-month expiry). Supabase's docs and
   the `supabase` CLI both describe this; it must be regenerated before expiry.

**Wire the secrets:**

```bash
export SUPABASE_AUTH_EXTERNAL_APPLE_CLIENT_ID="app.lengua.signin"   # the Service ID
export SUPABASE_AUTH_EXTERNAL_APPLE_SECRET="<generated ES256 client-secret JWT>"
```

Then set `enabled = true` under `[auth.external.apple]` (or enable it in the hosted dashboard).

**Verify (owner, once creds exist):**

```bash
curl -sI "http://127.0.0.1:54321/auth/v1/authorize?provider=apple" | grep -i location
# → 302 Location: https://appleid.apple.com/auth/authorize?...
```

---

## 3. Redirect / allow-list URLs (task 2.1.4)

`site_url` + `additional_redirect_urls` in `config.toml` are the **allow-list** of origins that
OAuth callbacks and email links may return to. Keep them in sync with the deployed web origins and
the native deep-link scheme:

- **Local:** `http://localhost:5173` (Vite dev), `:4173` (preview), `:3000` (alt).
- **Staging / Prod web:** the Vercel preview/staging/prod domains — **owner: confirm the final
  custom domain** and replace the `lengua-staging.vercel.app` / `lengua.app` placeholders.
- **Native (Capacitor):** `capacitor://localhost` + the `app.lengua://` deep-link scheme — **owner:
  confirm the final bundle id / URL scheme** when the mobile app is built (Phase 7).

An origin not matched by `site_url` or one of the `additional_redirect_urls` globs is rejected:
GoTrue ignores the requested `redirect_to` and falls back to `site_url`.

---

## 4. Custom SMTP — Resend (task 2.2.1, owner-only)

The built-in Supabase mailer is dev-only and heavily rate-limited; production verification / reset
/ magic-link mail must go through an authenticated domain. **Not done here** — recorded for the
owner.

1. Create a [Resend](https://resend.com) account; add and verify the sending domain.
2. In **each** Supabase project (staging + prod): Authentication → Emails → SMTP Settings → enable
   custom SMTP with the Resend host/port/user and the API key as the password. The matching
   `config.toml` block is `[auth.email.smtp]` (commented out; uses `env(...)` for the key — never
   commit it).
3. Set a branded sender (e.g. `no-reply@<domain>`) and sender name `Lengua`.
4. Bump `[auth.rate_limit] email_sent` above the default `2/hour` once real SMTP is enabled (the
   default only applies with custom SMTP and is far too low for real signups).

The branded templates in [`supabase/templates/`](../../supabase/templates) (task 2.2.3) apply to
both the built-in and the custom SMTP sender — no change needed when SMTP is switched on.

### SPF / DKIM / DMARC (task 2.2.2, owner-only)

Add the DNS records Resend provides for the sending domain (SPF `TXT`, DKIM `CNAME`/`TXT`, and a
DMARC `TXT` at `p=none` to start). Verify with `dig TXT <domain>` / `dig TXT
<selector>._domainkey.<domain>` and a mail-tester run (SPF=pass, DKIM=pass). Record the final
records in [`docs/runbook.md`](../../docs/runbook.md).
