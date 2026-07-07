import AxeBuilder from '@axe-core/playwright';

import { expect, test, type Page } from './fixtures';

/**
 * Accessibility sweep (axe-core) over the AUTHENTICATED surfaces — broadens the CI a11y pass beyond
 * the static `/login` page, which `.github/workflows/ci.yml`'s `a11y-perf` job already scans with
 * `@axe-core/cli`. This spec runs under the FakeLLM e2e harness the `e2e` job stands up (seeded demo
 * account + API container with `LLM_PROVIDER=fake` + the served web bundle), logs in as the demo
 * user, and runs axe on Dashboard / Generate / Review / Discover / Settings.
 *
 * GATING for `color-contrast` (WCAG 2.1 AA). After the design-token contrast pass (round-3 sweep)
 * the authenticated surfaces are clean of serious/critical `color-contrast` violations, so this spec
 * now ASSERTS zero of them across the swept screens — the a11y-advisory run in the `e2e` job dropped
 * its `|| echo` guard, so a regression fails the build. It still ATTACHES + logs the full axe report
 * per screen (all rule types, advisory) so any *other* a11y finding surfaces without gating. Gated on
 * `E2E_STACK=1` like the other authenticated flows, so it only runs against the seeded ephemeral
 * stack (never in the pure-unit `vitest` job).
 *
 * The swept sweep is light-theme (the app's `system` default resolves to light in headless CI), so
 * this asserts the light palette; the dark palette's token contrast is locked separately by the
 * fast, browserless `src/token-contrast.test.ts` unit test (both themes).
 */

const DEMO_EMAIL = 'demo@lengua.test';
const DEMO_PASSWORD = 'demo-password-123';
const STACK = process.env.E2E_STACK === '1';

/**
 * Impacts we gate on. axe reports `color-contrast` as `serious`; we also fail on `critical` for
 * good measure. (`minor`/`moderate` never apply to `color-contrast`.)
 */
const GATING_IMPACTS = new Set(['serious', 'critical']);

/**
 * Documented, intentionally-tolerated `color-contrast` residue (selector substrings). EMPTY today:
 * the light-theme authenticated surfaces are fully AA after the token pass. The iOS-brand solid
 * buttons that miss AA (white-on-systemBlue in DARK, white-on-systemRed destructive confirms) live
 * in dialogs / dark mode and never render on these light happy-path surfaces, so nothing needs
 * allowlisting here. Kept as a structured seam: add `{ screen, contains, why }` entries if an
 * unavoidable brand pair ever surfaces, and record it in the CHANGELOG.
 */
const ALLOWLIST: Array<{ screen: string; contains: string; why: string }> = [];

/** A single failing color-contrast node, flattened for a readable assertion message. */
interface ContrastFinding {
  screen: string;
  target: string;
  detail: string;
}

async function login(page: Page) {
  await page.goto('/login');
  await page.getByLabel('Email').fill(DEMO_EMAIL);
  await page.getByLabel('Password', { exact: true }).fill(DEMO_PASSWORD);
  await page.getByRole('button', { name: 'Log in' }).click();
  await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
}

/** Click a primary-nav link by its visible name and wait for the matching screen heading. */
async function navigateTo(page: Page, name: string) {
  await page
    .getByRole('navigation', { name: 'Primary' })
    .getByRole('link', { name })
    .click();
  await expect(page.getByRole('heading', { name })).toBeVisible();
}

/**
 * Run axe on the current page: ATTACH the full report (advisory, all rules) and RETURN the gating
 * `color-contrast` findings (serious/critical, minus the documented allowlist) so the caller can
 * aggregate and assert. Logs a one-line per-screen summary either way.
 */
async function auditScreen(
  page: Page,
  screen: string,
): Promise<ContrastFinding[]> {
  const { violations } = await new AxeBuilder({ page }).analyze();
  await test.info().attach(`axe-${screen}.json`, {
    body: JSON.stringify(violations, null, 2),
    contentType: 'application/json',
  });

  if (violations.length > 0) {
    const summary = violations
      .map((v) => `${v.id} (${v.impact ?? 'n/a'}) x${v.nodes.length}`)
      .join(', ');
    console.warn(
      `[a11y] ${screen}: ${violations.length} violation type(s) — ${summary}`,
    );
  } else {
    console.log(`[a11y] ${screen}: no violations`);
  }

  const findings: ContrastFinding[] = [];
  for (const v of violations) {
    if (v.id !== 'color-contrast' || !GATING_IMPACTS.has(v.impact ?? '')) {
      continue;
    }
    for (const node of v.nodes) {
      const target = node.target.join(' ');
      if (
        ALLOWLIST.some(
          (a) => a.screen === screen && target.includes(a.contains),
        )
      ) {
        continue;
      }
      // axe stashes the measured colours + ratio in the check's `data`.
      const data = node.any.find((c) => c.id === 'color-contrast')?.data as
        | { fgColor?: string; bgColor?: string; contrastRatio?: number }
        | undefined;
      const detail = data
        ? `fg=${data.fgColor} bg=${data.bgColor} ratio=${data.contrastRatio}`
        : (node.failureSummary?.replace(/\s+/g, ' ').trim() ?? '');
      findings.push({ screen, target, detail });
    }
  }
  return findings;
}

test.describe('accessibility (axe) @a11y', () => {
  test.skip(
    !STACK,
    'requires the seeded Supabase + API ephemeral stack (E2E_STACK=1)',
  );

  test('authenticated surfaces have zero serious color-contrast violations', async ({
    page,
  }) => {
    const findings: ContrastFinding[] = [];

    await login(page);
    findings.push(...(await auditScreen(page, 'dashboard')));

    for (const screen of ['Generate', 'Review', 'Discover', 'Settings']) {
      await navigateTo(page, screen);
      findings.push(...(await auditScreen(page, screen.toLowerCase())));
    }

    // The whole point of the gate: no serious/critical color-contrast anywhere on the swept surfaces.
    const message =
      findings.length === 0
        ? ''
        : `serious color-contrast violations:\n${findings
            .map((f) => `  • [${f.screen}] ${f.target} — ${f.detail}`)
            .join('\n')}`;
    expect(findings, message).toHaveLength(0);
  });
});
