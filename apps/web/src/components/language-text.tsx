/**
 * `LanguageText` (group 4.9) — renders a piece of target-language text with the correct direction,
 * a diacritic-correct script font, and the vowel-marks preference applied.
 *
 * Used everywhere a non-interactive target string is shown (generated sentences + their used-word
 * chips, Discover suggestions, the recognition card's prompt). Interactive (tappable) sentences use
 * {@link import('@/components/tappable-sentence').TappableSentence}, which applies the same three
 * concerns per word. Direction + font are derived from the language code (4.4 decision); the marks
 * are stripped when `showVowels` is false.
 */
import {
  displayText,
  directionForCode,
  scriptFontClass,
} from '@/lib/language-text';
import type { LanguageOut } from '@/lib/languages';
import { cn } from '@/lib/utils';

export interface LanguageTextProps {
  /** The raw target-language text. */
  text: string;
  /** The language it is written in (drives direction + script font). */
  language: Pick<LanguageOut, 'code'>;
  /** Whether to show vowel marks (false strips harakat / nikkud for display). */
  showVowels: boolean;
  /** Element to render as — block `p` (default) or inline `span`. */
  as?: 'p' | 'span';
  className?: string;
}

export function LanguageText({
  text,
  language,
  showVowels,
  as: Tag = 'p',
  className,
}: LanguageTextProps) {
  const dir = directionForCode(language.code);
  return (
    <Tag dir={dir} className={cn(scriptFontClass(language.code), className)}>
      {displayText(text, showVowels)}
    </Tag>
  );
}
