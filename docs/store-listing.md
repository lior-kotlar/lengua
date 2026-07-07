# Store listing & data-safety source of truth

The **single source** for Lengua's app-store metadata and privacy/data-safety answers. App Store
Connect (Apple) and Google Play Console both reference the identical values here, so the two stores
stay consistent and the privacy policy, the nutrition labels, and the Play Data Safety form all agree.

Related: the user-facing policy is [`privacy-policy.md`](privacy-policy.md); the region-of-record
table is in [`runbook.md`](runbook.md) (Data residency). Owner-entered store-console steps and the
device screenshots live in [`../planning/tasks/phase-8-compliance-store.md`](../planning/tasks/phase-8-compliance-store.md).

> **Placeholders to confirm at launch (owner):** the URLs below use the pre-launch host
> `https://lengua.app` and contact `privacy@lengua.app`. Swap to the real prod web domain + a
> monitored inbox before submitting to either store.

## Published URLs

The canonical URLs both stores must reference (tasks 8.1.3 / 8.3.2). Each is a public route on the
web app (reachable without signing in).

| Purpose | URL |
| --- | --- |
| Privacy policy | `https://lengua.app/privacy` |
| Support / contact | `https://lengua.app/support` |
| Account-deletion request (external, no login) | `https://lengua.app/delete-account` |

## Store-listing copy

Written once and reused per store (task 8.7.1). The character-limited fields below are capped at the
**shorter** of the two stores' limits so one set of copy fits both (Apple name/subtitle 30, Play
short description 80, Apple keywords 100, both full description 4000). The machine block is validated
in CI by `scripts/check_store_listing.py`.

<!-- store-fields:start -->
- name: Lengua
- subtitle: Learn words in real sentences
- short_description: Enter words; AI writes example sentences you review as flashcards.
- keywords: language,learning,flashcards,vocabulary,spaced repetition,CEFR,Anki,study,practice
- category: Education
- privacy_url: https://lengua.app/privacy
- support_url: https://lengua.app/support
<!-- store-fields:end -->

**Full description:**

<!-- full-description:start -->
Lengua turns the words you want to learn into real practice. Enter your vocabulary and an AI language
model writes natural example sentences that actually use them — then every sentence becomes
spaced-repetition flashcards (recognition + production) scheduled with the proven FSRS algorithm, so
you review each word exactly when you're about to forget it.

Why Lengua:
- You choose the words. Add any vocabulary and see it used in context, not in isolation.
- Natural sentences, on the spot. The AI writes example sentences at your level (CEFR), which adapts
  as you review.
- Real spaced repetition. FSRS-scheduled recognition and production cards so reviews stay efficient.
- Tap any word. Get a quick explanation of any word in a sentence while you review.
- Built for many languages, including right-to-left scripts and vowel marks (e.g. Arabic, Hebrew).
- Your data is yours. Export everything as JSON or delete your account and all its data at any time.

Privacy first: analytics are strictly opt-in, your data is stored in the EU, and you can export or
delete it whenever you like. Lengua is for learners who want focused, personalized practice from the
exact words they care about.
<!-- full-description:end -->

## Data-inventory matrix (Apple labels + Play Data Safety)

The authoritative mapping of every data type Lengua handles to its purpose, whether it's **linked to
your identity**, and whether it's used for **tracking** (task 8.4.1). This is the single source both
the Apple **App Privacy** questionnaire and the Google Play **Data Safety** form are filled from — the
answers must match this table exactly. Lengua does **no** cross-app/advertising tracking, so "Used for
tracking?" is **No** for every row.

| Data type | Collected? | Purpose | Linked to identity? | Used for tracking? |
| --- | --- | --- | --- | --- |
| **Email address** | Yes | Account creation & authentication (incl. Google sign-in) | Yes | No |
| **User content — vocabulary & generated sentences** | Yes | App functionality: generate sentences, schedule/serve flashcards; sent to the LLM provider to produce results | Yes | No |
| **Other user content — languages, review history, proficiency, settings** | Yes | App functionality: scheduling, progress, preferences | Yes | No |
| **Product analytics (usage events)** | Only with opt-in consent | Analytics: understand & improve usage; anonymized | No | No |
| **Crash & diagnostic data** | Yes | App functionality / stability: detect and fix errors | Not intentionally (no user content included) | No |
| **Identifiers — auth user id / session tokens** | Yes | Authentication & session management | Yes | No |

**Third parties the data reaches** (processors, not sold): Supabase (store + auth), the LLM provider
(Google Gemini in prod — vocabulary + generated sentences), PostHog (opt-in analytics), Sentry (crash
diagnostics). Full list + regions below and in [`privacy-policy.md`](privacy-policy.md).

**Reviewer sign-off:** the Apple App Privacy answers and the Play Data Safety answers must be entered
to match this table row-for-row; any divergence is recorded here with the reason. (Owner enters the
questionnaires — tasks 8.4.2 / 8.5.1 — and notes the confirmation here.)

## Data residency (per processor)

The region each data processor operates in, for the residency answers (task 8.2.2). The
region-of-record (with the exact Supabase region string captured at cutover) is maintained in
[`runbook.md`](runbook.md).

| Processor | Data | Region |
| --- | --- | --- |
| Supabase (Postgres + Auth) | Account + all learning data | EU |
| Google Cloud Run | Backend API (in transit) | EU (`lengua-prod`) |
| Vercel | Web frontend (static assets) | Global edge — no user data at rest |
| Google (Gemini) | Vocabulary + generated sentences | May process outside the EEA — SCCs / adequacy |
| PostHog | Opt-in analytics events | EU host |
| Sentry | Crash diagnostics | Sentry org region |

## Encryption & age rating (intended answers)

Owner-entered in the store consoles (tasks 8.4.3 / 8.6); the intended answers are recorded here so the
consoles match:

- **Export compliance / encryption (Apple):** the app uses only standard HTTPS/TLS — **exempt**
  (`ITSAppUsesNonExemptEncryption = NO`). No non-exempt encryption.
- **Age rating:** a language-learning app whose example sentences are AI-generated from
  user-supplied words (user-generated text via the LLM) — answer the UGC/content questions honestly;
  record the resulting Apple rating + Play IARC rating here once assigned.
