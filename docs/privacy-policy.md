# Privacy Policy

**Last updated:** 2026-07-06

This Privacy Policy explains what personal data Lengua ("Lengua", "we", "us") collects when you
use the Lengua language-learning app (web and mobile), why we collect it, the legal bases we rely
on, who we share it with, and the rights you have under the EU General Data Protection Regulation
(GDPR) and equivalent laws. It applies to the Lengua app and website at `https://lengua.app`.

> Lengua is a personal language-learning app: you enter vocabulary words, an AI language model
> writes natural example sentences using them, and each sentence becomes spaced-repetition
> flashcards you review over time.

## 1. Who is responsible for your data

Lengua is the **data controller** for the personal data described in this policy. If you have any
question about this policy or want to exercise your rights, contact us at:

- **Email:** privacy@lengua.app

We aim to respond to any data-rights request within 30 days, as required by the GDPR.

## 2. What data we collect, and why

We collect only what the app needs to work. The categories are:

| Category | What it is | Why we collect it |
| --- | --- | --- |
| **Account & authentication** | Your email address and the authentication identifiers created when you sign up (including Google sign-in, if you use it). | To create and secure your account and sign you in. |
| **Learning content** | The languages and CEFR levels you add, the vocabulary words you enter, the example sentences generated for you, your flashcards, your review history (ratings and timestamps), and your derived proficiency. | To provide the core service: generating sentences, scheduling reviews, and tracking your progress. |
| **Content sent for AI generation** | The vocabulary words you submit and the sentences generated from them. | Sent to our AI language-model provider so it can write example sentences, add vowel marks, and explain words (see §4). |
| **Product analytics (opt-in only)** | Anonymized, aggregated usage events (for example, which screens are used). No analytics are collected unless you explicitly opt in. | To understand how the app is used and improve it. See §8. |
| **Error & diagnostic data** | Technical error reports (stack traces, device/browser type, a request identifier). We do not intentionally include your learning content in error reports. | To detect, diagnose, and fix crashes and bugs, and to keep the service secure and reliable. |
| **Technical & device data** | Data stored locally in your browser/app (your theme, active language, and your analytics-consent choice) and the session tokens that keep you signed in. | To make the app function and remember your preferences on your device. |

We do **not** sell your personal data, we do **not** use it for advertising, and we do **not** use
it to build cross-site tracking or advertising profiles.

## 3. Where your data is stored — Supabase (EU)

Your account and all your learning data (profile, languages and their CEFR levels, vocabulary,
generated sentences, flashcards and their review history, and proficiency) are stored in
**Supabase** — a managed PostgreSQL database and authentication service — hosted in an **EU
region**. Authentication (email/password and Google sign-in) is handled by Supabase Auth.

The Lengua backend runs on **Google Cloud Run in an EU region**, and the Lengua web frontend is
served by **Vercel**. The EU region of record for each data-storing service is listed in our
internal data-residency record and in the store-listing metadata that accompanies our app-store
submissions.

## 4. AI language-model provider (the "LLM provider")

Generating example sentences, adding vowel marks, and explaining tapped words are done by a
third-party large-language-model (LLM) provider. When you generate cards, the vocabulary words you
enter — and the example sentences produced from them — are sent to the active LLM provider for that
purpose. This content is processed to return your results and is not used by us to build advertising
profiles.

The active provider depends on the environment the app runs in, and only one provider is active at
a time:

- **Google Gemini** is the provider for the production app that you use.
- **Groq** (`llama-3.1-8b-instant`) is used only in our internal development and testing
  environments, never with your real account data.

Because Google Gemini may process this content on infrastructure outside the European Economic Area
(EEA), such transfers are protected by appropriate safeguards — Standard Contractual Clauses and/or
an adequacy decision — as described in §6.

## 5. Legal bases for processing (GDPR Article 6)

We rely on the following legal bases:

- **Performance of a contract** (Art. 6(1)(b)) — for your account, your learning content, and
  sending your vocabulary/sentences to the LLM provider to deliver the results you asked for. This
  is the service you signed up for.
- **Consent** (Art. 6(1)(a)) — for optional product analytics. Analytics load only after you
  explicitly opt in, and you can withdraw consent at any time (see §8).
- **Legitimate interests** (Art. 6(1)(f)) — for keeping the service secure, preventing abuse, and
  diagnosing errors (error/diagnostic data). We balance these interests against your rights and
  keep this data minimal.

## 6. International data transfers

Your account and learning data are stored in the EU (§3). Some sub-processors — in particular the
LLM provider (Google) — may process data on infrastructure located outside the EEA. Where that
happens, the transfer is protected by an appropriate GDPR transfer mechanism, such as the European
Commission's Standard Contractual Clauses or an adequacy decision for the destination country.

## 7. Sub-processors

We share data only with the service providers needed to run Lengua. Each acts as a processor on our
behalf under a data-processing agreement:

| Sub-processor | Purpose | Data involved | Region / safeguard |
| --- | --- | --- | --- |
| **Supabase** | Database & authentication (the primary data store) | Account data + all learning content | EU region |
| **Google (Gemini)** | AI sentence generation, vowelization, word explanations (production) | Vocabulary words + generated sentences | May process outside the EEA; SCCs / adequacy |
| **Groq** | AI generation in development/testing only | Test data only — never your real account content | Development only |
| **PostHog** | Product analytics (only if you opt in) | Anonymized usage events | EU host |
| **Sentry** | Error & crash diagnostics | Technical error reports | Data-processing agreement in place |
| **Google Cloud (Cloud Run)** | Backend API hosting | Requests in transit | EU region |
| **Vercel** | Web frontend hosting | Web requests in transit | Global edge; static assets |

## 8. Analytics and your consent

Product analytics are **off until you opt in**. On first run the web app shows a consent banner. No
analytics SDK is loaded and no analytics events are collected unless you explicitly accept. Your
choice is remembered on your device, and declining (or never deciding) means nothing
analytics-related ever loads for that session. Even after you opt in, analytics load only when an
analytics key is configured for the deployment. You can change your choice at any time from the
app's Settings screen.

## 9. Data retention

- **While your account is active**, we keep your account and learning data so the service works.
- **When you delete your account** (see §10), your learning data and your authentication account are
  permanently erased. Deletion cascades across all your data — languages, vocabulary, generated
  sentences, flashcards, review history, proficiency, and settings — and removes your Supabase
  authentication record. Residual copies in encrypted backups are purged on the normal backup
  rotation.
- **Error/diagnostic data** is retained only as long as needed to investigate issues and is then
  discarded.

## 10. Your rights, and how to export or delete your data

Under the GDPR you have the right to **access**, **rectify**, **erase**, **restrict**, **object to**
the processing of your personal data, to **data portability**, and to **withdraw consent** at any
time. You also have the right to lodge a complaint with your local data-protection authority.

Lengua gives you direct, self-service control over the two most important rights:

- **Export your data (portability).** In the app, open **Account → Export my data** to download a
  machine-readable JSON file containing your profile, languages, cards, review history, proficiency,
  and settings.
- **Delete your account and data (erasure).** You can delete your account in **two** ways, and both
  trigger the same permanent, cascading deletion (including removal of your Supabase authentication
  record):
  1. **In the app:** open **Account → Delete account** and confirm.
  2. **Without signing in:** use the public deletion-request form at
     `https://lengua.app/delete-account`. You submit your account email and confirm ownership via a
     link we email you; confirming completes the deletion. This form is available even if you no
     longer have the app installed.

To exercise any other right, email **privacy@lengua.app**.

## 11. Cookies and local storage

Lengua does not use third-party advertising or cross-site tracking cookies. The app stores a small
amount of data locally in your browser/app to function: your theme and active-language preferences,
your analytics-consent choice, and the authentication session tokens that keep you signed in.
Clearing your browser storage will sign you out and reset these preferences.

## 12. Children

Lengua is not directed to children under the age of 16, and we do not knowingly collect personal
data from children under 16. If you believe a child has provided us personal data, contact us at
privacy@lengua.app and we will delete it.

## 13. Changes to this policy

We may update this policy from time to time. When we make material changes we will update the "Last
updated" date above and, where appropriate, notify you in the app. Continued use of Lengua after an
update means you accept the revised policy.

## 14. Contact

Questions, requests, or complaints about this policy or your personal data:

- **Email:** privacy@lengua.app

If you are in the EU/EEA, you also have the right to complain to your national data-protection
supervisory authority.
