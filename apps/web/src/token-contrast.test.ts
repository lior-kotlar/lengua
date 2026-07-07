import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

import { describe, expect, it } from 'vitest';

/**
 * Design-token contrast guard (WCAG 2.1 AA) — a fast, browserless companion to the runtime axe gate
 * in `e2e/a11y.spec.ts`. The axe sweep only exercises the LIGHT theme (the app's `system` default
 * resolves to light in headless CI); this test parses the real HSL custom properties out of
 * `index.css` and re-derives the contrast of every rendered token pair in BOTH themes, so a
 * regression to the dark palette (which axe never sees) also fails CI.
 *
 * The pairs below are exactly the ones the design renders as text (rating pills, CEFR/status chips,
 * links, the daily-limit panel, secondary/muted copy). The alpha-composited tints (`bg-hig-x/15`,
 * `bg-primary/15`, `bg-hig-orange/10`) are composited over their real surface before measuring, the
 * same way a browser paints them.
 */

const AA = 4.5; // normal text
const UI_FLOOR = 3.0; // large-text / non-text UI floor — used only for the documented brand exceptions

// vitest runs with the package dir (`apps/web`) as cwd, so `src/index.css` resolves deterministically.
const css = readFileSync(resolve(process.cwd(), 'src/index.css'), 'utf8');

/** Extract `--name: H S% L%` HSL triples from a `selector { ... }` block (no nested braces inside). */
function parseTokens(
  selector: string,
): Record<string, [number, number, number]> {
  const block = new RegExp(`${selector}\\s*\\{([^}]*)\\}`).exec(css);
  if (!block) throw new Error(`could not find CSS block for ${selector}`);
  const out: Record<string, [number, number, number]> = {};
  for (const m of block[1].matchAll(/--([\w-]+):\s*([^;]+);/g)) {
    const hsl = /^(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)%\s+(\d+(?:\.\d+)?)%$/.exec(
      m[2].trim(),
    );
    if (hsl) out[m[1]] = [Number(hsl[1]), Number(hsl[2]), Number(hsl[3])];
  }
  return out;
}

const LIGHT = parseTokens(':root');
const DARK = parseTokens('\\.dark');

type Rgb = [number, number, number];

function hslToRgb([h, s, l]: [number, number, number]): Rgb {
  s /= 100;
  l /= 100;
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const hp = h / 60;
  const x = c * (1 - Math.abs((hp % 2) - 1));
  let r = 0;
  let g = 0;
  let b = 0;
  if (hp < 1) [r, g, b] = [c, x, 0];
  else if (hp < 2) [r, g, b] = [x, c, 0];
  else if (hp < 3) [r, g, b] = [0, c, x];
  else if (hp < 4) [r, g, b] = [0, x, c];
  else if (hp < 5) [r, g, b] = [x, 0, c];
  else [r, g, b] = [c, 0, x];
  const m = l - c / 2;
  return [(r + m) * 255, (g + m) * 255, (b + m) * 255];
}

function luminance([r, g, b]: Rgb): number {
  const lin = (v: number) => {
    v /= 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

/** Source-over composite of `fg` at `alpha` over opaque `bg`. */
function over(fg: Rgb, alpha: number, bg: Rgb): Rgb {
  return [
    fg[0] * alpha + bg[0] * (1 - alpha),
    fg[1] * alpha + bg[1] * (1 - alpha),
    fg[2] * alpha + bg[2] * (1 - alpha),
  ];
}

function contrast(fg: Rgb, bg: Rgb): number {
  const l1 = luminance(fg);
  const l2 = luminance(bg);
  return (Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05);
}

/**
 * Contrast of `fgToken` (optionally at `fgAlpha`) over a stack of `[token, alpha]` layers painted
 * bottom→top (first entry is the opaque base surface).
 */
function ratio(
  tokens: Record<string, [number, number, number]>,
  fgToken: string,
  bgStack: Array<[string, number]>,
  fgAlpha = 1,
): number {
  let bg = hslToRgb(tokens[bgStack[0][0]]);
  for (const [tok, a] of bgStack.slice(1))
    bg = over(hslToRgb(tokens[tok]), a, bg);
  let fg = hslToRgb(tokens[fgToken]);
  if (fgAlpha < 1) fg = over(fg, fgAlpha, bg);
  return contrast(fg, bg);
}

/** The rendered text pairs that MUST clear AA, per theme. `[label, fgToken, bgStack]`. */
function mustPass(
  t: Record<string, [number, number, number]>,
): Array<[string, number]> {
  const pairs: Array<[string, number]> = [];
  const add = (label: string, r: number) => pairs.push([label, r]);

  // Rating pills + CEFR/status chips: text-hig-X-deep on bg-hig-X/15 over card AND background.
  for (const hue of ['red', 'orange', 'blue', 'green']) {
    for (const surf of ['card', 'background']) {
      add(
        `${hue}-deep on ${hue}/15 over ${surf}`,
        ratio(t, `hig-${hue}-deep`, [
          [surf, 1],
          [`hig-${hue}`, 0.15],
        ]),
      );
    }
    // Deep hue as solid text (Generate saved note, danger-zone label, error/empty states).
    add(`${hue}-deep on card`, ratio(t, `hig-${hue}-deep`, [['card', 1]]));
    add(
      `${hue}-deep on background`,
      ratio(t, `hig-${hue}-deep`, [['background', 1]]),
    );
  }

  // Blue chips (Languages / user-menu / dashboard / tinted button) use bg-hig-blue/15 after the
  // round-3 migration off bg-primary/15 (which darkened with the AA-tuned --primary).
  for (const surf of ['card', 'background']) {
    add(
      `blue chip on hig-blue/15 over ${surf}`,
      ratio(t, 'hig-blue-deep', [
        [surf, 1],
        ['hig-blue', 0.15],
      ]),
    );
  }

  // Daily-limit panel: hig-orange-deep body copy (full opacity) on bg-hig-orange/10.
  for (const surf of ['card', 'background']) {
    add(
      `daily-panel orange-deep on orange/10 over ${surf}`,
      ratio(t, 'hig-orange-deep', [
        [surf, 1],
        ['hig-orange', 0.1],
      ]),
    );
  }

  // Secondary / muted copy on its real surfaces.
  add('muted-fg on card', ratio(t, 'muted-foreground', [['card', 1]]));
  add(
    'muted-fg on background',
    ratio(t, 'muted-foreground', [['background', 1]]),
  );
  add(
    'muted-fg on secondary',
    ratio(t, 'muted-foreground', [['secondary', 1]]),
  );

  return pairs;
}

describe('design-token contrast (WCAG 2.1 AA)', () => {
  describe('light theme', () => {
    // Light is the axe-swept theme; the primary button + link text must also clear AA here.
    it.each([
      [
        'white on primary (button)',
        ratio(LIGHT, 'primary-foreground', [['primary', 1]]),
      ],
      ['primary link on card', ratio(LIGHT, 'primary', [['card', 1]])],
      [
        'primary link on background',
        ratio(LIGHT, 'primary', [['background', 1]]),
      ],
      ...mustPass(LIGHT),
    ])('%s ≥ 4.5:1', (_label, r) => {
      expect(r).toBeGreaterThanOrEqual(AA);
    });
  });

  describe('dark theme', () => {
    // In dark, the blue LINK text keeps using --primary (which stays the vivid systemBlue so links
    // clear AA on the dark canvas); the solid primary BUTTON (white-on-systemBlue) is the documented
    // iOS-brand exception below.
    it.each([
      ['primary link on card', ratio(DARK, 'primary', [['card', 1]])],
      [
        'primary link on background',
        ratio(DARK, 'primary', [['background', 1]]),
      ],
      ...mustPass(DARK),
    ])('%s ≥ 4.5:1', (_label, r) => {
      expect(r).toBeGreaterThanOrEqual(AA);
    });
  });

  // Documented iOS-brand solid-fill exceptions (white on systemBlue / systemRed). They render only
  // in dialogs (destructive confirm) and dark mode, never on the light happy-path surfaces the axe
  // gate sweeps, so they are tracked in the CHANGELOG rather than fixed. We still floor them at the
  // large-text / UI 3:1 minimum so they can't silently degrade further.
  it('brand solid-fill exceptions stay above the 3:1 UI floor', () => {
    expect(
      ratio(DARK, 'primary-foreground', [['primary', 1]]),
    ).toBeGreaterThanOrEqual(UI_FLOOR);
    expect(
      ratio(LIGHT, 'destructive-foreground', [['destructive', 1]]),
    ).toBeGreaterThanOrEqual(UI_FLOOR);
    expect(
      ratio(DARK, 'destructive-foreground', [['destructive', 1]]),
    ).toBeGreaterThanOrEqual(UI_FLOOR);
  });
});
