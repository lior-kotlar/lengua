import { describe, expect, it } from 'vitest';

import {
  directionForCode,
  displayText,
  hasDiacritics,
  isRtlCode,
  isVowelizableCode,
  scriptFontClass,
  stripDiacritics,
  vowelMarkTerm,
} from '@/lib/language-text';

// Built from explicit code points so the marks are unambiguous regardless of editor normalisation.
// Hebrew שָׁלוֹם (shalom, with nikkud) → bare שלום.
const HEBREW_VOWELIZED = 'שָׁלוֹם';
const HEBREW_BARE = 'שלום';
// Arabic مَرْحَبًا (marhaban, with harakat) → bare مرحبا.
const ARABIC_VOWELIZED = 'مَرْحَبًا';
const ARABIC_BARE = 'مرحبا';

describe('directionForCode', () => {
  it('is rtl for Arabic and Hebrew (and their script-mates), case/region-insensitive', () => {
    for (const code of [
      'ar',
      'he',
      'AR',
      'He',
      'ar-EG',
      'he-IL',
      'fa',
      'ur',
      'iw',
      'yi',
    ]) {
      expect(directionForCode(code)).toBe('rtl');
    }
  });

  it('is ltr for Latin-script codes and for a missing/blank code', () => {
    for (const code of ['es', 'en', 'de', 'EN-us', '', '  ', null, undefined]) {
      expect(directionForCode(code)).toBe('ltr');
    }
  });

  it('isRtlCode mirrors directionForCode', () => {
    expect(isRtlCode('ar')).toBe(true);
    expect(isRtlCode('es')).toBe(false);
    expect(isRtlCode(null)).toBe(false);
  });
});

describe('scriptFontClass', () => {
  it('maps Arabic-script codes to the Arabic font', () => {
    expect(scriptFontClass('ar')).toBe('font-arabic');
    expect(scriptFontClass('fa-IR')).toBe('font-arabic');
  });

  it('maps Hebrew-script codes to the Hebrew font', () => {
    expect(scriptFontClass('he')).toBe('font-hebrew');
    expect(scriptFontClass('yi')).toBe('font-hebrew');
  });

  it('returns no class for Latin-script / unknown / missing codes', () => {
    expect(scriptFontClass('es')).toBe('');
    expect(scriptFontClass('zxx')).toBe('');
    expect(scriptFontClass(null)).toBe('');
  });
});

describe('vowelMarkTerm', () => {
  it("is 'harakat' for Arabic-script codes (case/region-insensitive)", () => {
    for (const code of [
      'ar',
      'ar-EG',
      'AR',
      'fa',
      'fa-IR',
      'ur',
      'ckb',
      'ps',
      'sd',
      'ug',
    ]) {
      expect(vowelMarkTerm(code)).toBe('harakat');
    }
  });

  it("is 'nikkud' for Hebrew-script codes", () => {
    for (const code of ['he', 'he-IL', 'iw', 'yi', 'ji']) {
      expect(vowelMarkTerm(code)).toBe('nikkud');
    }
  });

  it('is null for other scripts and a missing/blank code', () => {
    for (const code of ['es', 'en', 'ru', 'zxx', '', '  ', null, undefined]) {
      expect(vowelMarkTerm(code)).toBeNull();
    }
  });
});

describe('isVowelizableCode', () => {
  it('is true for Arabic/Hebrew-script codes and false otherwise', () => {
    expect(isVowelizableCode('ar')).toBe(true);
    expect(isVowelizableCode('he')).toBe(true);
    expect(isVowelizableCode('fa')).toBe(true);
    expect(isVowelizableCode('ur')).toBe(true);
    expect(isVowelizableCode('es')).toBe(false);
    expect(isVowelizableCode('')).toBe(false);
    expect(isVowelizableCode(null)).toBe(false);
  });

  it('mirrors vowelMarkTerm(...) !== null', () => {
    for (const code of ['ar', 'he', 'fa', 'es', 'zxx', '', null, undefined]) {
      expect(isVowelizableCode(code)).toBe(vowelMarkTerm(code) !== null);
    }
  });
});

describe('hasDiacritics', () => {
  it('detects Hebrew nikkud and Arabic harakat', () => {
    expect(hasDiacritics(HEBREW_VOWELIZED)).toBe(true);
    expect(hasDiacritics(ARABIC_VOWELIZED)).toBe(true);
  });

  it('is false for bare consonantal text and Latin text (incl. precomposed accents)', () => {
    expect(hasDiacritics(HEBREW_BARE)).toBe(false);
    expect(hasDiacritics(ARABIC_BARE)).toBe(false);
    expect(hasDiacritics('café señor')).toBe(false);
  });
});

describe('stripDiacritics', () => {
  it('removes Hebrew nikkud, leaving the consonants', () => {
    expect(stripDiacritics(HEBREW_VOWELIZED)).toBe(HEBREW_BARE);
  });

  it('removes Arabic harakat, leaving the consonants', () => {
    expect(stripDiacritics(ARABIC_VOWELIZED)).toBe(ARABIC_BARE);
  });

  it('keeps the Arabic tatweel (a base joining character, not a vowel mark)', () => {
    expect(stripDiacritics('ـ')).toBe('ـ');
  });

  it('leaves Latin text (precomposed accents) untouched and is idempotent', () => {
    expect(stripDiacritics('résumé')).toBe('résumé');
    expect(stripDiacritics(stripDiacritics(HEBREW_VOWELIZED))).toBe(
      HEBREW_BARE,
    );
  });

  it('does not share regex state across calls (no lastIndex leak)', () => {
    // Two consecutive calls on vowel-marked text must both fully strip — a stateful global regex
    // would skip the second.
    expect(stripDiacritics(ARABIC_VOWELIZED)).toBe(ARABIC_BARE);
    expect(stripDiacritics(ARABIC_VOWELIZED)).toBe(ARABIC_BARE);
  });
});

describe('displayText', () => {
  it('returns the original text when vowels are shown', () => {
    expect(displayText(HEBREW_VOWELIZED, true)).toBe(HEBREW_VOWELIZED);
  });

  it('strips the diacritics when vowels are hidden', () => {
    expect(displayText(HEBREW_VOWELIZED, false)).toBe(HEBREW_BARE);
  });
});
