# docs

Project documentation: privacy policy, legal, and operational runbooks.

- [`streamlit-parity.md`](streamlit-parity.md) — Legacy Streamlit → React parity checklist (task
  4.11.1); marks the legacy app deprecated/retained-for-reference.
- [`runbook.md`](runbook.md) — operational runbook: health checks, deploy, rollback, run a
  migration, rotate a secret, respond to a budget-exhausted alert, restore from backup, store-release
  checklist, on-call (Phase 9), and the legacy SQLite → Postgres import.
- [`privacy-policy.md`](privacy-policy.md) — the GDPR privacy policy (Phase 8): data collected,
  Supabase (EU) storage, the LLM provider (Gemini), lawful bases, sub-processors, retention, and how
  to export/delete your data. Published at `/privacy` on the web app.
- [`store-listing.md`](store-listing.md) — the single source of truth for app-store metadata (Phase
  8): the published URLs, store-listing copy (name/subtitle/description/keywords/category), the
  data-inventory matrix behind the Apple/Play data-safety answers, and per-processor data residency.
- [`byok-seam.md`](byok-seam.md) — bring-your-own-key design note (Phase 3 seam).
- [`../architecture.html`](../architecture.html) — interactive single-file architecture map of the
  monorepo (PR #94); open it directly in a browser.

The `runbook.md` On-call and Store-release sections remain Phase-0 placeholders filled in at launch
(Phase 9). Relative links across these docs, and the `store-listing.md` character limits, are checked
in CI (`scripts/check_doc_links.py` + `scripts/check_store_listing.py`).
