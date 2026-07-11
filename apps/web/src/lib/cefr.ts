/**
 * CEFR level helpers — pure, dependency-free, and unit-tested.
 *
 * The learner's proficiency in a language is a continuous score on the CEFR scale; the backend
 * (`lengua_core.proficiency`) collapses it to a band label (`A1`…`C2`) plus an intra-band
 * `progress` fraction (0..1) and exposes both through `GET /proficiency/{language_id}`. This module
 * holds the small client-side bits that derive presentation from that payload: the canonical band
 * order (kept in sync with the backend `config.CEFR_BANDS`), the next band to aim for, a clamped
 * percentage for the progress bar, and the locked band → colour mapping for the bar fill.
 */

/** Canonical CEFR bands, lowest → highest. Mirrors the backend `config.CEFR_BANDS`. */
export const CEFR_BANDS = ['A1', 'A2', 'B1', 'B2', 'C1', 'C2'] as const;

/** One of the six CEFR band labels. */
export type CefrBand = (typeof CEFR_BANDS)[number];

/** Type guard: is `value` a known CEFR band? */
export function isCefrBand(value: string): value is CefrBand {
  return (CEFR_BANDS as readonly string[]).includes(value);
}

/**
 * The band immediately above `band`, or `null` when already at the top (`C2`).
 *
 * Used to label the progress bar ("Progress to B1"). An unknown band is treated as "no next band"
 * so a malformed payload degrades to a plain bar rather than throwing.
 */
export function nextBand(band: string): CefrBand | null {
  const index = (CEFR_BANDS as readonly string[]).indexOf(band);
  if (index === -1 || index >= CEFR_BANDS.length - 1) {
    return null;
  }
  return CEFR_BANDS[index + 1];
}

/**
 * Convert a 0..1 intra-band `progress` fraction to a whole-number percentage, clamped to 0..100.
 *
 * Rounds to the nearest whole percent, with one exception: a fraction that is below 1 but rounds
 * up to 100 (≥ 0.995) is held at 99. The backend only advances the band at the integer boundary
 * (`band_progress` returns 1.0 solely at the absolute top, where the "% to next" caption is
 * hidden), so a true 100% caption while the band chip still shows the current band would misread.
 * Capping the near-top window at 99 keeps the caption honest without shifting any other percentage
 * (0.62 → 62, 0.555 → 56 are unchanged); an exact 1.0 still renders 100.
 *
 * Defensive against out-of-range/NaN inputs (a bad payload renders an empty bar, never a broken one).
 */
export function progressPercent(progress: number): number {
  if (!Number.isFinite(progress)) {
    return 0;
  }
  const clamped = Math.max(0, Math.min(1, progress));
  const rounded = Math.round(clamped * 100);
  return rounded === 100 && clamped < 1 ? 99 : rounded;
}

/**
 * Tailwind background class for the progress-bar fill, by band tier (locked palette).
 *
 * Beginner (A) is warm, intermediate (B) is blue, advanced (C) is green — using the same
 * red / orange / blue / green family as the rest of the app, over a neutral (muted) track:
 *   A1 → red, A2 → orange, B1/B2 → blue, C1/C2 → green. An unknown band → neutral.
 */
export function cefrBandColor(band: string): string {
  switch (band) {
    case 'A1':
      return 'bg-hig-red';
    case 'A2':
      return 'bg-hig-orange';
    case 'B1':
    case 'B2':
      return 'bg-hig-blue';
    case 'C1':
    case 'C2':
      return 'bg-hig-green';
    default:
      return 'bg-muted-foreground';
  }
}

/**
 * Tailwind classes for a CEFR band CHIP (tinted pill: soft fill + deep text), same band → hue
 * mapping as {@link cefrBandColor}. The `-deep` text vars re-point at the vivid hues in dark mode,
 * so one string per band is valid in both modes. Unknown bands degrade to a neutral chip.
 */
export function cefrBandChipClass(band: string): string {
  switch (band) {
    case 'A1':
      return 'bg-hig-red/15 text-hig-red-deep';
    case 'A2':
      return 'bg-hig-orange/15 text-hig-orange-deep';
    case 'B1':
    case 'B2':
      return 'bg-hig-blue/15 text-hig-blue-deep';
    case 'C1':
    case 'C2':
      return 'bg-hig-green/15 text-hig-green-deep';
    default:
      return 'bg-secondary text-muted-foreground';
  }
}
