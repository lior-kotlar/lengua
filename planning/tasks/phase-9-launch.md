# Phase 9 — Launch (all platforms together)

> **Effort:** S  ·  **Depends on:** Phases 0–8 complete (web parity, infra/CI/CD, mobile packaging, compliance & store readiness all done)  ·  **Unlocks:** v1 is live; post-launch backlog
> **Context:** phases 0–6 (web + infra/CD, M1–M3 + the M4 staging leg) are recorded in [`../../CHANGELOG.md`](../../CHANGELOG.md); launch coordinates web + iOS + Android.
> The per-PR quality gate applies to EVERY task below: each lands via a PR that is 100% green + ≥80% coverage (backend & frontend) + Playwright E2E. A task is not done until its tests keep coverage ≥80%.

**Goal:** web + iOS + Android are live on production at the same time, every v1 success criterion (the Phase 9 exit gate below) is met, and the first 48 hours are watched on dashboards/alerts with a rollback ready.

**Status legend:** [ ] todo · [~] in progress · [x] done · [!] blocked

---

## 9.1 — Final production smoke test (all platforms)  ·  S

_Context: before any store submission or domain cut-over, prove the full Generate → Save → Review → Discover loop works end-to-end on prod across web, iOS, and Android, on real private per-user data. This is the launch go/no-go._

- [ ] **9.1.1** Run a scripted **web** prod smoke test: sign up a brand-new throwaway user (email + Google + Apple) against the prod stack and complete Generate → Save → Review → Discover, confirming the new user only sees their own data.
      verify: a Playwright run against the prod URL signs up a fresh user, generates a sentence, saves both cards, grades a review, and fetches a Discover suggestion — all asserts pass and a second user's data is never visible.
- [ ] **9.1.2** Run a **TestFlight (iOS)** smoke test of the same loop on a real device against prod: install the release-candidate build, sign up, and complete Generate → Save → Review → Discover including the daily-review local notification permission prompt.
      verify: the TestFlight build installs and runs the full loop on a physical iPhone against the prod API; a checklist (login, generate, review, discover, RTL render, notification permission) is recorded with screenshots in the launch runbook.
      depends: Phase 7 signed iOS build, Phase 8 TestFlight track
- [ ] **9.1.3** Run a **Play internal-testing (Android)** smoke test of the same loop on a real device against prod: install the internal-track build, sign up, and complete the full loop including back-button/keyboard/RTL behavior.
      verify: the Play internal-testing build installs and runs the full loop on a physical Android device against the prod API; the same checklist is recorded with screenshots in the launch runbook.
      depends: Phase 7 signed Android build, Phase 8 Play internal-testing track
- [ ] **9.1.4** Verify the **store reviewer/demo account** exercises the full loop on prod from a clean state (so Apple/Google reviewers can complete review without your data).
      verify: log into the seeded reviewer account on web and confirm it can generate, review, and discover; credentials are current and match what's filled into both store review notes.
      depends: 9.1.1
- [ ] **9.1.5** Confirm prod **cost-guard is armed** before exposing the app: per-user daily caps, per-user rate limit, and the global daily budget kill-switch are active on prod with the active provider (Gemini at launch).
      verify: against prod, drive a user past their generate cap and confirm a friendly cap message (not an error); push synthetic global usage to the ceiling and confirm generation returns "daily limit reached" with no paid usage incurred.
      depends: Phase 3 cost guard, 9.1.1

## 9.2 — Submit & promote to the stores  ·  S

_Context: with smoke tests green, push the release-candidate builds onto the public store tracks. iOS goes into App Store review; Android promotes from internal testing to the production track._

- [ ] **9.2.1** Submit the iOS build to **App Store review**: attach the reviewer demo credentials, export-compliance answer, and privacy-nutrition responses, then submit for review.
      verify: in App Store Connect the version state is **Waiting for Review / In Review** with the demo account and review notes attached; no submission-time validation errors.
      depends: 9.1.2, 9.1.4, Phase 8 nutrition labels & age rating
- [ ] **9.2.2** Promote the Android build from internal testing to the **Play production** track (staged/phased rollout), with the Data Safety form and store listing finalized.
      verify: in Play Console the production release is **in review / rolling out** with a staged-rollout percentage set, Data Safety complete, and no policy/pre-launch-report blockers.
      depends: 9.1.3, 9.1.4, Phase 8 Data Safety form
- [ ] **9.2.3** Confirm the **OTA live-update channel points at prod** so post-launch web-layer fixes ship to installed apps without store review, while native changes stay on the store track.
      verify: push a trivial visible web-layer change through the OTA prod channel to an installed release build and confirm it appears after relaunch without a store update; native version is unchanged.
      depends: Phase 7 OTA channels

## 9.3 — Cut web over to the production domain  ·  S

_Context: point the public production domain at the Vercel prod project and the API prod domain at Cloud Run, with valid TLS, so the website launches alongside the apps._

- [ ] **9.3.1** Attach the production **web domain** to the Vercel prod project and confirm TLS + canonical redirects (www/apex, http→https).
      verify: `curl -I https://<prod-web-domain>` returns 200 with a valid certificate; the non-canonical host 301-redirects to the canonical https origin.
      depends: Phase 6 Vercel prod project
- [ ] **9.3.2** Confirm the prod web build targets the **prod API domain** (not staging) and CORS/auth redirect URIs (Supabase, Google, Apple) include the prod web origin.
      verify: load the prod web domain, complete an email + Google + Apple login, and confirm API calls hit the prod API host with no CORS or OAuth-redirect errors in the console/network panel.
      depends: 9.3.1, Phase 6 prod API deploy
- [ ] **9.3.3** Verify prod **health and readiness** endpoints are green and that the external uptime monitor is watching the prod domain.
      verify: `curl https://<prod-api-domain>/health` returns 200 and the UptimeRobot/Grafana synthetic monitor shows the prod check green at its interval (ties to Phase 5 uptime check).
      depends: Phase 5 uptime check, 9.3.2

## 9.4 — Watch, alert, and hold a rollback ready (first 48h)  ·  S

_Context: launch is not "ship and walk away." Watch dashboards/alerts for 48 hours with the rollback procedure rehearsed so a bad release can be reverted in minutes on every platform._

- [ ] **9.4.1** Confirm all **prod dashboards are live**: service health (RED), cost-guard (LLM usage vs budget), product (signups/reviews/active users), and infra all show real prod traffic.
      verify: open each Grafana dashboard against prod after the domain cut-over and confirm non-empty panels for request rate/error rate/latency, `gemini_budget_remaining`, and signups/reviews.
      depends: Phase 5 dashboards, 9.3.2
- [ ] **9.4.2** Confirm the **prod alert pipeline fires** to the real channel: error-rate, latency, budget≈exhausted, and uptime alerts are enabled on prod and route to Slack/Discord/email, with **Sentry** receiving prod errors.
      verify: deliberately trip one prod alert (e.g. force a brief 5xx or push synthetic budget to ≥80%) and confirm the message arrives in the channel; a thrown prod error appears as a Sentry issue with a `trace_id` resolving to a Grafana trace.
      depends: Phase 5 alerts & Sentry
- [ ] **9.4.3** Rehearse and document the **rollback procedure** for each surface in `docs/runbook.md`: API (Cloud Run revision revert), web (Vercel instant rollback), and mobile web-layer (OTA channel revert), each with a target time-to-revert.
      verify: perform a dry-run rollback of the Cloud Run API revision and a Vercel deployment on prod (then restore), confirming each completes and `/health` stays green; the runbook records the exact commands and rollback was timed under the stated target.
      depends: Phase 6 runbook & rollback, 9.3.2
- [ ] **9.4.4** Run the **48-hour launch watch**: monitor dashboards/alerts on a defined cadence, triage any Sentry issues, and log observations + any incidents in the runbook; close the watch with a go/stable sign-off or a rollback decision.
      verify: a dated 48h watch log exists in the runbook capturing error-rate, p95 latency, budget consumption, and signup count at each check; no unresolved P1 incident remains open at sign-off.
      depends: 9.4.1, 9.4.2, 9.4.3

---

## Phase 9 exit gate

Phase 9 is DONE only when all of these hold (these are the v1 launch success criteria):

- [ ] A new user can sign up (email/Google/Apple) on **web, iOS, and Android** and use the full Generate → Save → Review → Discover loop on their own private data — verify: the prod smoke tests in 9.1.1 (web), 9.1.2 (iOS/TestFlight), and 9.1.3 (Android/internal) all pass on real devices against prod, each with data isolation confirmed.
- [ ] Three environments exist with **auto-staging and gated prod**, and prod is live — verify: a merge to `main` deploys staging automatically while the prod web domain (9.3.1) and prod API (9.3.3) are served only via the gated promotion (Phase 6), both returning 200.
- [ ] **LLM usage cannot cause a bill** on prod — verify: 9.1.5 shows per-user caps, rate limit, and the global budget kill-switch tripping on prod with zero paid usage.
- [ ] **Traces, logs, metrics + Sentry** flow and an **uptime alert fires** to a real channel — verify: prod dashboards render live traffic (9.4.1) and a deliberately tripped prod alert reaches the channel with a Sentry issue linked to a Grafana trace (9.4.2), and the external uptime monitor watches prod `/health` (9.3.3).
- [ ] **In-app account deletion + a published privacy policy + store data-safety forms** are complete — verify: in-app deletion works for the smoke-test user, the privacy-policy URL returns 200, and both Apple privacy nutrition labels (9.2.1) and the Play Data Safety form (9.2.2) are submitted.
- [ ] **iOS passes the TestFlight path and Android passes Play internal testing**, and both are submitted/promoted to production — verify: iOS is In Review in App Store Connect (9.2.1) and Android is rolling out on the Play production track (9.2.2), each having cleared its testing track in Phase 8.
- [ ] A 48-hour launch watch closed with a stable sign-off and a rehearsed rollback ready — verify: the dated watch log and timed rollback dry-run in 9.4.3 / 9.4.4 exist in `docs/runbook.md` with no open P1.
- [ ] every task above merged via a green PR with the quality gate held (≥80% coverage, E2E).
