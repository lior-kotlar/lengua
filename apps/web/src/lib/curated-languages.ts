/**
 * Curated language list (issue #95, Option B) — the single source of truth for the add-language
 * picker.
 *
 * Picking an entry sets the language `name` (interpolated verbatim into the generation prompt),
 * the `code`, and the vowel-marks default in one gesture — so a beginner adding Arabic gets the
 * right code, right-to-left direction, a script-correct font, and harakat *without* knowing to
 * opt in. Everything not on this list stays addable via the free-form "custom / experimental"
 * path (see `add-language-form.tsx`).
 *
 * DESIGN NOTE — `rtl` is deliberately NOT a field. Text direction and the script font are DERIVED
 * from the `code` by {@link import('./language-text')} (`directionForCode`, `scriptFontClass`), so
 * duplicating them here would be a second source of truth that could drift. `curated-languages.test`
 * asserts the two stay consistent instead. Likewise `script` is carried for future font/spacing
 * work but is NOT persisted (no DB column until something consumes it).
 */

/** A writing system tag. Carried for future font/spacing decisions; never persisted. */
export type Script =
  | 'Latin'
  | 'Cyrillic'
  | 'Greek'
  | 'Arabic'
  | 'Hebrew'
  | 'Devanagari'
  | 'Bengali'
  | 'Han'
  | 'Japanese'
  | 'Hangul'
  | 'Thai';

/** One curated language: what the picker shows and submits. */
export interface CuratedLanguage {
  /** English name — what is stored as the language `name` and interpolated into prompts. */
  name: string;
  /** Endonym, shown as secondary text in its own script (also hints the writing system). */
  nativeName: string;
  /** Lowercase primary subtag, e.g. "es". Drives direction/font via lib/language-text.ts. */
  code: string;
  /** Writing system tag for future font/spacing work (NOT persisted). */
  script: Script;
  /** Language uses optional vowel diacritics (harakat / nikkud) worth toggling. */
  vowelizable: boolean;
}

/**
 * The curated set — the CEFR-taught European canon plus the major world languages the generation
 * model handles confidently. Alphabetical by English `name` (the picker preserves this order).
 *
 * `vowelizable: true` is reserved for the three languages whose everyday orthography drops optional
 * vowel diacritics that a learner benefits from toggling — Arabic (harakat), Hebrew (nikkud), and
 * Persian (which shares the Arabic script and its harakat). This matches the existing S14 hint in
 * the add form (`he` / `ar` / `fa`).
 */
export const CURATED_LANGUAGES: readonly CuratedLanguage[] = [
  {
    name: 'Arabic',
    nativeName: 'العربية',
    code: 'ar',
    script: 'Arabic',
    vowelizable: true,
  },
  {
    name: 'Bengali',
    nativeName: 'বাংলা',
    code: 'bn',
    script: 'Bengali',
    vowelizable: false,
  },
  {
    name: 'Bulgarian',
    nativeName: 'Български',
    code: 'bg',
    script: 'Cyrillic',
    vowelizable: false,
  },
  {
    name: 'Catalan',
    nativeName: 'Català',
    code: 'ca',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'Chinese (Mandarin)',
    nativeName: '中文',
    code: 'zh',
    script: 'Han',
    vowelizable: false,
  },
  {
    name: 'Croatian',
    nativeName: 'Hrvatski',
    code: 'hr',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'Czech',
    nativeName: 'Čeština',
    code: 'cs',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'Danish',
    nativeName: 'Dansk',
    code: 'da',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'Dutch',
    nativeName: 'Nederlands',
    code: 'nl',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'English',
    nativeName: 'English',
    code: 'en',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'Estonian',
    nativeName: 'Eesti',
    code: 'et',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'Filipino (Tagalog)',
    nativeName: 'Filipino',
    code: 'fil',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'Finnish',
    nativeName: 'Suomi',
    code: 'fi',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'French',
    nativeName: 'Français',
    code: 'fr',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'German',
    nativeName: 'Deutsch',
    code: 'de',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'Greek',
    nativeName: 'Ελληνικά',
    code: 'el',
    script: 'Greek',
    vowelizable: false,
  },
  {
    name: 'Hebrew',
    nativeName: 'עברית',
    code: 'he',
    script: 'Hebrew',
    vowelizable: true,
  },
  {
    name: 'Hindi',
    nativeName: 'हिन्दी',
    code: 'hi',
    script: 'Devanagari',
    vowelizable: false,
  },
  {
    name: 'Hungarian',
    nativeName: 'Magyar',
    code: 'hu',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'Icelandic',
    nativeName: 'Íslenska',
    code: 'is',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'Indonesian',
    nativeName: 'Bahasa Indonesia',
    code: 'id',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'Italian',
    nativeName: 'Italiano',
    code: 'it',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'Japanese',
    nativeName: '日本語',
    code: 'ja',
    script: 'Japanese',
    vowelizable: false,
  },
  {
    name: 'Korean',
    nativeName: '한국어',
    code: 'ko',
    script: 'Hangul',
    vowelizable: false,
  },
  {
    name: 'Latvian',
    nativeName: 'Latviešu',
    code: 'lv',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'Lithuanian',
    nativeName: 'Lietuvių',
    code: 'lt',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'Malay',
    nativeName: 'Bahasa Melayu',
    code: 'ms',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'Norwegian',
    nativeName: 'Norsk',
    code: 'no',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'Persian (Farsi)',
    nativeName: 'فارسی',
    code: 'fa',
    script: 'Arabic',
    vowelizable: true,
  },
  {
    name: 'Polish',
    nativeName: 'Polski',
    code: 'pl',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'Portuguese',
    nativeName: 'Português',
    code: 'pt',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'Romanian',
    nativeName: 'Română',
    code: 'ro',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'Russian',
    nativeName: 'Русский',
    code: 'ru',
    script: 'Cyrillic',
    vowelizable: false,
  },
  {
    name: 'Serbian',
    nativeName: 'Српски',
    code: 'sr',
    script: 'Cyrillic',
    vowelizable: false,
  },
  {
    name: 'Slovak',
    nativeName: 'Slovenčina',
    code: 'sk',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'Slovenian',
    nativeName: 'Slovenščina',
    code: 'sl',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'Spanish',
    nativeName: 'Español',
    code: 'es',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'Swahili',
    nativeName: 'Kiswahili',
    code: 'sw',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'Swedish',
    nativeName: 'Svenska',
    code: 'sv',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'Thai',
    nativeName: 'ไทย',
    code: 'th',
    script: 'Thai',
    vowelizable: false,
  },
  {
    name: 'Turkish',
    nativeName: 'Türkçe',
    code: 'tr',
    script: 'Latin',
    vowelizable: false,
  },
  {
    name: 'Ukrainian',
    nativeName: 'Українська',
    code: 'uk',
    script: 'Cyrillic',
    vowelizable: false,
  },
  {
    name: 'Urdu',
    nativeName: 'اردو',
    code: 'ur',
    script: 'Arabic',
    vowelizable: false,
  },
  {
    name: 'Vietnamese',
    nativeName: 'Tiếng Việt',
    code: 'vi',
    script: 'Latin',
    vowelizable: false,
  },
];

/** The first subtag of a BCP-47-ish code, lower-cased (`"pt-BR"` → `"pt"`). Empty for blank. */
function primarySubtag(code: string | null | undefined): string {
  if (code === null || code === undefined) {
    return '';
  }
  return code.trim().toLowerCase().split('-')[0];
}

/**
 * Find the curated entry whose English `name` matches `name`, case-insensitively and trimmed.
 * Returns `undefined` for a non-curated (custom) name — the caller uses that to drive the
 * "experimental" badge and the picker's custom fallback. A blank/whitespace name never matches.
 */
export function findCurated(name: string): CuratedLanguage | undefined {
  const needle = name.trim().toLowerCase();
  if (needle === '') {
    return undefined;
  }
  return CURATED_LANGUAGES.find((lang) => lang.name.toLowerCase() === needle);
}

/**
 * Find the curated entry whose `code` shares the primary subtag of `code` (so `pt-BR` matches
 * Portuguese `pt`). Powers the custom-path smart defaults — typing a known code pre-sets its
 * vowel-marks default. Returns `undefined` for a blank/unknown code.
 */
export function findCuratedByCode(
  code: string | null | undefined,
): CuratedLanguage | undefined {
  const subtag = primarySubtag(code);
  if (subtag === '') {
    return undefined;
  }
  return CURATED_LANGUAGES.find((lang) => lang.code === subtag);
}
