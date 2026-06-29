# infra/

Infrastructure, CI/CD, and Supabase configuration.

- `github-actions/` — CI/CD workflows (the per-PR quality gate from Phase 0 group 0.5; the
  deploy pipeline from Phase 6). Active workflows live in `.github/workflows/`.
- `supabase/` — Supabase CLI config, SQL policies (RLS), and seed scripts.
- `branch-protection.md` — the committed record of required status checks and the
  branch-protection policy on `main` (Phase 0 task 0.6.2).
