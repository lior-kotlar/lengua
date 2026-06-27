/**
 * Sharing guard for the 429 "daily limit reached" UI (group 4.10.2).
 *
 * The cross-cutting contract requires a SINGLE reusable daily-limit panel for the quota-429 shape,
 * consumed by every LLM-bound screen (Generate + Discover today, any future one). This is the
 * "usage/grep check" half of the 4.10.2 verify: it scans the product source to prove the panel UI
 * is defined in exactly one place and that Generate + Discover both reach it through the shared
 * `LlmErrorState` → `DailyLimitPanel` path, so the 429 UI can never silently fork into a duplicate.
 *
 * (The behavioural half — "renders only for the quota-429 error shape" — lives in
 * `daily-limit-panel.test.tsx` + `llm-error-state.test.tsx`.)
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

/** The web `src/` directory (vitest runs with cwd = `apps/web`). */
const SRC_DIR = join(process.cwd(), 'src');

/** Recursively collect product source files (excludes tests, type decls). */
function sourceFiles(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      out.push(...sourceFiles(full));
      continue;
    }
    if (
      /\.tsx?$/.test(entry) &&
      !/\.(test|spec)\.tsx?$/.test(entry) &&
      !entry.endsWith('.d.ts')
    ) {
      out.push(full);
    }
  }
  return out;
}

const FILES = sourceFiles(SRC_DIR);

function read(relativePath: string): string {
  return readFileSync(join(SRC_DIR, relativePath), 'utf8');
}

/** Normalise to forward slashes so the assertions are OS-independent. */
function posix(path: string): string {
  return path.replace(/\\/g, '/');
}

const PANEL_MARKER = 'data-testid="daily-limit-panel"';

describe('shared 429 daily-limit panel (4.10.2)', () => {
  it('defines the daily-limit panel UI in exactly one place', () => {
    const owners = FILES.filter((file) =>
      readFileSync(file, 'utf8').includes(PANEL_MARKER),
    ).map(posix);

    expect(owners).toHaveLength(1);
    expect(owners[0]).toMatch(/components\/daily-limit-panel\.tsx$/);
  });

  it('routes Generate AND Discover through the single shared LlmErrorState (no duplicated 429 UI)', () => {
    for (const screen of ['pages/Generate.tsx', 'pages/Discover.tsx']) {
      const source = read(screen);
      // Both consume the shared error component…
      expect(source).toContain('LlmErrorState');
      // …and neither hand-rolls its own daily-limit panel.
      expect(source).not.toContain(PANEL_MARKER);
    }
  });

  it('renders the shared panel from the shared LlmErrorState (single quota-429 path)', () => {
    expect(read('components/llm-error-state.tsx')).toContain('DailyLimitPanel');
  });
});
