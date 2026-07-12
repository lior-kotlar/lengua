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
import { vowelMarksLabel } from '@/lib/language-text';

export function VowelMarksToggle() {
  const { activeLanguage } = useActiveLanguage();
  const { showVowels, setShowVowels } = useVowelMarks();

  // Only meaningful for languages whose text carries vowel marks.
  if (activeLanguage === null || !activeLanguage.vowelized) {
    return null;
  }

  // Show the script-specific term ("harakat" / "nikkud"); fall back to the generic label for an odd
  // vowelized language whose code isn't a recognised Arabic/Hebrew script. The SAME string drives the
  // switch's accessible name (below), so the visible label and the accessible name can never diverge
  // — a WCAG 2.5.3 "label in name" requirement (the accessible name must contain the visible label).
  const labelText = vowelMarksLabel(activeLanguage.code);

  return (
    <div className="flex w-fit items-center gap-2.5 text-subhead">
      <label className="flex items-center gap-2.5">
        <Switch
          checked={showVowels}
          onCheckedChange={setShowVowels}
          aria-label={labelText}
        />
        <span className="font-medium text-muted-foreground">{labelText}</span>
      </label>
      <HelpTip text={VOWEL_MARKS_HELP} label="About vowel marks" />
    </div>
  );
}
