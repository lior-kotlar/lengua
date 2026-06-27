/**
 * Vowel-marks toggle (task 4.9.3) — a switch that shows/hides the harakat / nikkud in displayed
 * target-language text.
 *
 * Self-gating: it renders only when the active language is `vowelized` (Arabic / Hebrew with
 * vocalization), so it never clutters Latin-script screens. The preference itself lives in
 * {@link useVowelMarks} (persisted device-wide), so toggling here updates every screen at once.
 */
import { useActiveLanguage } from '@/components/active-language-context';
import { useVowelMarks } from '@/components/vowel-marks-context';
import { cn } from '@/lib/utils';

export function VowelMarksToggle() {
  const { activeLanguage } = useActiveLanguage();
  const { showVowels, setShowVowels } = useVowelMarks();

  // Only meaningful for languages whose text carries vowel marks.
  if (activeLanguage === null || !activeLanguage.vowelized) {
    return null;
  }

  return (
    <label className="flex w-fit items-center gap-2 text-sm">
      <button
        type="button"
        role="switch"
        aria-checked={showVowels}
        aria-label="Show vowel marks"
        onClick={() => setShowVowels(!showVowels)}
        className={cn(
          'relative inline-flex h-5 w-9 shrink-0 items-center rounded-full transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
          showVowels ? 'bg-primary' : 'bg-muted',
        )}
      >
        <span
          aria-hidden="true"
          className={cn(
            'inline-block h-4 w-4 transform rounded-full bg-background shadow transition-transform',
            showVowels ? 'translate-x-4' : 'translate-x-0.5',
          )}
        />
      </button>
      <span className="font-medium text-muted-foreground">Vowel marks</span>
    </label>
  );
}
