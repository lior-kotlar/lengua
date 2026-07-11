import { describe, expect, it } from 'vitest';

import {
  CEFR_BANDS,
  cefrBandChipClass,
  cefrBandColor,
  isCefrBand,
  nextBand,
  progressPercent,
} from '@/lib/cefr';

describe('CEFR_BANDS', () => {
  it('matches the backend band order', () => {
    expect(CEFR_BANDS).toEqual(['A1', 'A2', 'B1', 'B2', 'C1', 'C2']);
  });
});

describe('isCefrBand', () => {
  it('accepts known bands and rejects others', () => {
    expect(isCefrBand('B2')).toBe(true);
    expect(isCefrBand('A1')).toBe(true);
    expect(isCefrBand('Z9')).toBe(false);
    expect(isCefrBand('')).toBe(false);
  });
});

describe('nextBand', () => {
  it('returns the next band up', () => {
    expect(nextBand('A1')).toBe('A2');
    expect(nextBand('B1')).toBe('B2');
    expect(nextBand('C1')).toBe('C2');
  });

  it('returns null at the top band', () => {
    expect(nextBand('C2')).toBeNull();
  });

  it('returns null for an unknown band', () => {
    expect(nextBand('nope')).toBeNull();
  });
});

describe('progressPercent', () => {
  it('converts a 0..1 fraction to a rounded percentage', () => {
    expect(progressPercent(0)).toBe(0);
    expect(progressPercent(0.4)).toBe(40);
    expect(progressPercent(0.555)).toBe(56);
    expect(progressPercent(1)).toBe(100);
  });

  it('holds a below-1 fraction that rounds up to 100 at 99', () => {
    // The band only advances at the integer boundary, so a "100% to next" caption while the chip
    // still shows the current band would misread. Round-to-100 while progress < 1 is capped at 99.
    expect(progressPercent(0.995)).toBe(99); // Math.round(99.5) === 100, but progress < 1
    expect(progressPercent(0.999)).toBe(99);
    // Just below the round-up threshold already lands at 99 by ordinary rounding — no discontinuity.
    expect(progressPercent(0.994)).toBe(99);
    // Only an exact 1.0 (the absolute top, where the caption is hidden) shows 100.
    expect(progressPercent(1)).toBe(100);
  });

  it('clamps out-of-range and non-finite values', () => {
    expect(progressPercent(-0.5)).toBe(0);
    expect(progressPercent(2)).toBe(100);
    expect(progressPercent(Number.NaN)).toBe(0);
  });
});

describe('cefrBandColor', () => {
  it('maps bands to the locked red/orange/blue/green palette by tier', () => {
    expect(cefrBandColor('A1')).toBe('bg-hig-red');
    expect(cefrBandColor('A2')).toBe('bg-hig-orange');
    expect(cefrBandColor('B1')).toBe('bg-hig-blue');
    expect(cefrBandColor('B2')).toBe('bg-hig-blue');
    expect(cefrBandColor('C1')).toBe('bg-hig-green');
    expect(cefrBandColor('C2')).toBe('bg-hig-green');
  });

  it('falls back to neutral for an unknown band', () => {
    expect(cefrBandColor('??')).toBe('bg-muted-foreground');
  });
});

describe('cefrBandChipClass', () => {
  it('maps bands to tinted chips in the same hue tiers as the bar fill', () => {
    expect(cefrBandChipClass('A1')).toBe('bg-hig-red/15 text-hig-red-deep');
    expect(cefrBandChipClass('A2')).toBe(
      'bg-hig-orange/15 text-hig-orange-deep',
    );
    expect(cefrBandChipClass('B1')).toBe('bg-hig-blue/15 text-hig-blue-deep');
    expect(cefrBandChipClass('B2')).toBe('bg-hig-blue/15 text-hig-blue-deep');
    expect(cefrBandChipClass('C1')).toBe('bg-hig-green/15 text-hig-green-deep');
    expect(cefrBandChipClass('C2')).toBe('bg-hig-green/15 text-hig-green-deep');
  });

  it('falls back to a neutral chip for an unknown band', () => {
    expect(cefrBandChipClass('??')).toBe('bg-secondary text-muted-foreground');
  });
});
