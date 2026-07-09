import { describe, expect, it } from 'vitest';

import {
  CURATED_LANGUAGES,
  findCurated,
  findCuratedByCode,
} from '@/lib/curated-languages';
import { directionForCode } from '@/lib/language-text';

describe('curated language table — invariants', () => {
  it('is non-empty', () => {
    expect(CURATED_LANGUAGES.length).toBeGreaterThan(0);
  });

  it('has unique, lowercase, non-blank codes', () => {
    const codes = CURATED_LANGUAGES.map((l) => l.code);
    expect(new Set(codes).size).toBe(codes.length);
    for (const code of codes) {
      expect(code).toBe(code.toLowerCase());
      expect(code.trim()).not.toBe('');
    }
  });

  it('has unique, non-blank English names', () => {
    const names = CURATED_LANGUAGES.map((l) => l.name);
    expect(new Set(names).size).toBe(names.length);
    for (const name of names) {
      expect(name.trim()).not.toBe('');
    }
  });

  it('gives every entry a non-blank endonym and a script tag', () => {
    for (const lang of CURATED_LANGUAGES) {
      expect(lang.nativeName.trim()).not.toBe('');
      expect(lang.script).toBeTruthy();
    }
  });

  it('marks exactly Arabic, Hebrew and Persian as vowelizable', () => {
    const vowelizable = CURATED_LANGUAGES.filter((l) => l.vowelizable).map(
      (l) => l.code,
    );
    expect(new Set(vowelizable)).toEqual(new Set(['ar', 'he', 'fa']));
  });

  it('keeps every Arabic/Hebrew-script entry right-to-left per directionForCode', () => {
    for (const lang of CURATED_LANGUAGES) {
      if (lang.script === 'Arabic' || lang.script === 'Hebrew') {
        expect(directionForCode(lang.code)).toBe('rtl');
      } else {
        // The two RTL scripts are the ONLY curated RTL entries — no other script is right-to-left.
        expect(directionForCode(lang.code)).toBe('ltr');
      }
    }
  });

  it('only allows vowelizable on Arabic/Hebrew-script (RTL) entries', () => {
    for (const lang of CURATED_LANGUAGES) {
      if (lang.vowelizable) {
        expect(directionForCode(lang.code)).toBe('rtl');
      }
    }
  });

  it('lists entries alphabetically by English name', () => {
    const names = CURATED_LANGUAGES.map((l) => l.name);
    const sorted = [...names].sort((a, b) => a.localeCompare(b, 'en'));
    expect(names).toEqual(sorted);
  });
});

describe('findCurated', () => {
  it('matches by exact English name', () => {
    expect(findCurated('Spanish')?.code).toBe('es');
  });

  it('is case-insensitive and trims surrounding whitespace', () => {
    expect(findCurated('  spanish  ')?.code).toBe('es');
    expect(findCurated('ARABIC')?.code).toBe('ar');
  });

  it('returns undefined for a non-curated name', () => {
    expect(findCurated('Klingon')).toBeUndefined();
  });

  it('returns undefined for a blank name', () => {
    expect(findCurated('')).toBeUndefined();
    expect(findCurated('   ')).toBeUndefined();
  });

  it('matches a multi-word curated name', () => {
    expect(findCurated('chinese (mandarin)')?.code).toBe('zh');
  });
});

describe('findCuratedByCode', () => {
  it('matches an exact primary subtag', () => {
    expect(findCuratedByCode('he')?.name).toBe('Hebrew');
  });

  it('matches a region-tagged code by its primary subtag', () => {
    expect(findCuratedByCode('pt-BR')?.name).toBe('Portuguese');
  });

  it('is case-insensitive and trims whitespace', () => {
    expect(findCuratedByCode('  AR ')?.name).toBe('Arabic');
  });

  it('returns undefined for an unknown or blank code', () => {
    expect(findCuratedByCode('xx')).toBeUndefined();
    expect(findCuratedByCode('')).toBeUndefined();
    expect(findCuratedByCode(null)).toBeUndefined();
    expect(findCuratedByCode(undefined)).toBeUndefined();
  });

  it('matches a three-letter primary subtag', () => {
    expect(findCuratedByCode('fil')?.name).toBe('Filipino (Tagalog)');
  });
});
