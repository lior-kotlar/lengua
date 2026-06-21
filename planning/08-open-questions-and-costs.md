# 08 — Open Questions, Costs & Backlog

## Decisions confirmed (planning round 2)

| Decision | Choice | Consequence |
| --- | --- | --- |
| **Audience / scale** | Small public, slow growth (tens–low hundreds) | Operator-funded Gemini stays free via per-user caps + the global daily kill-switch; a **BYOK seam** is designed in (Phase 3) as the growth escape hatch. |
| **Per-PR quality gate** | 100% pass + 80% coverage (backend **and** frontend) + Playwright **E2E on every PR** | Full spec in [09-testing-quality.md](09-testing-quality.md); E2E uses an ephemeral stack with **Gemini stubbed** to stay fast/free. |
| **Offline review** | Fast-follow after launch | v1 is online-first; offline cache + grade-queue sync is the #1 post-launch item. |
| **Audio / TTS** | Later; **on-device/browser TTS first** | No cloud-TTS cost in v1; revisit paid TTS only if quality demands it. |

## Decisions confirmed (planning round 3)

| Decision | Choice | Consequence |
| --- | --- | --- |
| **v1 feature scope** | Keep all current features | Generate, Review, Discover, Settings, multi-language, vowel marks, tap-a-word, Anki import all ship. Discover + tap-a-word add (capped) Gemini cost. |
| **Monetization** | Paid-ready, not built | Add `profiles.plan` (default `free`) + reuse usage metering; a paid tier (higher caps / BYOK) becomes a config change later. No payment code in v1. |
| **Accounts** | Signup required (no guest) | Simplest + best abuse control for the operator key; a seeded **demo account** serves store reviewers. |
| **Mobile updates** | OTA web-bundle updates | Push JS/UI fixes via a live-update channel (Capgo/OSS) without store review; native changes still go through the stores. |

## Decisions confirmed (planning round 4)

| Decision | Choice | Consequence |
| --- | --- | --- |
| **Auth email** | Free-tier SMTP provider | Wire Resend/Brevo (free) as **custom SMTP** in Supabase; set SPF/DKIM for deliverability. Built-in Supabase email is dev-only. |
| **Region / privacy** | EU region, GDPR-strict | Create Supabase (and ideally Cloud Run/Vercel) in an **EU region**; add an **analytics consent** step plus data **export + deletion**. |
| **Product analytics** | PostHog, consent-gated | Free tier, anonymized, EU-hosted, behind consent; measure signup → first-generate → first-review funnels + retention. Distinct from OTel/Sentry. |
| **Review reminders** | Daily local notification (v1) | On-device reminder when cards are due (permission prompt + scheduling); free/offline. Server push is post-launch. |

## Decisions confirmed (planning round 5)

| Decision | Choice | Consequence |
| --- | --- | --- |
| **UI stack** | Tailwind CSS + shadcn/ui | Copy-in components, full control, strong RTL support for Arabic/Hebrew. |
| **App identity** | "Lengua", `com.lengua.app` | Use across stores + OAuth redirect setup; confirm name/id availability. |
| **Login methods** | Email + Google + Apple | Broadest reach; Apple is mandatory on iOS because Google is offered. |
| **Language entry** | Free text (any language) | Keep today's behavior; Gemini handles any language. No curated list to maintain. |

## Decisions confirmed (planning round 6)

| Decision | Choice | Consequence |
| --- | --- | --- |
| **LLM provider** | **Groq free tier** the default (e.g. `gemma2-9b-it` / a Qwen model); **Gemini** a one-env-var switch for later / prod | **All development uses Groq for now** (no card, ~30 RPM / ~1K RPD per model). `LLM_PROVIDER` flips to Gemini in any env — done later to validate real prompt output and as the prod default — with no code change. One provider interface + the same quota gate; non-Gemini providers use JSON mode and parse into `GeneratedCard` / `WordNote`. Accept lower model quality on Groq during dev — fine for wiring the pipeline. |

## Decisions still to confirm (with my recommended defaults)

The plan assumes these defaults so it's actionable; flag any you want to change.

| # | Question | Recommended default | Notes |
| --- | --- | --- | --- |
| 1 | **2 or 3 environments?** | **3**: local + staging + prod | `local` via Supabase CLI keeps us inside the free hosted-project limit. Drop staging for 2. |
| 2 | **Backend host** | **Cloud Run** | Fly.io is the fallback; avoid Render free (sleeps). |
| 3 | **Observability backend** | **Grafana Cloud** (+ Sentry) | Honeycomb (traces) or self-hosted SigNoz are alternatives. |
| 4 | **Rate-limit store** | Postgres counters first; **Upstash Redis** if needed | Avoids a dependency until load justifies it. |
| 5 | **App identifiers** | ✅ Decided (round 5): `com.lengua.app` — still confirm availability | Needed for both stores + OAuth redirect setup. |
| 6 | **Retire Streamlit?** | Keep until React reaches parity, then remove | Lets you dogfood without regressions. |
| 7 | **Social logins set** | Email + Google + Apple | Apple is mandatory on iOS if Google is offered. |
| 8 | **Per-user daily caps (actual numbers)** | Set from Gemini's *current* free limits ÷ expected users, with margin | The global kill-switch is the hard backstop. |
| 9 | **UI component library** | ✅ Decided (round 5): Tailwind + shadcn/ui | Strong RTL support. |
| 10 | **Custom domain?** | Free subdomains for v1 | ~$10/yr if you want a branded domain later. |

## Costs — the honest picture

### Unavoidable (you said no paying — these are the exceptions)

| Item | Cost | When |
| --- | --- | --- |
| **Apple Developer Program** | **$99 / year** | Before any App Store submission (start early — verification can take days). |
| **Google Play registration** | **$25 one-time** | Before any Play submission. |

### Can stay $0 (with the guardrails in this plan)

- **LLM provider** — **Groq** free tier by default for all dev now (no card required); **Gemini**
  free tier switched on later. Both kept free by per-user caps + the global daily kill-switch.
  *The one thing that can surprise you; the cost-guard dashboard + alert exist for this.*
- Supabase, Cloud Run, Vercel, Grafana Cloud, Sentry, GitHub Actions, Upstash — all free tier.

### Optional later

- Custom domain (~$10/yr). Paid tiers only if you outgrow free limits (more users, more
  telemetry retention, always-on backend).

## Accounts to create (Phase 0 checklist)

- [ ] GitHub (repo + Actions)
- [ ] Supabase (org + staging/prod projects + CLI)
- [ ] Google Cloud (Cloud Run + Secret Manager)
- [ ] Vercel
- [ ] Groq Console (free-tier API key — the **default** LLM provider; needed now)
- [ ] Google AI Studio (Gemini API key — **later**, only when flipping `LLM_PROVIDER=gemini`)
- [ ] Grafana Cloud
- [ ] Sentry
- [ ] **Apple Developer ($99/yr)**
- [ ] **Google Play Console ($25)**
- [ ] (optional) Upstash, domain registrar

## "Anything else we want to add?" — backlog

Not needed for v1; ranked roughly by value for a learning app.

1. **Offline review + sync** — cache the due batch, queue grades offline, flush on reconnect.
   Huge for a flashcard app (subway studying). Generation stays online.
2. **Server push notifications** — streak/review reminders via FCM/APNs. (v1 uses on-device
   **local** notifications, which are simpler and free.)
3. **Product analytics** — PostHog free tier: funnels (signup → first generate → first review),
   retention, feature usage.
4. **TTS audio** — pronounce sentences/words. *Decided: post-v1, on-device/browser TTS first
   (free); only consider cost-gated cloud TTS if on-device quality is insufficient.*
5. **Streaks / gamification** — daily streak, goals, gentle nudges; strong retention lever.
6. **Import/export & shared decks** — beyond the Anki import you already have; share or publish
   decks; CSV/Anki export.
7. **UI internationalization** — the app *teaches* languages but its own UI is English; i18n
   the interface for non-English speakers.
8. **Spaced-repetition insights** — per-language progress charts, forecast of upcoming reviews.
9. **Admin/support tooling** — impersonation-free support views, abuse review, manual budget
   override.
10. **Accessibility pass** — screen-reader labels, contrast, font scaling (also helps store review).

## Risks to watch

- **Gemini latency/limits** shaping UX (slow generation) and the free-tier ceiling vs user
  growth. The cost guard mitigates the bill; the **BYOK seam** (Phase 3) is the planned switch
  if "slow growth" turns into real growth — flip it on instead of paying or rewriting.
- **Supabase free-tier project limits / idle pausing** — confirm at setup; the local CLI stack
  is the mitigation.
- **Apple review friction** — account deletion, Sign in with Apple, and privacy labels are the
  usual rejection causes; all are in Phase 7–8.
- **RTL/diacritics rendering in the mobile webview** — test on real devices early (Phase 7).
- **Scope creep** — the backlog above is post-v1 on purpose; protect the launch.
