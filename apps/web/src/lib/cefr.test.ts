import { describe, expect, it } from 'vitest';

import {
  CEFR_BANDS,
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

  it('clamps out-of-range and non-finite values', () => {
    expect(progressPercent(-0.5)).toBe(0);
    expect(progressPercent(2)).toBe(100);
    expect(progressPercent(Number.NaN)).toBe(0);
  });
});

describe('cefrBandColor', () => {
  it('maps bands to the locked red/orange/blue/green palette by tier', () => {
    expect(cefrBandColor('A1')).toBe('bg-red-500');
    expect(cefrBandColor('A2')).toBe('bg-orange-500');
    expect(cefrBandColor('B1')).toBe('bg-blue-500');
    expect(cefrBandColor('B2')).toBe('bg-blue-500');
    expect(cefrBandColor('C1')).toBe('bg-green-500');
    expect(cefrBandColor('C2')).toBe('bg-green-500');
  });

  it('falls back to neutral for an unknown band', () => {
    expect(cefrBandColor('??')).toBe('bg-muted-foreground');
  });
});
