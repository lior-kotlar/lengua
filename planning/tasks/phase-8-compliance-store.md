# Phase 8 — Compliance & store readiness

> **Effort:** M  ·  **Depends on:** Phase 7 complete (signed iOS + Android Capacitor builds installing and running the full loop against prod) — overlaps Phase 7  ·  **Unlocks:** Phase 9 (launch)
> **Context:** the shipped security/privacy posture (auth, RLS, account export + delete) is recorded in [`../../CHANGELOG.md`](../../CHANGELOG.md); this phase adds the compliance/store layer.
> The per-PR quality gate applies to EVERY task below: each lands via a PR that is 100% green + ≥80% coverage (backend & frontend) + Playwright E2E. A task is not done until its tests keep coverage ≥80%.

**Goal:** Every launch-blocker in the 07 store-legal checklist is satisfied — published privacy & support URLs, GDPR consent + EU residency + in-app export/delete, in-app account deletion plus an external web deletion form, Apple nutrition labels + Play Data Safety, age ratings, Apple encryption declaration, complete store listings with screenshots for web and every required device size — and a closed test build is running on TestFlight (iOS) and Play internal testing and passes internal review.

**Status legend:** [ ] todo · [~] in progress · [x] done · [!] blocked

---

## 8.1 — Privacy policy & support URLs  ·  S

_Context: both stores require a published, reachable privacy-policy URL and a support/contact URL; the policy must disclose Supabase as the data store and that user vocabulary/sentences are sent to the LLM provider (Groq in dev / Gemini in prod) — see 07 launch-blocker checklist._

- [ ] **8.1.1** Write the privacy policy from the `docs/privacy-policy.md` placeholder: disclose data stored in **Supabase (EU region)**, that submitted vocabulary/sentences are **sent to the LLM provider (Google Gemini in prod) for generation**, the categories of data collected (account email, learning content, anonymized analytics), retention, the lawful basis (GDPR), and a contact email for data requests.
      verify: `docs/privacy-policy.md` contains explicit sections for "Supabase" and "Gemini"/"LLM provider", a contact email, and the words "export" and "delete"; a markdown-lint / link-check task in CI passes with no dead links.
- [ ] **8.1.2** Publish the privacy policy at a stable public HTTPS URL (a `/privacy` route on the web app or a static page) and the support/contact info at a `/support` URL, both linked from the web app footer and the in-app Account screen.
      verify: `curl -sI https://<prod-web-host>/privacy` and `curl -sI https://<prod-web-host>/support` each return `200` with `content-type: text/html`; a Playwright test asserts the Account screen renders working links to both URLs.
- [ ] **8.1.3** Record the canonical privacy-policy URL and support URL in the store-metadata source of truth (`docs/store-listing.md`) so both App Store Connect and Play Console reference the identical published URLs.
      verify: `docs/store-listing.md` lists both URLs; a check script confirms each URL returns `200` (the same URLs that 8.1.2 publishes) — fails the launch-blocker checklist item in 07 if either is unreachable.
      depends: 8.1.2

## 8.2 — GDPR: consent, residency & in-app data rights  ·  M

_Context: EU audience, GDPR-strict (08 round 4). Analytics must be opt-in before PostHog loads, Supabase lives in an EU region, and export/delete must be reachable in-app (07 privacy section)._

- [ ] **8.2.1** Confirm the first-run **analytics consent** gate (built in Phase 4 [4.10.3] and wired to PostHog in Phase 5 [5.9.1]) meets the GDPR launch-blocker: PostHog (and any analytics) initializes **only after explicit opt-in**, the choice persists, and a "decline" path leaves analytics fully uninitialized for the whole session. Add the launch-blocker assertion; do NOT rebuild the banner.
      verify: a Playwright E2E test asserts that on first load no PostHog/analytics network request fires until "Accept" is clicked, that declining fires none across a full session, and that the stored consent survives a reload; `pnpm test` covers the consent-gate unit logic.
      depends: 4.10.3, 5.9.1
- [ ] **8.2.2** Confirm and document **EU data residency**: the Supabase project region is EU, and capture the region of any other data-touching service (Cloud Run / Vercel / PostHog) in `docs/store-listing.md` so the Data Safety / nutrition-label answers are accurate.
      verify: the Supabase project settings show an EU region (screenshot/region string recorded in `docs/runbook.md`); `docs/store-listing.md` lists the region of each data processor used in the privacy answers.
- [ ] **8.2.3** Confirm the in-app **data export** Account action (built in Phase 4 [4.8.2] against `GET /account/export` from Phase 2) satisfies the GDPR export launch-blocker, and add the launch-blocker E2E assertion; do NOT rebuild the UI.
      verify: a Playwright E2E logs in as the demo user, clicks "Export my data", and asserts a JSON file is downloaded whose contents match the `GET /account/export` response for that user.
      depends: 4.8.2
- [ ] **8.2.4** Confirm the in-app **account deletion** Account flow (built in Phase 4 [4.8.3] against `DELETE /account` from Phase 2) satisfies Apple's in-app-deletion requirement, and add the launch-blocker E2E assertion that deletion is reachable using only in-app navigation; do NOT rebuild the UI.
      verify: a Playwright E2E logs in as a throwaway user, completes the delete-account confirmation, asserts the session is cleared and re-login fails (account gone); the test reaches deletion using only in-app navigation (no external URL), satisfying Apple's in-app requirement.
      depends: 4.8.3

## 8.3 — External web account-deletion request form  ·  S

_Context: Google Play requires BOTH an in-app deletion path (8.2.4) AND an externally reachable web deletion request form usable without installing the app (07 launch-blocker checklist)._

- [ ] **8.3.1** Build a public web **account-deletion request form** at a stable URL (e.g. `/delete-account`) reachable without logging into the app, that verifies the requester's email and triggers the same hard-delete-with-cascade path (including removal of the Supabase `auth.users` record) as the in-app flow.
      verify: `curl -sI https://<prod-web-host>/delete-account` returns `200`; an E2E/integration test submits the form for a seeded throwaway account and asserts the account's domain rows AND its `auth.users` record are gone afterward (no orphans), mirroring `tests/test_account_delete.py` from Phase 2.
- [ ] **8.3.2** Document and link the deletion form: record its URL in `docs/store-listing.md` and reference it in the privacy policy and Play Console "Data deletion" field.
      verify: `docs/store-listing.md` and `docs/privacy-policy.md` both contain the `/delete-account` URL, and a link-check confirms it returns `200`.
      depends: 8.3.1

## 8.4 — Apple privacy nutrition labels & encryption declaration  ·  M

_Context: App Store Connect requires the privacy "nutrition labels" (data collected/used + linkage/tracking) and an export-compliance/encryption declaration for every build (07 launch-blocker checklist)._

- [ ] **8.4.1** Produce a **data-inventory matrix** in `docs/store-listing.md` mapping every data type the app handles (email, learning content/vocab, anonymized analytics, crash/diagnostics, identifiers) to purpose, whether it's linked to identity, and whether it's used for tracking — the single source for both the Apple labels and the Play form.
      verify: `docs/store-listing.md` contains a table covering at minimum email, user content (vocab/sentences sent to the LLM), analytics, and crash diagnostics, each with purpose + linked? + tracking? columns; a reviewer sign-off note is recorded in the PR.
- [ ] **8.4.2** Complete the **App Privacy ("nutrition labels")** questionnaire in App Store Connect from the 8.4.1 matrix (data collected, linked vs. not, used for tracking = No, third parties incl. the LLM provider).
      verify: App Store Connect shows the App Privacy section as **complete/ready for submission** (screenshot in the PR); the answers match the 8.4.1 matrix exactly (diff noted in `docs/store-listing.md`).
      depends: 8.4.1
- [ ] **8.4.3** Set the **export-compliance / encryption declaration**: declare the app uses only standard HTTPS/TLS encryption (exempt) via `ITSAppUsesNonExemptEncryption = NO` in `Info.plist` and confirm the matching answer in App Store Connect, so builds don't stall on export compliance.
      verify: `apps/web/ios/App/App/Info.plist` contains `ITSAppUsesNonExemptEncryption` set to `false`; a build uploaded to TestFlight does **not** show an "export compliance required" prompt (confirmed in App Store Connect, screenshot in the PR).

## 8.5 — Google Play Data Safety & data-deletion declaration  ·  S

_Context: Play requires the Data Safety form (mirrors Apple's labels) and a declared data-deletion mechanism pointing at both the in-app flow and the external form (07 launch-blocker checklist)._

- [ ] **8.5.1** Complete the **Play Console Data Safety** form from the 8.4.1 matrix (data collected/shared, encryption in transit = Yes, deletion available = Yes, third parties incl. the LLM provider).
      verify: Play Console shows the Data Safety section as **complete** (screenshot in the PR); answers match the 8.4.1 matrix and are cross-checked against the Apple labels for consistency (diff noted in `docs/store-listing.md`).
      depends: 8.4.1
- [ ] **8.5.2** Fill the Play Console **account/data deletion** declaration: point the "delete account" URL at the external web form (8.3.1) and confirm the in-app deletion path exists.
      verify: Play Console's data-deletion field contains the `/delete-account` URL (returns `200`) and the form notes the in-app path; recorded in `docs/store-listing.md`.
      depends: 8.3.1, 8.5.1

## 8.6 — Age ratings (both stores)  ·  S

_Context: both stores require content age-rating questionnaires before a listing can be submitted (07 launch-blocker checklist)._

- [ ] **8.6.1** Complete the **Apple age-rating** questionnaire in App Store Connect (a language-learning app with user-generated text via the LLM — answer the UGC/content questions honestly) and record the resulting rating.
      verify: App Store Connect shows an assigned age rating and the Age Rating section as complete (screenshot in the PR); the rating is recorded in `docs/store-listing.md`.
- [ ] **8.6.2** Complete the **Google Play content-rating (IARC)** questionnaire and record the assigned rating.
      verify: Play Console shows an IARC rating assigned and the Content Rating section complete (screenshot in the PR); the rating is recorded in `docs/store-listing.md` and is consistent with the Apple answer.

## 8.7 — Store listing copy & metadata  ·  S

_Context: each store needs name, subtitle/short description, full description, keywords, category, and the privacy/support URLs from 8.1 (04 store-assets section)._

- [ ] **8.7.1** Author all listing copy in `docs/store-listing.md` as the single source: app **name** ("Lengua"), subtitle/short description, full description, **keywords**, primary **category** (Education), and the privacy + support URLs — written once and reused per store.
      verify: `docs/store-listing.md` contains every field (name, subtitle, description, keywords, category, privacy URL, support URL); a lint check asserts the description is within the shorter of the two stores' character limits so the same copy fits both.
- [ ] **8.7.2** Enter the listing metadata into **App Store Connect** (name, subtitle, description, keywords, category, privacy & support URLs) for the app version.
      verify: App Store Connect's version metadata matches `docs/store-listing.md` (screenshot in the PR); the App Information section reports no missing-metadata warnings.
      depends: 8.7.1
- [ ] **8.7.3** Enter the listing metadata into **Play Console** (title, short & full description, category, contact email, privacy URL).
      verify: Play Console's Main store listing shows all required fields filled with the `docs/store-listing.md` values (screenshot in the PR) and reports the store-listing section as complete.
      depends: 8.7.1

## 8.8 — Screenshots & store graphics  ·  M

_Context: 04 requires screenshots for web preview and each required device size (iPhone, iPad if supported, Android phone/tablet) plus Play's feature graphic; all rendered from the real app (icons/splash come from Phase 7)._

- [ ] **8.8.1** Capture **iPhone** screenshots at each App-Store-required display size from the running app (key screens: Generate, Review with the Again/Hard/Good/Easy colors, Discover, Account), and store them under `docs/store-assets/ios/`.
      verify: `docs/store-assets/ios/` contains the required iPhone sizes; a small script (or `file`/`identify`) asserts each image's pixel dimensions exactly match an App Store iPhone requirement, and App Store Connect accepts the upload without a dimension error (screenshot in the PR).
- [ ] **8.8.2** Capture **iPad** screenshots at the required size **only if iPad is a declared device family** for the build (otherwise mark this task N/A with a note).
      verify: if iPad is supported, `docs/store-assets/ios/ipad/` holds correctly-dimensioned images and App Store Connect accepts them; if not supported, the PR records that the build's device family excludes iPad (so iPad screenshots aren't required).
- [ ] **8.8.3** Capture **Android phone and tablet** screenshots plus the Play **feature graphic** (1024×500) from the running app, stored under `docs/store-assets/android/`.
      verify: `docs/store-assets/android/` contains phone + tablet screenshots within Play's accepted dimension range and a 1024×500 feature graphic; Play Console accepts all graphics with no dimension warning (screenshot in the PR).
- [ ] **8.8.4** Capture **web preview images** for the web listing/landing and verify **RTL screens render correctly** (Arabic/Hebrew `dir=rtl`, diacritics) in at least one captured screenshot per store, since RTL is a core differentiator.
      verify: `docs/store-assets/web/` contains the web preview images and at least one screenshot shows an RTL language rendering correctly (visual check noted in the PR); a Playwright screenshot test of an RTL Review screen passes a baseline comparison.

## 8.9 — Closed testing tracks (TestFlight + Play internal)  ·  M

_Context: a closed test on TestFlight (iOS) and the Play internal testing track must run a real build through the same pre-launch checks (07 pre-launch security checklist), proving the signed build from Phase 7 is reviewable._

- [ ] **8.9.1** Upload the signed iOS build to **TestFlight**, complete the TestFlight test-information (incl. the **reviewer demo account** credentials), and invite at least one internal tester who installs and runs the full loop.
      verify: the build shows **"Ready to Test"** in TestFlight, an internal tester installs it and completes Generate→Review→Discover signed in as the demo account (manual confirmation recorded in the PR), and the build carries no unresolved export-compliance flag (from 8.4.3).
      depends: 8.4.3, 2.5.3 (demo account)
- [ ] **8.9.2** Upload the signed Android build (AAB) to the **Play internal testing** track, add testers, and have a tester install via the internal-testing link and run the full loop.
      verify: the Play internal-testing release is **active/live to testers**, the opt-in link installs the app, and a tester completes the full loop signed in as the demo account (manual confirmation recorded in the PR).
      depends: 2.5.3 (demo account)
- [ ] **8.9.3** Run the **pre-launch security audit on the shipped client bundle**: confirm **no secret is reachable from the built web/app bundle** (only the Supabase anon key + public URLs may be present) — audit the artifact that TestFlight/Play actually ships.
      verify: a CI/script scan (e.g. `gitleaks`/grep for service-role/JWT-secret/LLM-provider-key patterns) over the built `apps/web/dist` and the packaged native bundle finds **zero** server-only secrets; the test fails CI if any non-anon key string appears (ties to the 07 pre-launch checklist item).
- [ ] **8.9.4** Run the **deletion-cascade verification against the closed-test environment**: delete a tester account created during closed testing and confirm the delete truly cascades, including removal of the **Supabase auth user**, with no orphan rows.
      verify: `pytest tests/test_account_delete.py` passes against the test stack and a manual check confirms the closed-test tester's `auth.users` row and all domain rows are gone (recorded in the PR) — satisfying the 07 "deletion truly cascades incl. Supabase auth user" checklist item.
      depends: 8.2.4, 8.3.1

---

## Phase 8 exit gate

Phase 8 is DONE only when all of these hold:

- [ ] The published privacy-policy URL and support URL are live and disclose Supabase + the LLM provider — verify: `curl -sI` returns `200` for both URLs and `docs/privacy-policy.md` contains the required Supabase + Gemini/LLM-provider disclosures (the 07 launch-blocker items for privacy & support URLs).
- [ ] GDPR rights are in place: analytics is consent-gated, Supabase is in an EU region, and export + delete are reachable in-app — verify: the consent-gate Playwright test passes (no analytics before opt-in), the Account-screen export and delete E2E tests pass, and the EU region is recorded in `docs/runbook.md`.
- [ ] Account deletion is reachable in-app AND via an external web form, and the delete truly cascades incl. the Supabase auth user — verify: the in-app delete E2E and the `/delete-account` form both complete, and `pytest tests/test_account_delete.py` confirms zero orphan rows and the removed `auth.users` record (07 pre-launch checklist).
- [ ] Apple App Privacy labels + encryption declaration and Google Play Data Safety are complete and mutually consistent — verify: both stores show their privacy sections as complete (screenshots), answers match the 8.4.1 data-inventory matrix, and `ITSAppUsesNonExemptEncryption=false` with no export-compliance prompt.
- [ ] Age ratings are assigned in both stores — verify: App Store Connect and Play Console each show an assigned rating with the questionnaire complete (recorded in `docs/store-listing.md`).
- [ ] Both store listings are complete with copy + screenshots for web and every required device size — verify: App Store Connect and Play Console report no missing-metadata warnings, and `docs/store-assets/` holds correctly-dimensioned iPhone (+iPad if supported), Android phone/tablet, feature graphic, and web images.
- [ ] No secret is present in the shipped client bundle — verify: the secret-scan over the built web/native artifacts finds zero server-only secrets (only the Supabase anon key + public URLs), per the 07 pre-launch checklist.
- [ ] A test build passes internal review on both tracks — verify: the iOS build is "Ready to Test" on TestFlight and the Android build is live on the Play internal track, each installed and run through the full loop as the reviewer demo account.
- [ ] every task above merged via a green PR with the quality gate held (≥80% coverage, E2E)
