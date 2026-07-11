/**
 * Vowel-marks toggle (task 4.9.3) — a switch that shows/hides the harakat / nikkud in displayed
 * target-language text.
 *
 * Self-gating: it renders only when the active language is `vowelized` (Arabic / Hebrew with
 * vocalization), so it never clutters Latin-script screens. The preference itself lives in
 * {@link useVowelMarks} (persisted device-wide), so toggling here updates every screen at once.
 */
import { HelpTip, VOWEL_MARKS_HELP } from '@/components/help-tip';
import { useActiveLanguage } from '@/components/active-language-context';
import { useVowelMarks } from '@/components/vowel-marks-context';
import { Switch } from '@/components/ui/switch';
import { vowelMarkTerm } from '@/lib/language-text';

export function VowelMarksToggle() {
  const { activeLanguage } = useActiveLanguage();
  const { showVowels, setShowVowels } = useVowelMarks();

  // Only meaningful for languages whose text carries vowel marks.
  if (activeLanguage === null || !activeLanguage.vowelized) {
    return null;
  }

  // Show the script-specific term ("harakat" / "nikkud"); fall back to the generic label for an odd
  // vowelized language whose code isn't a recognised Arabic/Hebrew script.
  const term = vowelMarkTerm(activeLanguage.code);
  const labelText = term ? `Vowel marks (${term})` : 'Vowel marks';

  return (
    <div className="flex w-fit items-center gap-2.5 text-subhead">
      <label className="flex items-center gap-2.5">
        <Switch
          checked={showVowels}
          onCheckedChange={setShowVowels}
          aria-label="Show vowel marks"
        />
        <span className="font-medium text-muted-foreground">{labelText}</span>
      </label>
      <HelpTip text={VOWEL_MARKS_HELP} label="About vowel marks" />
    </div>
  );
}
