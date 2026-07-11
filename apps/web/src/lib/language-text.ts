/**
 * Language-text helpers (group 4.9) — the pure functions behind right-to-left direction,
 * diacritic-correct fonts, and the vowel-marks (harakat / nikkud) toggle.
 *
 * These have no React/DOM dependency so they are trivially unit-testable and reused by every place
 * that renders target-language text (the Generate / Review / Discover screens, `LanguageText`, and
 * the tap-a-word `TappableSentence`).
 *
 * Locked decision (4.4): text direction is DERIVED from the language code — there is no manual
 * "direction" field. Arabic / Hebrew (and the other common RTL scripts) render right-to-left;
 * everything else is left-to-right.
 */

/** Text direction for a language's content region. */
export type Direction = 'ltr' | 'rtl';

/**
 * Primary language subtags that are written right-to-left (Arabic + Hebrew scripts).
 *
 * Matched against the FIRST subtag of the language code (`ar-EG` → `ar`), case-insensitively. The
 * task only requires Arabic (`ar`) and Hebrew (`he`); the rest are the other languages that use the
 * same two scripts (Persian, Urdu, Pashto, Sindhi, Uyghur for Arabic; `iw` is the legacy Hebrew
 * code, Yiddish + Judeo-* use the Hebrew script), so they get correct shaping for free.
 */
const RTL_SUBTAGS = new Set([
  'ar', // Arabic
  'arc', // Aramaic
  'ckb', // Central Kurdish (Sorani)
  'dv', // Divehi / Maldivian (Thaana)
  'fa', // Persian / Farsi
  'he', // Hebrew
  'iw', // Hebrew (legacy code)
  'ji', // Yiddish (legacy code)
  'ps', // Pashto
  'sd', // Sindhi
  'ug', // Uyghur
  'ur', // Urdu
  'yi', // Yiddish
]);

/** Primary subtags written in the Arabic script (→ an Arabic-shaping, harakat-correct font). */
const ARABIC_SCRIPT_SUBTAGS = new Set([
  'ar',
  'ckb',
  'fa',
  'ps',
  'sd',
  'ug',
  'ur',
]);

/** Primary subtags written in the Hebrew script (→ a Hebrew-shaping, nikkud-correct font). */
const HEBREW_SCRIPT_SUBTAGS = new Set(['he', 'iw', 'ji', 'yi']);

/** The first subtag of a BCP-47-ish code, lower-cased (`"ar-EG"` → `"ar"`, `null` → `""`). */
function primarySubtag(code: string | null | undefined): string {
  if (code === null || code === undefined) {
    return '';
  }
  return code.trim().toLowerCase().split('-')[0];
}

/**
 * The text direction for a language code. RTL for Arabic / Hebrew (and the other scripts that use
 * those two writing systems); `ltr` for everything else, including a missing/blank code.
 */
export function directionForCode(code: string | null | undefined): Direction {
  return RTL_SUBTAGS.has(primarySubtag(code)) ? 'rtl' : 'ltr';
}

/** Whether a language code is written right-to-left. */
export function isRtlCode(code: string | null | undefined): boolean {
  return directionForCode(code) === 'rtl';
}

/**
 * The Tailwind font-family utility class for a language's script, or `''` for the default app font.
 *
 * `font-arabic` / `font-hebrew` map (in `tailwind.config.ts`) to the self-hosted Noto fonts bundled
 * in `main.tsx`, which position harakat / nikkud correctly on their base letters. Latin-script
 * languages keep the default UI font.
 */
export function scriptFontClass(code: string | null | undefined): string {
  const subtag = primarySubtag(code);
  if (ARABIC_SCRIPT_SUBTAGS.has(subtag)) {
    return 'font-arabic';
  }
  if (HEBREW_SCRIPT_SUBTAGS.has(subtag)) {
    return 'font-hebrew';
  }
  return '';
}

/** The script-specific name for a language's optional vowel diacritics. */
export type VowelMarkTerm = 'harakat' | 'nikkud';

/**
 * The script-specific term for a language code's vowel marks:
 *  - `'harakat'` for Arabic-script codes (`ar`, `fa`, `ur`, …),
 *  - `'nikkud'` for Hebrew-script codes (`he`, `iw`, `yi`, …),
 *  - `null` for every other script (Latin / Cyrillic / …) and a blank/missing code.
 *
 * Derived from the SAME subtag sets that drive {@link scriptFontClass}, so the term shown to the
 * user and the diacritic-correct font can never disagree.
 */
export function vowelMarkTerm(
  code: string | null | undefined,
): VowelMarkTerm | null {
  const subtag = primarySubtag(code);
  if (ARABIC_SCRIPT_SUBTAGS.has(subtag)) {
    return 'harakat';
  }
  if (HEBREW_SCRIPT_SUBTAGS.has(subtag)) {
    return 'nikkud';
  }
  return null;
}

/**
 * Whether a code is written in a script that carries optional vowel diacritics worth toggling
 * (Arabic or Hebrew script) — i.e. whether the vowel-marks option is meaningful for it. Used by the
 * custom add-language path to decide whether to offer the checkbox at all.
 *
 * NOTE: this is SCRIPT-level, so it is `true` for `ur` (Urdu, Arabic script) even though the curated
 * Urdu entry is `vowelizable: false`; the custom path is the experimental escape hatch, and offering
 * the option there is harmless.
 */
export function isVowelizableCode(code: string | null | undefined): boolean {
  return vowelMarkTerm(code) !== null;
}

// ── Diacritics (harakat / nikkud) ────────────────────────────────────────────────────────────────
//
// The combining vowel marks of the Arabic and Hebrew scripts. Stripping these from displayed text
// (when the vowel-marks toggle is off) leaves the consonantal skeleton — the way these languages are
// normally written — while keeping the base letters untouched. Only nonspacing marks in the
// Arabic/Hebrew ranges are listed, so Latin precomposed accents (á, ü, …) and base letters (incl.
// the Arabic tatweel U+0640) are never affected.
const DIACRITIC_RANGES =
  // Hebrew points: niqqud + cantillation (te'amim) + the shin/sin dots and qamats-qatan.
  '\\u0591-\\u05BD\\u05BF\\u05C1\\u05C2\\u05C4\\u05C5\\u05C7' +
  // Arabic harakat/tashkil, Quranic annotation marks, superscript alef, and Extended-A marks.
  '\\u0610-\\u061A\\u064B-\\u065F\\u0670' +
  '\\u06D6-\\u06DC\\u06DF-\\u06E4\\u06E7\\u06E8\\u06EA-\\u06ED' +
  '\\u08D3-\\u08E1\\u08E3-\\u08FF';

/** Builds a fresh matcher each call so the stateful global-regex `lastIndex` never leaks. */
function diacriticMatcher(global: boolean): RegExp {
  return new RegExp(`[${DIACRITIC_RANGES}]`, global ? 'gu' : 'u');
}

/** Whether the text contains any Arabic/Hebrew vowel mark (harakat / nikkud). */
export function hasDiacritics(text: string): boolean {
  return diacriticMatcher(false).test(text);
}

/**
 * Remove the Arabic/Hebrew vowel marks from the text, leaving the base letters (and all other
 * characters) intact. A no-op for text without any such marks (e.g. Latin scripts).
 */
export function stripDiacritics(text: string): string {
  return text.replace(diacriticMatcher(true), '');
}

/**
 * The text to actually display given the vowel-marks preference: the original when marks are shown,
 * otherwise the same text with harakat / nikkud stripped. Centralises the toggle's one behaviour so
 * every render site (sentences, words, tap-a-word segments) strips identically.
 */
export function displayText(text: string, showVowels: boolean): string {
  return showVowels ? text : stripDiacritics(text);
}
