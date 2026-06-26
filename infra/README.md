# infra

Infrastructure & CI/CD supporting docs.

The per-PR CI quality gate lives in `.github/workflows/` (GitHub auto-discovers workflows only
there). This directory holds the committed CI/branch-protection docs added in Phase 0 groups
0.5–0.6 (e.g. `ci/README.md`, `branch-protection.md`).

The **Supabase CLI config** (the file the CLI actually reads) lives at the repo-root `supabase/`
(`config.toml`, `migrations/`, `templates/`). Owner-only Auth setup that can't be committed —
Google/Apple OAuth credentials and custom SMTP (Resend) — is documented in
[`supabase/oauth-setup.md`](supabase/oauth-setup.md).
