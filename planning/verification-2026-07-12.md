# Post-audit verification — 2026-07-12

**What this is:** a fresh re-verification of every "done" claim after the 2026-07-11 audit's
follow-ups shipped, focused on the six post-audit merges (**#153–#158** — the audit itself covered
everything up to #149) plus docs consistency, local test suites, repo hygiene, and the live GitHub
state. Run as a multi-agent workflow (~60 agents): **Fable 5** for the deep code reviews,
adversarial refutation, and the completeness critic; **Opus 4.8** for the mechanical
doc-consistency / suite / hygiene sweeps. **Every finding below survived an adversarial refutation
pass** (an independent agent tried to disprove it against the code) and an
already-tracked-elsewhere check.

**Headline: the done-claims hold.** All #153–#155 shipped claims (A1.a–e, A2.a–d, A3) verified
in-tree; local suites green (backend 555 non-integration passed; web 804 tests, 99.7% line
coverage, lint/typecheck/prettier/build/api-types/doc-links all pass); the CI e2e gate confirmed
**non-vacuous** (all 29 specs execute — none silently skip); repo hygiene clean (no orphans, no
real TODOs, `.claude` tooling reference-intact); secondary READMEs (`apps/*`, `infra/**`,
`supabase/`, scripts) all accurate. 16 findings were confirmed — 1 defensive-code gap, 2 marginal
edge-case bugs, 1 test-guard gap, 12 doc/bookkeeping errors — **all acted on the same day** (see
§2); what still needs a human is in §1 and §4.

---

## 1. Open tasks (what's left after this sweep)

### T1 — Merge PR #159 (owner-review class) — **the only open code action**

The prompt-store render guard broadening (finding V1, below) is implemented, tested, and green,
but it edits generation-critical prompt-assembly code — the same owner-review class as #153 — so
it was **opened for review, not self-merged**.

- [ ] **T1.a** Review + merge [PR #159](https://github.com/lior-kotlar/lengua/pull/159)
      (squash), after owner (Kotlar) authorization — same protocol as #153.
- [ ] **T1.b** After the merge: flip this file's V1 status in §2 and the board line in
      [outstanding-work.md](outstanding-work.md) §1.1 from "PR open" to "merged", the same way
      #153's record was flipped.

### T2 — Optional post-v1 hardening (added to [outstanding-work.md](outstanding-work.md) §1.2 — no action for v1)

Two marginal, adversarially-confirmed edge cases on the **custom (experimental)** language path.
Both have benign failure modes (a duplicate row that resolves deterministically to the oldest, no
500) and are deliberately **not** v1 work:

- [ ] **T2.a** Unicode case-folding: `get_by_name`'s `lower()` match is not full case-folding —
      custom names differing only in non-ASCII case (Turkish `İ`, NFC-vs-NFD accents) can still
      create near-duplicate rows. Fix if ever hardened: NFC-normalize + `str.casefold()` in the
      service before compare, or a Postgres ICU collation / `citext`.
- [ ] **T2.b** Concurrent-add race: `add_language` is check-then-insert and `UNIQUE(user_id,
      name)` is case-sensitive, so two in-flight case-variant adds can both insert. Fix if ever
      hardened: functional unique index on `(user_id, lower(name))` + an `IntegrityError` →
      return-existing-row handler. **Migration-gated → owner-review per protocol.**

---

## 2. Findings → what was done (all same-day, 2026-07-12)

### Code fixes (three approved by Ben, implemented as separate PRs)

- **V1 — Prompt-store render guard incomplete** (medium, `lengua_core/prompts.py`). The #153
  guard caught only `(KeyError, IndexError, ValueError)`, but `str.format` raises
  **AttributeError** for `{language.foo}` and **TypeError** for `{language[foo]}` (reproduced
  empirically) — such an override passes read-time validation, then 500s every generation: the
  exact mass-500 mode #150(a) was built to eliminate. **Fixed in
  [PR #159](https://github.com/lior-kotlar/lengua/pull/159)** — guard broadened to
  `except Exception` (safe: `CancelledError`/`KeyboardInterrupt` derive from `BaseException`),
  two new parametrized test cases, README fail-safe claim made accurate. **Open — awaiting owner
  merge (T1).**
- **V2 — "Keep legacy Streamlit runnable" had zero automated coverage** (medium). The standing
  CLAUDE.md contract was enforced by nothing; #153 rewrote `lengua_core/prompts.py`, the legacy
  app's highest-churn dependency. **Fixed: a CI import-smoke guard** — imports the legacy support
  modules, executes the four pages' top-level imports (AST-extracted; page *bodies* are not run —
  they need a real Streamlit runtime), `compileall`s the pages, and calls the prompt builders
  under the no-store default, via `uv run --with streamlit` (streamlit stays out of the project
  deps). Proven to fail on a sabotaged symbol.
- **V3 — #158 a11y regression: label-in-name** (low, WCAG 2.5.3). #158 made the vowel-marks
  toggle's visible label language-aware but left the hardcoded `aria-label="Show vowel marks"`,
  so the accessible name stopped containing the visible label. **Fixed in
  [PR #160](https://github.com/lior-kotlar/lengua/pull/160)** — new `vowelMarksLabel()` is the
  single source of truth for both strings; label-in-name tests (nikkud + harakat) proven to fail
  on the old code. (The #158 add-form checkbox was checked: not affected — its name comes from
  the `<label>` text.)

### Doc / bookkeeping corrections (the docs-sync PR that added this file)

1. `CHANGELOG.md` #150 entry still said "awaiting owner review / paused" — #153 merged
   2026-07-11 (squash `de1ecc4`); heading + body corrected to the #80-style merged record.
2. **PR #158 was recorded nowhere** (it merged after the audit's final docs sync; no tracking
   issue; the only post-audit PR that skipped the CHANGELOG). A retroactive CHANGELOG entry was
   added; it is distinct from the still-open §1.2 "vowelized toggle on an *existing* language"
   item.
3. `provider.py` **module** docstring still claimed the LLM key is checked "once, eagerly … dies
   at startup" — contradicting the A4 fix applied to the *function* docstring (per-request
   construction; fail-fast on first LLM-dependent request). Module docstring aligned.
4. `prompt_store.py:4` still advertised "(or pin)" — the pin path was removed by #153 itself.
5. `test_prompt_store.py` module docstring still listed the deleted `resolve`/pinned-version
   tests; now describes the actual `snapshot()`/validation coverage.
6. `repositories/languages.py` docstring implied the test suite runs on SQLite ("portable across
   SQLite (tests)…") — all repo tests run on Postgres; reworded.
7. `docs/streamlit-parity.md` row 33 described the pre-#95 add form — rewritten for the
   picker-first flow; row 35 + §6 updated for #158's script-aware labels/help tip (and V3's
   accessible-name guarantee).
8. `planning/owner-deferred-tasks.md` branch-protection JSON used CI **job ids** as required-check
   contexts; GitHub matches **check names** — replaced with the six exact names from
   `infra/branch-protection.md`.
9. `.claude/agents/phase-task-runner.md` instructed `gh pr merge --merge`; the repo is
   **squash-only** — corrected.
10. `language-combobox.tsx` header comment cited the deleted `planning/language-support-design.md`
    — de-linked (spec lives in git history).
11. `planning/audit-2026-07-11.md:143` claimed an "import smoke + CI" covered the legacy app —
    none existed at audit time; corrected (and V2 now actually adds one).
12. `.gitignore` scratch pattern typo (`/next-propt.txt`) — correct spelling added alongside.

### Refuted / already tracked (recorded so the list is complete)

- *Refuted:* "progressPercent 99-cap doesn't cover out-of-contract payloads" (backend contract
  makes it unreachable); "parity §8 'Google + Apple OAuth' overstates" (the row maps built
  surfaces; enablement is documented owner-gating); "parity `scripts/…` paths are wrong" (the
  doc's established apps/api-relative convention).
- *Provenance note:* #153–#158 were all author-merged by Ben with no GitHub review object; the
  board records #153's owner authorization as out-of-band — consistent with how this project
  works, just not visible on GitHub.
- *Environment, not defects:* the full local backend pytest fails only because port 54322 hosts
  an unrelated Postgres (the integration auto-skip probe connects to it); CI runs the same tests
  green. Local e2e untestable for the same port reason — CI e2e verified green **and**
  non-vacuous instead.

---

## 3. What was re-verified as OK (coverage record)

Post-audit merge reviews: #153 A1.a–e ✓ (minus the V1 gap) · #154 A2.a–d ✓ · #155 A3 (incl.
0.994/0.995/0.999/1.0 boundary tests) ✓ · #158 code quality/tests ✓ (minus V3 + bookkeeping) ·
#156/#157 docs ✓. Planning-docs cross-consistency ✓ (after the fixes above). Runbook + phase-file
reference integrity ✓ (every cited path/section exists; `production` GitHub environment correctly
absent; branch protection correctly off). Phase-8 code-slice artifacts (#130–#133) all present ✓.
README + secondary READMEs current ✓. Suites: backend ruff/format/mypy clean, 555 non-integration
passed; web 804 tests + full gate + build ✓; api-types drift-free ✓; 179 doc links resolve ✓;
store-listing limits ✓. Hygiene: no orphans/TODOs/untracked junk; `.claude` skills + agents +
plan file intact ✓. GitHub: only #103 open; no open PRs (before this sweep's); all recent CI +
deploy-staging runs green ✓.

Areas still not deep-verified (unchanged residual risk, all low): `infra/grafana/**` dashboard
JSON semantics (owner sees them live at §G); a real Streamlit-server run of the legacy app
(the new V2 guard covers imports/symbols only, by design).

---

## 4. Manual actions — Ben / Kotlar (by software)

**This sweep found no new manual actions.** The complete, ordered owner inventory remains
[`audit-2026-07-11.md`](audit-2026-07-11.md) **§5** (36 numbered rows: do-now → prod cutover →
mobile → launch → post-launch). Next up, unchanged:

| Who | Software | Action |
|-----|----------|--------|
| Kotlar | Resend + DNS registrar | Custom SMTP + SPF/DKIM/DMARC → re-enable prod email confirmation ([#103](https://github.com/lior-kotlar/lengua/issues/103)) — the only open GitHub issue |
| Kotlar (Ben ok'd) | GitHub PR [#159](https://github.com/lior-kotlar/lengua/pull/159) | Authorize/merge the prompt-store guard PR (T1) |
| Either | Google Cloud + Supabase Auth | (Optional) Google OAuth creds + `VITE_OAUTH_PROVIDERS` |
| — | — | Everything else waits for the prod-cutover decision — [go-live-activation.md](go-live-activation.md) §F/§G |

**Issue-tracking decision (2026-07-12):** contrary to earlier recollection, **no GitHub issues
exist** for Track-2/Track-3 work or the §1.2 backlog (only #103). Ben decided the planning files
**stay** as the tracker for prod/mobile work — nothing was deleted on the issues' account.

---

## 5. File-necessity review (requested 2026-07-12)

Every file in `planning/`, `docs/`, and the repo root was reviewed for whether it is still
required. **Verdict: nothing needs deletion**; the repo is already clean (the audit deleted the
true orphans). Per file:

| File | Verdict |
|------|---------|
| `planning/outstanding-work.md`, `README.md`, `tasks/task-tracker.md` | **Required** — the live board. |
| `planning/go-live-activation.md`, `owner-deferred-tasks.md` | **Required** — owner runbooks (Track 2). |
| `planning/tasks/phase-7/8/9-*.md` | **Kept by decision** (Ben, 2026-07-12) — the Track-3 tracker. |
| `planning/audit-2026-07-11.md` | **Required** — canonical owner manual-actions inventory (§5); referenced by CLAUDE.md + planning/README. |
| `docs/privacy-policy.md`, `store-listing.md` | **Required** — compliance artifacts, CI-checked, served/derived from. |
| `docs/runbook.md` | **Required** — ops runbook; On-call/Store-release sections fill at launch. |
| `docs/streamlit-parity.md` | **Keep while the legacy app is retained** (CLAUDE.md contract); retire together with `legacy_streamlit/` + root `requirements.txt` if the legacy app is ever dropped. |
| `docs/byok-seam.md` | **Keep** — documents the live bring-your-own-key seam (3 KB). |
| Root `requirements.txt` | **Required** — the legacy Streamlit app's install pins (README §legacy); not used by the monorepo apps. |
| Root `Makefile` | **Required** — the documented `make verify` local gate. |
| Root `architecture.html` | **Optional** — 74 KB one-off PR #94 visualization, linked only from `docs/README.md`. The only genuine delete candidate in the repo; owner's call — delete any time, or keep as onboarding aid. |

---

*Method stats: 13 first-round checkers (4 Fable-5 deep reviews, 9 Opus-4.8 sweeps) → 21 raw
findings → semantic dedup (15) → per-finding 2-lens adversarial verify (refute-against-code +
already-tracked) → completeness critic → 5 follow-up checks (legacy-runnable, e2e-vacuousness,
parity row-walk, merge provenance, secondary-README sweep) with their own refutation. A session
limit killed 4 late agents; their work was recovered from the run journal and re-verified. 1
finding refuted in round 1, 2 in the recovery pass; 1 already tracked (a11y → fixed as V3
anyway).*
