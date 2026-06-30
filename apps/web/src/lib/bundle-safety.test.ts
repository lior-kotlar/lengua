/**
 * Web-bundle secret-leak audit — source half (task 6.3.4).
 *
 * Vite statically inlines only `VITE_`-prefixed env vars into the bundle, so the SOURCE is the
 * place a secret leaks toward the browser. This test scans the non-test, non-types web source
 * (the code that actually compiles into `dist/`) and asserts:
 *
 *   1. it never references a server-only secret env name (service-role key, Groq/Gemini key,
 *      Supabase JWT secret, DATABASE_URL) — not even a `VITE_`-prefixed variant of one;
 *   2. every `VITE_*` token it references is on the small client-safe allow-list; and
 *   3. it never reads any of those server-only secrets off `import.meta.env` specifically.
 *
 * The complementary check over the actually-built `dist/` is the CI `build` job's
 * "Audit web bundle for leaked secrets" grep step (vitest can run before any build, so the source
 * scan here is the unit-test half the verify asks for).
 */
import { readFileSync, readdirSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

/**
 * The COMPLETE client-safe `VITE_*` surface that may appear in the bundle. Every one is a public
 * value (backend URL, Supabase project URL + anon key, public Sentry DSN + environment tag +
 * trace-sample rate, public PostHog key, OAuth-provider toggle, dev-only debug flag) — never a
 * server secret.
 */
const CLIENT_SAFE_ENV = [
  'VITE_API_BASE_URL',
  'VITE_SUPABASE_URL',
  'VITE_SUPABASE_ANON_KEY',
  'VITE_SENTRY_DSN_WEB',
  'VITE_SENTRY_ENVIRONMENT',
  'VITE_SENTRY_TRACES_SAMPLE_RATE',
  'VITE_POSTHOG_KEY',
  'VITE_OAUTH_PROVIDERS',
  'VITE_ENABLE_DEBUG_TOOLS',
] as const;

/**
 * Server-only secret markers that must NEVER appear in web source. Tracked as substrings so a
 * `VITE_`-prefixed variant (e.g. `VITE_GROQ_API_KEY`) is caught too — Vite WOULD inline that.
 */
const FORBIDDEN_SECRET_SUBSTRINGS = [
  'SERVICE_ROLE',
  'JWT_SECRET',
  'GROQ',
  'GEMINI',
  'DATABASE_URL',
];

/** `.../apps/web/src` — vitest runs from the `apps/web` project root (its cwd). */
const SRC_DIR = path.resolve(process.cwd(), 'src');

/** Recursively collect the source files that compile into the bundle (no tests, no `.d.ts`). */
function collectSourceFiles(dir: string): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      files.push(...collectSourceFiles(full));
    } else if (
      /\.(ts|tsx)$/.test(entry.name) &&
      !/\.(test|spec)\.(ts|tsx)$/.test(entry.name) &&
      !entry.name.endsWith('.d.ts')
    ) {
      files.push(full);
    }
  }
  return files;
}

const SOURCES = collectSourceFiles(SRC_DIR).map((file) => ({
  file: path.relative(SRC_DIR, file),
  text: readFileSync(file, 'utf8'),
}));

/** Every `VITE_*` token referenced anywhere in source, tagged with its file. */
function viteTokens(): { file: string; token: string }[] {
  const found: { file: string; token: string }[] = [];
  for (const { file, text } of SOURCES) {
    for (const match of text.matchAll(/\bVITE_[A-Za-z0-9_]+/g)) {
      found.push({ file, token: match[0] });
    }
  }
  return found;
}

/** True if `text` reads an env key whose name embeds `secret` off `import.meta.env`. */
function readsForbiddenEnv(text: string, secret: string): boolean {
  // import.meta.env.<…secret…>  OR  import.meta.env['<…secret…>'] (prefix like VITE_ allowed).
  const re = new RegExp(
    String.raw`import\.meta\.env\s*[.[]\s*['"]?[A-Za-z0-9_$]*` +
      secret +
      String.raw`[A-Za-z0-9_$]*`,
  );
  return re.test(text);
}

describe('web bundle secret-leak audit (6.3.4)', () => {
  it('has source files to audit', () => {
    expect(SOURCES.length).toBeGreaterThan(0);
  });

  it('never references a server-only secret env name', () => {
    const hits: string[] = [];
    for (const { file, text } of SOURCES) {
      for (const secret of FORBIDDEN_SECRET_SUBSTRINGS) {
        if (text.includes(secret)) hits.push(`${file} → ${secret}`);
      }
    }
    expect(hits).toEqual([]);
  });

  it('only references client-safe VITE_* env names', () => {
    const safe = new Set<string>(CLIENT_SAFE_ENV);
    const offenders = viteTokens().filter(({ token }) => !safe.has(token));
    expect(offenders).toEqual([]);
  });

  it('never reads a server-only secret off import.meta.env', () => {
    const hits: string[] = [];
    for (const { file, text } of SOURCES) {
      for (const secret of FORBIDDEN_SECRET_SUBSTRINGS) {
        if (readsForbiddenEnv(text, secret))
          hits.push(`${file} → import.meta.env…${secret}`);
      }
    }
    expect(hits).toEqual([]);
  });

  it('locks the exact client-safe surface (tripwire on edits)', () => {
    expect([...CLIENT_SAFE_ENV].sort()).toEqual(
      [
        'VITE_API_BASE_URL',
        'VITE_ENABLE_DEBUG_TOOLS',
        'VITE_OAUTH_PROVIDERS',
        'VITE_POSTHOG_KEY',
        'VITE_SENTRY_DSN_WEB',
        'VITE_SENTRY_ENVIRONMENT',
        'VITE_SENTRY_TRACES_SAMPLE_RATE',
        'VITE_SUPABASE_ANON_KEY',
        'VITE_SUPABASE_URL',
      ].sort(),
    );
  });
});
