# Privacy Policy

> **Placeholder.** This is a Phase 0 stub. The full, legally-reviewed privacy
> policy is written in Phase 8 (compliance & store) before any public launch.
> Do not treat this as the published policy.

## Summary of data handling (current behavior)

This section records, at a high level, where Lengua stores data and what leaves
the app, so the eventual policy starts from the truth.

### Data we store

- **Storage provider — Supabase.** User accounts and all learning data
  (profiles, languages and their CEFR levels, vocabulary words, generated
  sentences, and the FSRS-scheduled flashcards plus their review history) are
  stored in **Supabase** (managed Postgres + Auth). Authentication (email and
  Google sign-in) is handled by Supabase Auth.

### Data sent to the LLM provider

- **Vocabulary and sentences go to the active LLM provider.** When you generate
  cards, the vocabulary words you enter — and the example sentences produced from
  them — are sent to the configured large-language-model (LLM) provider to write
  natural example sentences, vocalize them, and explain tapped words.
- **Active provider depends on environment.** The provider is selected by the
  `LLM_PROVIDER` setting:
  - **Groq (`llama-3.1-8b-instant`)** is the active provider for all development
    and CI today.
  - **Google Gemini** is reserved for production and will become the active
    provider when production flips to it.
  Only one provider is active at a time; your vocabulary and the generated
  sentences are sent to whichever provider is currently configured.

### Product analytics (opt-in only)

- **Analytics is off until you opt in.** The web app shows a first-run consent
  banner. No product-analytics SDK is loaded and no analytics events are
  collected unless you explicitly accept; the choice is remembered on your
  device, and declining (or never deciding) means nothing analytics-related ever
  loads. PostHog is the intended analytics provider (wired in a later phase);
  even after opt-in it loads only when an analytics key is configured for the
  deployment.

## To be completed in Phase 8

- Legal basis, data-subject rights, and GDPR consent/residency.
- Data retention and deletion (account export + delete cascade).
- Sub-processor list and contact details.
- Cookie / local-storage disclosure for the web app.
