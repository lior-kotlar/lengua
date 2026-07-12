# Outstanding work — what's left

**What this is:** the single live list of everything in Lengua that is **not complete**, organized
into three tracks by *who can act on it and when*. Whenever something incomplete is noticed (in any
session), append it to the matching track with *where* + *status*.

Everything **done** — phases 0–6, milestones M1–M3, the M4 staging leg, the 22 resolved
live-staging findings, the three doable-now hardening sweeps, and the Phase-8 compliance code
slice — is recorded in [`../CHANGELOG.md`](../CHANGELOG.md). Validated 2026-07-08 against the code
(every "done" claim re-verified in-tree before this reorganization), re-audited 2026-07-11
([audit-2026-07-11.md](audit-2026-07-11.md)), and re-verified post-follow-ups 2026-07-12
([verification-2026-07-12.md](verification-2026-07-12.md)).

**How to run a work item:** `/next-task` (one Track-1 item per run — see
[`../.claude/skills/next-task/SKILL.md`](../.claude/skills/next-task/SKILL.md)) or `/run-phase N`
(a whole phase). Both spawn `phase-task-runner` agents (Opus / max) that implement → verify →
PR → self-merge or pause; the orchestrating session stays light.

| Track | What | Who / when |
| --- | --- | --- |
| **[1 — Code, doable now](#track-1--code-work-doable-now)** | buildable + CI-verifiable; no owner creds, no prod, no mobile | any Claude Code session, now |
| **[2 — Owner-gated](#track-2--owner-gated)** | needs live consoles / creds / DNS / paid accounts | Kotlar (or Ben once creds exist) |
| **[3 — Deferred by decision](#track-3--deferred-by-decision-mobile--store--launch)** | mobile → store → launch — deliberately later, after the Track-2 prod cutover | later, in order |

Plus [tech debt / watch items](#tech-debt--watch-items) at the bottom.

---

## Track 1 — Code work, doable now

*Scope guardrails: do NOT touch mobile/Capacitor, prod, secrets, migrations, or store consoles.
Everything here lands trunk-based, one PR per item, proven by the per-PR CI gate (≥80% coverage
held, legacy Streamlit kept runnable).*

### 1.1 Open code items

_No open code items._ **§1.1 is empty again** — the last item, V1 below, merged 2026-07-12.

- ~~**V1 = [PR #159](https://github.com/lior-kotlar/lengua/pull/159) — prompt-store render-guard
  broadening (#153 follow-up)**~~ — **shipped 2026-07-12** (squash `647e84d`). The #153 guard
  caught only `(KeyError, IndexError, ValueError)`, but `str.format` raises AttributeError for
  `{language.foo}` and TypeError for `{language[foo]}`, so such a DB override still 500'd every
  generation; the guard is now `except Exception` (+2 mutation-proven tests, README made
  accurate). Opened for owner review (generation-critical class, like #153), then **merged on the
  owner's (Ben's) authorization after a unanimous three-lens delegated review** (correctness ·
  test-mutation · docs/protocol; see [verification-2026-07-12.md](verification-2026-07-12.md)).

The 2026-07-11 completion-audit follow-ups (issues
[#150](https://github.com/lior-kotlar/lengua/issues/150),
[#151](https://github.com/lior-kotlar/lengua/issues/151),
[#152](https://github.com/lior-kotlar/lengua/issues/152)) all **shipped 2026-07-11**, the
audit's A4 wording corrections landed 2026-07-12, and the 2026-07-12 verification's other two
code fixes shipped the same day (shipped-record below):

- ~~**A1 = #150 — Prompt-store hardening (#80 follow-ups)**~~ — **shipped 2026-07-11** (PR #153,
  squash `de1ecc4`, green CI). It was opened as an owner-review PR (it edits generation-critical
  prompt-assembly code, same reason #80 was owner-gated), then **merged after the owner explicitly
  authorized it**. (a) each DB-overridden fragment render is wrapped in a try/except that logs
  loudly and falls back to `CODE_DEFAULTS` for that fragment — a malformed override no longer 500s
  every generation; (b) read-time validation drops unknown keys (vs `PROMPT_KEYS`) and empty-string
  overrides so they can't silently blank a fragment; (c) an integration test boots `create_app`
  with a non-empty store and asserts a real HTTP generation's assembled system instruction carries
  the DB override; (d) each prompt build captures the whole active snapshot **once** (new
  `snapshot()` hook + `MappingProxyType`), so a concurrent `warm()` can't tear a build across two
  versions; (e) the caller-less version-pinning path (`resolve(version>0)` /
  `read_pinned_prompt_from_db`) was **trimmed** (lower-risk than wiring a new request-param/flag
  with no product owner) and the docs corrected — rollback still works via `is_active`. **(f)** (a
  DB `CHECK`/key-enum constraint — migration-gated) is intentionally **left for the owner** per
  protocol; A1.b covers the same failure at read time.
- ~~**A2 = #151 — Language-picker follow-ups (#95)**~~ — **shipped 2026-07-11** (frontend + a small
  server fix; self-merged, green CI). (a) fixed **server-side**: `LanguagesRepository.get_by_name`
  now matches on `lower(name)` (portable across SQLite/Postgres), so the idempotent-add dedupe *and*
  the rename-conflict guard both treat "French"/"french" as one language — no case-variant duplicate
  rows; (b) the add-form's "Change" / "Back to list" affordances are disabled while the add is in
  flight, so a slow-network user can't navigate away and get clobbered by the success reset; (c) a
  new e2e drives the curated pick→submit→remove flow (`languages.spec.ts`), the feature's primary
  path (every prior e2e drove only the custom fallback); (d) the analytics `curated` flag now
  threads the **real submit path** from the form (a `curated` field on `AddLanguageInput`) instead
  of a name-table lookup — a custom add of a curated-named language reads as custom, as the event's
  docstring promises.
- ~~**A3 = #152 — Home-tile percent edge (#146)**~~ — **shipped 2026-07-11** (frontend display-only;
  self-merged, green CI). `progressPercent` (`apps/web/src/lib/cefr.ts`) now caps a below-1 fraction
  that rounds up to 100 (≥ 0.995) at **99**, so the "% to next" caption can no longer read "100% to B2"
  while the band chip still shows B1 — the band only advances at the integer boundary. Chosen cap-at-99
  over a plain floor to leave every other percent unchanged (0.62 → 62, 0.555 → 56; an exact 1.0 still
  reads 100). Added the ≥0.995 boundary tests. **§1.1 now has no open code items.**

- ~~**V3 — vowel-marks toggle label-in-name (a11y, #158 regression)**~~ — **shipped 2026-07-12**
  (PR #160, frontend-only, self-merged on green CI). #158's language-aware visible label had left a
  hardcoded `aria-label` behind, breaking WCAG 2.5.3; a new shared `vowelMarksLabel()` now drives
  both strings so they can't diverge.
- ~~**V2 — CI guard for "keep legacy Streamlit runnable"**~~ — **shipped 2026-07-12** (PR #161,
  squash `3aa2109`, self-merged on green CI). The standing CLAUDE.md contract had zero automated
  coverage; `apps/api/scripts/legacy_smoke.py` (run in the CI lint job via `uv run --with
  streamlit` — streamlit stays out of the project deps) now imports the legacy modules, executes
  the pages' AST-extracted top-level imports, byte-compiles the pages, and exercises the prompt
  builders. Proven to fail on a sabotaged symbol; ~zero added CI wall-clock.

(#158 — language-aware vowel-marks option (harakat/nikkud + help tip) — shipped 2026-07-11 as a
direct feature PR with no tracking issue; recorded retroactively in [`../CHANGELOG.md`](../CHANGELOG.md)
by the 2026-07-12 verification. Distinct from the §1.2 "vowelized toggle on an *existing*
language" item, which remains open.)

(#146 — Home language cards: explicit "% to next level" + per-tile due/new breakdown —
frontend-only gap-closing on the Dashboard tiles (the progress footnote now reads `62% to B2`
via `progressPercent`, and the due badge reads `{due} due · {fresh} new` via `DueTotals`); shipped
2026-07-10 (PR #148); see [`../CHANGELOG.md`](../CHANGELOG.md).)

(#95 — curated language picker + custom/experimental fallback (Option B) — implemented per the
`language-support-design.md` spec (retired post-ship; git history retains it); shipped 2026-07-09;
see [`../CHANGELOG.md`](../CHANGELOG.md).)

(#80 — DB-backed versioned prompts — shipped in PR #143, owner-reviewed and merged 2026-07-09; see
[`../CHANGELOG.md`](../CHANGELOG.md).)

### 1.2 Post-v1 backlog (deliberately post-launch — pull forward only if wanted)

Not launch-blocking; the plan schedules these after v1. Each is pure code and could be pulled into
Track 1 by choice: **accessibility remainder** (screen-reader labels,
font scaling — colour contrast is already WCAG 2.1 AA and CI-gated, #135); server push
notifications (FCM/APNs; v1 uses on-device local reminders); TTS audio (on-device first); streaks /
gamification; import/export & shared decks (beyond Anki import); UI internationalization (the
app's own UI is English-only); spaced-repetition insights (progress charts, review forecast);
admin / support tooling (support views, abuse review, manual budget override); UI-wire the
`vowelized` toggle on an *existing* language (backend already supports it via
`PATCH /languages/{id}`; today the flag is set only at add time — see `docs/streamlit-parity.md` §1).

(**Offline review + sync** was removed from this backlog by owner decision 2026-07-12 — deemed not
necessary.)

Added by the [2026-07-12 verification](verification-2026-07-12.md) (both marginal, custom-path
only, benign failure modes — see its §1 T2): **Unicode case-folding** for custom language-name
dedupe (NFC + `casefold()` or ICU/citext; `lower()` misses Turkish `İ`, NFC-vs-NFD); **functional
unique index** on `(user_id, lower(name))` + `IntegrityError` → return-existing handler to close
the concurrent case-variant add race (**migration-gated → owner review**).

---

## Track 2 — Owner-gated

Needs live accounts, consoles, DNS, or the deployed prod service. Step-by-step runbook:
[`go-live-activation.md`](go-live-activation.md).

- **(A) M4 prod cutover** — [`go-live-activation.md`](go-live-activation.md) §F. Apply the prod DB
  schema incl. migration `0006` (⚠ first swap `SUPABASE_PROD_DATABASE_URL` to the IPv4 **session
  pooler**, port 5432 — the direct IPv6 host fails on GitHub runners); prod Supabase Auth + API
  CORS = exact prod origins; create the GitHub **`production` environment + required reviewer**,
  then promote the exact staging-validated **image digest** (no rebuild); deploy web prod; run the
  rollback drill (≥2 revisions retained). Also at cutover: swap the `privacy@lengua.app` +
  `https://lengua.app` placeholders (privacy policy, `/support`, `/delete-account`,
  `docs/store-listing.md`) to the monitored inbox + real prod domain.
- **(B) Phase-5 live observability** — [`go-live-activation.md`](go-live-activation.md) §G. Traces
  in Tempo + per-route p95 in Mimir; logs in Loki + Tempo→Loki jump; RED / cost-guard / product /
  infra dashboards non-empty; Sentry issues ↔ trace; Grafana + Sentry alert rules firing to a real
  channel; external uptime monitor; PostHog funnel / D1–D7 retention / feature usage. All as-code
  committed (`infra/grafana/**`, `infra/uptime/**`, exporters + alert rules); needs live
  Grafana/Sentry/PostHog/uptime creds against the deployed service. **Do alongside it** (deferred
  observability follow-ups): export the browser client span to Tempo; unify web-Sentry ↔ Tempo by
  `trace_id`; add the `proficiency_cefr_band` metric with the live CEFR panel to judge it against
  (skipped in round 3 as untestable without the panel); confirm the exact `http_server_duration*`
  metric name in Grafana.
- **(F) Owner setup residuals** — details in [`owner-deferred-tasks.md`](owner-deferred-tasks.md):
  Resend custom SMTP + SPF/DKIM/DMARC on a verified domain → **re-enable prod email confirmation**
  ([issue #103](https://github.com/lior-kotlar/lengua/issues/103); the interim staging
  `mailer_autoconfirm=true` must NOT ship to prod); Google + Apple OAuth creds +
  `VITE_OAUTH_PROVIDERS` per env; branch protection (0.6.3) + Dependabot (0.6.4) at launch (⚠ turning
  branch protection on ends the autonomous self-merge flow); gate prod `/docs` `/redoc`
  `/openapi.json` (S20); move Cloud Run to a dedicated runtime SA with
  `secretmanager.secretAccessor` only (6.1.6); Vercel→Cloudflare host migration
  ([`go-live-activation.md`](go-live-activation.md) §H — **plan only**, do not execute).
- **Phase-6 live remainder** (folds into (A)): live rollback drill (`6.8.2`
  `infra/deploy/rollback.sh` once), RLS pytest against the staging DB (`6.2.4`), confirm idempotent
  seed (`6.2.5`), live secret-rotation (`6.4.4`), backup/restore drill (`6.8.4`).

---

## Track 3 — Deferred by decision (mobile → store → launch)

Deliberately postponed (owner call, 2026-07): do these after the prod cutover, in order.

- **(C) Phase 7 — mobile** ([`tasks/phase-7-mobile.md`](tasks/phase-7-mobile.md), ☐ not started).
  Paid store accounts (Apple $99/yr — start early; Google Play $25), Capacitor native projects +
  plugins, OAuth-in-webview, OTA channel, on-device full-loop validation.
- **(D) Phase 8 — store consoles** ([`tasks/phase-8-compliance-store.md`](tasks/phase-8-compliance-store.md)).
  The **buildable/CI-verifiable code slice is DONE** (#130–#133 — privacy policy + docs CI, public
  deletion path + `/privacy` `/support` `/delete-account`, launch-blocker E2E, store-listing +
  data-inventory + residency). Remaining tasks are **owner-blocked on the paid store accounts + the
  deployed prod app**: Apple App Privacy labels (8.4.2) + encryption declaration (8.4.3), Play Data
  Safety (8.5.x), age ratings (8.6), console listing entry (8.7.2/8.7.3), device screenshots (8.8),
  TestFlight/Play closed tests (8.9) — each derives from `docs/store-listing.md`.
- **(E) Phase 9 — launch** ([`tasks/phase-9-launch.md`](tasks/phase-9-launch.md), ☐ not started).
  Cross-platform prod smoke, store submit → promote, custom-domain cutover, 48h watch; finalize the
  runbook On-call + Store-release sections.

---

## Tech debt / watch items

Small, non-blocking items in shipped code — close when the relevant area is next worked:

- **Prod DB is Supabase-only by construction.** The API assumes the `authenticated` role per request
  (RLS), so the runtime `DATABASE_URL` **must** be a Supabase-provisioned Postgres (has the
  `authenticated` role + `auth.uid()`); a bare Alembic-only Postgres 500s on the role switch. Also
  asyncpg's prepared-statement cache breaks against the Supabase **transaction** pooler (6543) —
  use the **session** pooler (5432) or `statement_cache_size=0`. Confirm prod `DATABASE_URL` before
  the cutover (folds into Track 2 (A)).
- **Process-local state → shared store when scaling past one Cloud Run instance:** the product
  metrics (`active_users`/`signups_total`), the rate limiter (incl. its `max_keys` bound), and the
  discover cache are all per-process. One shared-store move covers all three.
- **Coverage carve-outs.** `lengua_core/models.py`, `app/settings.py`, the whole
  `legacy_streamlit/`, and the web `src/main.tsx` + `src/components/ui/**` presentational
  primitives are excluded from the 80% gate; ~20 backend modules are `@pytest.mark.integration`
  (auto-skip offline), so the 80% gate is only truly enforced in CI with Postgres up. A local no-DB
  run auto-relaxes `--cov-fail-under` to 0 with a loud banner (`tests/conftest.py`).
- **Base-image digest pin needs periodic refresh** (`apps/api/Dockerfile`) — last refreshed
  2026-07-07 → `sha256:423ed6ab…` (#136); the tag drifts, so re-check periodically (or via
  Dependabot once enabled).
- **Doc finalization at launch:** the runbook **On-call** + **Store-release** sections are filled in
  at launch (Phase 9).
- **Stale code-comment doc citation (migration only).** The applied migration
  `migrations/versions/20260630_0006_*.py` still cites the deleted `staging-validation.md`;
  migrations are off-limits even for comments, so it lingers by design.
- **OTel logs deprecation:** revisit the `opentelemetry.sdk._logs.LoggingHandler` deprecation when
  the OTel logs signal stabilizes.
- **`_client_ip` trusts the leftmost `X-Forwarded-For` hop** (`apps/api/app/routers/account_deletion.py`)
  — client-supplied on some proxy topologies, so the per-IP deletion throttle (#137) is best-effort
  (the docstring already says so). Surfaced (and deemed non-blocking: the #141 `max_keys` bound
  doesn't depend on it) by the #141 adversarial review. Evidence conflicts on whether Cloud Run's
  frontend normalizes XFF — confirm the deployed topology's behavior at the prod cutover and, if the
  leftmost hop is spoofable there, switch to the rightmost-trusted hop.
- **Watch:** confirm Supabase free-tier idle-pausing / project limits at prod setup.
