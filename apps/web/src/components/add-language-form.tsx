/**
 * Add-language form (task 4.4.2).
 *
 * Collects name (required), a code, a starting CEFR band, and the vowel-marks flag, then creates the
 * language via {@link useAddLanguage} (which also `PUT`s the starting band for a brand-new language
 * when it isn't the default A1 — see the hook for the create-vs-proficiency reconciliation). On
 * success it resets, toasts, and hands the language back via `onCreated` so the caller can make it
 * active.
 *
 * Text direction + script font are DERIVED from the language `code` (group 4.9) — there is no manual
 * "direction" field. Because of that, vowel marks (harakat / nikkud) only render correctly when a
 * code is set, so the code is REQUIRED whenever vowel marks are enabled (with inline help for the
 * common right-to-left codes). A blank-code + vowelized language would otherwise fall back to an
 * LTR Latin font with mispositioned diacritics (finding S14).
 */
import { useState } from 'react';

import { FormField } from '@/components/form-field';
import { Button } from '@/components/ui/button';
import { toast } from '@/components/ui/use-toast';
import { CEFR_BANDS } from '@/lib/cefr';
import { isApiError } from '@/lib/api-client';
import { useAddLanguage, type LanguageOut } from '@/lib/languages';

export interface AddLanguageFormProps {
  /** Called with the created (or already-existing) language after a successful add. */
  onCreated?: (language: LanguageOut) => void;
}

export function AddLanguageForm({ onCreated }: AddLanguageFormProps) {
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [band, setBand] = useState<string>(CEFR_BANDS[0]);
  const [vowelized, setVowelized] = useState(false);
  const [nameError, setNameError] = useState<string | null>(null);
  const [codeError, setCodeError] = useState<string | null>(null);

  const addLanguage = useAddLanguage();

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const trimmedName = name.trim();
    const trimmedCode = code.trim();

    let invalid = false;
    if (trimmedName === '') {
      setNameError('Enter a language name.');
      invalid = true;
    } else {
      setNameError(null);
    }
    // S14: vowel marks render in a script-correct font + direction derived from the code, so a code
    // is required when they're on. Without one the text would render LTR/Latin with broken nikkud.
    if (vowelized && trimmedCode === '') {
      setCodeError(
        'Enter a language code (e.g. he, ar, fa) so vowel marks render correctly.',
      );
      invalid = true;
    } else {
      setCodeError(null);
    }
    if (invalid) {
      return;
    }

    addLanguage.mutate(
      { name: trimmedName, code: trimmedCode, vowelized, band },
      {
        onSuccess: ({ language, created, bandError }) => {
          setName('');
          setCode('');
          setBand(CEFR_BANDS[0]);
          setVowelized(false);
          if (!created) {
            // S3: idempotent re-add — the existing language (and its CEFR level) is untouched.
            toast({
              title: 'Already in your languages',
              description: `You already have ${language.name}.`,
            });
          } else if (bandError) {
            // S12: created, but the starting-level write failed — flag it without claiming failure.
            toast({
              variant: 'destructive',
              title: 'Added, but the starting level wasn’t set',
              description: `${language.name} was added at the default level — set its level from the level panel.`,
            });
          } else {
            toast({
              title: 'Language added',
              description: `${language.name} is ready to use.`,
            });
          }
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
      <div className="space-y-1.5">
        <FormField
          id="language-code"
          label={vowelized ? 'Code' : 'Code (optional)'}
          placeholder="es"
          autoComplete="off"
          value={code}
          onChange={(event) => setCode(event.target.value)}
          error={codeError}
          required={vowelized}
        />
        <p id="language-code-hint" className="text-xs text-muted-foreground">
          Sets text direction and script font. Required for vowel marks — common right-to-left
          codes: Hebrew <code className="font-mono">he</code>, Arabic{' '}
          <code className="font-mono">ar</code>, Persian{' '}
          <code className="font-mono">fa</code>.
        </p>
      </div>

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
