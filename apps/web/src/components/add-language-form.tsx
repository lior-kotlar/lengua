/**
 * Add-language form (task 4.4.2).
 *
 * Collects name (required), an optional code, a starting CEFR band, and the vowel-marks flag, then
 * creates the language via {@link useAddLanguage} (which also `PUT`s the starting band when it isn't
 * the default A1 — see the hook for the create-vs-proficiency reconciliation). On success it resets,
 * toasts, and hands the new language back via `onCreated` so the caller can make it active.
 *
 * Note: text direction is derived from the language `code` (group 4.9), so there is no manual
 * "direction" field here — reconciling the plan's "name + CEFR starting level/direction" wording.
 */
import { useState } from 'react';

import { FormField } from '@/components/form-field';
import { Button } from '@/components/ui/button';
import { toast } from '@/components/ui/use-toast';
import { CEFR_BANDS } from '@/lib/cefr';
import { isApiError } from '@/lib/api-client';
import { useAddLanguage, type LanguageOut } from '@/lib/languages';

export interface AddLanguageFormProps {
  /** Called with the created language after a successful add (e.g. to select it as active). */
  onCreated?: (language: LanguageOut) => void;
}

export function AddLanguageForm({ onCreated }: AddLanguageFormProps) {
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [band, setBand] = useState<string>(CEFR_BANDS[0]);
  const [vowelized, setVowelized] = useState(false);
  const [nameError, setNameError] = useState<string | null>(null);

  const addLanguage = useAddLanguage();

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const trimmed = name.trim();
    if (trimmed === '') {
      setNameError('Enter a language name.');
      return;
    }
    setNameError(null);

    addLanguage.mutate(
      { name: trimmed, code, vowelized, band },
      {
        onSuccess: (language) => {
          setName('');
          setCode('');
          setBand(CEFR_BANDS[0]);
          setVowelized(false);
          toast({
            title: 'Language added',
            description: `${language.name} is ready to use.`,
          });
          onCreated?.(language);
        },
        onError: (error) => {
          toast({
            variant: 'destructive',
            title: 'Could not add language',
            description: isApiError(error)
              ? error.message
              : 'Please try again.',
          });
        },
      },
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
      <FormField
        id="language-name"
        label="Name"
        placeholder="Spanish"
        autoComplete="off"
        value={name}
        onChange={(event) => setName(event.target.value)}
        error={nameError}
        required
      />
      <FormField
        id="language-code"
        label="Code (optional)"
        placeholder="es"
        autoComplete="off"
        value={code}
        onChange={(event) => setCode(event.target.value)}
      />

      <div className="space-y-1.5">
        <label htmlFor="language-band" className="text-sm font-medium">
          Starting level
        </label>
        <select
          id="language-band"
          value={band}
          onChange={(event) => setBand(event.target.value)}
          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        >
          {CEFR_BANDS.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </div>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={vowelized}
          onChange={(event) => setVowelized(event.target.checked)}
          className="h-4 w-4 rounded border-input"
        />
        Include vowel marks (harakat / nikkud)
      </label>

      <Button type="submit" disabled={addLanguage.isPending}>
        {addLanguage.isPending ? 'Adding…' : 'Add language'}
      </Button>
    </form>
  );
}
