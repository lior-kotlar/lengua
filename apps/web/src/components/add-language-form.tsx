/**
 * Add-language form (task 4.4.2; reworked for issue #95 — curated picker + custom fallback).
 *
 * PICKER-FIRST flow. The primary entry is a searchable {@link LanguageCombobox} over the curated
 * language list, not the free-text Name/Code fields:
 *
 *  - **Curated selection** → NO Name/Code inputs at all (the choice shows as a chip with a "Change"
 *    affordance). Below it: the Starting level select and — ONLY when the language is `vowelizable`
 *    (Arabic / Hebrew / Persian) — a vowel-marks toggle defaulted ON. Submits `{name, code,
 *    vowelized}` exactly as before; the S14 "code required when vowelized" rule holds by
 *    construction (a curated entry always has a code).
 *  - **Custom (experimental)** → today's free-form fields (Name prefilled from the search query,
 *    optional Code, level, vowel-marks checkbox) under a "Custom (experimental)" heading, keeping
 *    the S14 validation (a code is required when vowel marks are on) and deriving text direction +
 *    script font from the code as before. Typing a code whose primary subtag matches a curated
 *    entry pre-sets the vowel default; a soft, non-blocking hint warns if another of the user's
 *    languages already uses that code's primary subtag.
 *
 * On success it resets to the picker, toasts, and hands the language back via `onCreated`. While a
 * submit is in flight the step's "Change" / "Back to list" affordances are locked (issue #151), so a
 * slow-network user can't navigate away between pressing "Add" and that reset.
 */
import { useEffect, useRef, useState } from 'react';

import { LanguageCombobox } from '@/components/language-combobox';
import { FormField } from '@/components/form-field';
import { Button } from '@/components/ui/button';
import { toast } from '@/components/ui/use-toast';
import { CEFR_BANDS } from '@/lib/cefr';
import {
  findCuratedByCode,
  type CuratedLanguage,
} from '@/lib/curated-languages';
import { HelpTip, VOWEL_MARKS_HELP } from '@/components/help-tip';
import { isApiError } from '@/lib/api-client';
import {
  scriptFontClass,
  isRtlCode,
  isVowelizableCode,
  vowelMarkTerm,
} from '@/lib/language-text';
import {
  useAddLanguage,
  type AddLanguageInput,
  type LanguageOut,
} from '@/lib/languages';
import { cn } from '@/lib/utils';

export interface AddLanguageFormProps {
  /** Called with the created (or already-existing) language after a successful add. */
  onCreated?: (language: LanguageOut) => void;
  /**
   * The user's existing languages — used only for the custom path's soft duplicate hint (a
   * non-blocking notice when another language already uses the typed code's primary subtag).
   * Optional; the hint is simply skipped when omitted.
   */
  existingLanguages?: readonly LanguageOut[];
}

/** The three states of the form: the picker, a chosen curated language, or the custom fields. */
type Step =
  | { kind: 'picker' }
  | { kind: 'curated'; language: CuratedLanguage }
  | { kind: 'custom'; initialName: string };

/** A CEFR-level `<select>` shared by both submit paths. */
function LevelSelect({
  value,
  onChange,
  selectRef,
}: {
  value: string;
  onChange: (value: string) => void;
  /** Optional ref to the underlying `<select>` (used to move focus onto it on step entry). */
  selectRef?: React.Ref<HTMLSelectElement>;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor="language-band" className="text-body font-medium">
        Starting level
      </label>
      <select
        ref={selectRef}
        id="language-band"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="select-chevron h-10 w-full rounded-md border border-input bg-card px-3.5 pr-8 text-body transition-[border-color,box-shadow] duration-150 focus-visible:border-primary/60 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-primary/25 disabled:opacity-50"
      >
        {CEFR_BANDS.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    </div>
  );
}

export function AddLanguageForm({
  onCreated,
  existingLanguages,
}: AddLanguageFormProps) {
  const [step, setStep] = useState<Step>({ kind: 'picker' });
  // Whether the user has left the picker at least once. Used so the combobox auto-focuses when we
  // RETURN to it (Change / Back / post-submit reset) — landing keyboard & SR users back on the
  // search input — but NOT on the page's first render (which would steal focus on load).
  const returnedToPickerRef = useRef(false);

  function goToPicker() {
    returnedToPickerRef.current = true;
    setStep({ kind: 'picker' });
  }

  const addLanguage = useAddLanguage();

  /** Shared success/error handling for both submit paths. */
  function submit(input: AddLanguageInput) {
    addLanguage.mutate(input, {
      onSuccess: ({ language, created, bandError }) => {
        goToPicker();
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
          description: isApiError(error) ? error.message : 'Please try again.',
        });
      },
    });
  }

  if (step.kind === 'picker') {
    return (
      <LanguageCombobox
        autoFocus={returnedToPickerRef.current}
        onSelect={(language) => setStep({ kind: 'curated', language })}
        onSelectCustom={(query) =>
          setStep({ kind: 'custom', initialName: query })
        }
      />
    );
  }

  if (step.kind === 'curated') {
    return (
      <CuratedForm
        language={step.language}
        pending={addLanguage.isPending}
        onChangeLanguage={goToPicker}
        onSubmit={submit}
      />
    );
  }

  return (
    <CustomForm
      initialName={step.initialName}
      existingLanguages={existingLanguages}
      pending={addLanguage.isPending}
      onBack={goToPicker}
      onSubmit={submit}
    />
  );
}

/** The curated submit path: a chip + level + (conditional) vowel-marks toggle. No Name/Code inputs. */
function CuratedForm({
  language,
  pending,
  onChangeLanguage,
  onSubmit,
}: {
  language: CuratedLanguage;
  pending: boolean;
  onChangeLanguage: () => void;
  onSubmit: (input: AddLanguageInput) => void;
}) {
  const [band, setBand] = useState<string>(CEFR_BANDS[0]);
  // Fixes #95 pain point 3: default vowel marks ON for vowelizable languages so a beginner adding
  // Arabic gets harakat without opting in; advanced users untick.
  const [vowelized, setVowelized] = useState(language.vowelizable);
  const levelRef = useRef<HTMLSelectElement>(null);

  // Move focus onto the first meaningful control when this step appears, so a keyboard/SR user who
  // pressed Enter on a curated row isn't dropped to `<body>`.
  useEffect(() => {
    levelRef.current?.focus();
  }, []);

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    onSubmit({
      name: language.name,
      code: language.code,
      vowelized: language.vowelizable ? vowelized : false,
      band,
      // Provenance for the funnel event (#151): this is the curated picker path.
      curated: true,
    });
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4" noValidate>
      {/* The selection chip — the read-only substitute for the Name/Code inputs. */}
      <div className="flex items-center justify-between gap-3 rounded-md border bg-secondary/50 px-3.5 py-2.5">
        <span className="flex min-w-0 items-baseline gap-2">
          <span className="truncate text-body font-medium">
            {language.name}
          </span>
          <span
            lang={language.code}
            className={cn(
              'shrink-0 text-subhead text-muted-foreground',
              scriptFontClass(language.code),
            )}
          >
            {language.nativeName}
          </span>
        </span>
        <button
          type="button"
          onClick={onChangeLanguage}
          // #151: locked while a submit is in flight so a slow-network user can't navigate back to
          // the picker between pressing "Add" and the success reset (which would clobber their view).
          disabled={pending}
          className="shrink-0 rounded text-subhead font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50"
        >
          Change
        </button>
      </div>

      <LevelSelect value={band} onChange={setBand} selectRef={levelRef} />

      {language.vowelizable && (
        <div className="flex items-center gap-2 text-body">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={vowelized}
              onChange={(event) => setVowelized(event.target.checked)}
              className="h-4 w-4 rounded border-input"
            />
            Include vowel marks (
            {vowelMarkTerm(language.code) ?? 'harakat / nikkud'})
          </label>
          <HelpTip text={VOWEL_MARKS_HELP} label="About vowel marks" />
        </div>
      )}

      <Button type="submit" disabled={pending}>
        {pending ? 'Adding…' : 'Add language'}
      </Button>
    </form>
  );
}

/**
 * The custom (experimental) submit path: today's free-form fields, with the code→curated
 * smart-default and a soft duplicate hint. RTL/font are derived from the code exactly as before.
 */
function CustomForm({
  initialName,
  existingLanguages,
  pending,
  onBack,
  onSubmit,
}: {
  initialName: string;
  existingLanguages?: readonly LanguageOut[];
  pending: boolean;
  onBack: () => void;
  onSubmit: (input: AddLanguageInput) => void;
}) {
  const [name, setName] = useState(initialName);
  const [code, setCode] = useState('');
  const [band, setBand] = useState<string>(CEFR_BANDS[0]);
  const [vowelized, setVowelized] = useState(false);
  // Once the user hand-toggles the vowel checkbox, stop letting a code lookup override their choice.
  const [vowelizedTouched, setVowelizedTouched] = useState(false);
  const [nameError, setNameError] = useState<string | null>(null);
  const [codeError, setCodeError] = useState<string | null>(null);
  const formRef = useRef<HTMLFormElement>(null);

  // Move focus onto the first field when this step appears (a keyboard/SR user who chose the custom
  // row lands in the Name input rather than at `<body>`). Places the caret at the end of the
  // prefilled query so they can keep typing.
  useEffect(() => {
    const nameInput =
      formRef.current?.querySelector<HTMLInputElement>('#language-name');
    if (nameInput) {
      nameInput.focus();
      const end = nameInput.value.length;
      nameInput.setSelectionRange(end, end);
    }
  }, []);

  const trimmedCode = code.trim();
  const curatedByCode = findCuratedByCode(trimmedCode);
  // The script-specific vowel-mark term for the typed code (`'harakat'` / `'nikkud'`), or null when
  // the code's script has no vowel marks — in which case the checkbox is not offered at all.
  const vowelTerm = vowelMarkTerm(trimmedCode);

  // Soft, non-blocking duplicate hint: another of the user's languages already uses this code's
  // primary subtag. Submission stays allowed (the server is idempotent by name).
  const subtag = trimmedCode.toLowerCase().split('-')[0];
  const duplicate =
    subtag !== '' && existingLanguages !== undefined
      ? existingLanguages.find(
          (lang) =>
            (lang.code ?? '').trim().toLowerCase().split('-')[0] === subtag,
        )
      : undefined;

  function handleCodeChange(next: string) {
    setCode(next);
    setCodeError(null);
    // The vowel-marks checkbox only exists for Arabic/Hebrew-script codes. When the code isn't one,
    // the checkbox is hidden — so force the option OFF (and clear the manual-touch flag) rather than
    // carry a stale `vowelized: true` that a Latin language would then submit / trip S14 on.
    if (!isVowelizableCode(next)) {
      setVowelized(false);
      setVowelizedTouched(false);
      return;
    }
    // Smart default: typing a known code pre-sets the vowel-marks default (until the user overrides).
    if (!vowelizedTouched) {
      const curated = findCuratedByCode(next);
      setVowelized(curated?.vowelizable ?? false);
    }
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    const trimmedName = name.trim();

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

    onSubmit({
      name: trimmedName,
      code: trimmedCode,
      vowelized,
      band,
      // Provenance for the funnel event (#151): this is the custom/experimental path, even when the
      // typed name/code happens to match a curated language.
      curated: false,
    });
  }

  return (
    <form
      ref={formRef}
      onSubmit={handleSubmit}
      className="space-y-4"
      noValidate
    >
      <div className="space-y-1.5">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-headline">Custom (experimental)</h3>
          <button
            type="button"
            onClick={onBack}
            // #151: locked while a submit is in flight (see CuratedForm) so the user can't leave the
            // custom step between pressing "Add" and the success reset.
            disabled={pending}
            className="shrink-0 rounded text-subhead font-medium text-primary hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50"
          >
            Back to list
          </button>
        </div>
        <p className="text-footnote text-muted-foreground">
          Not on the curated list — sentence quality depends on the AI model’s
          coverage of this language. Text direction and vowel marks are derived
          from the code.
        </p>
      </div>

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
          onChange={(event) => handleCodeChange(event.target.value)}
          error={codeError}
          required={vowelized}
        />
        <p
          id="language-code-hint"
          className="text-footnote text-muted-foreground"
        >
          Sets text direction and script font. Required for vowel marks — common
          right-to-left codes: Hebrew <code className="font-mono">he</code>,
          Arabic <code className="font-mono">ar</code>, Persian{' '}
          <code className="font-mono">fa</code>.
        </p>
        {curatedByCode !== undefined && (
          <p className="text-footnote text-muted-foreground">
            Recognized as{' '}
            <span className="font-medium">{curatedByCode.name}</span> (
            {isRtlCode(trimmedCode) ? 'right-to-left' : 'left-to-right'}).
          </p>
        )}
        {duplicate !== undefined && (
          <p role="status" className="text-footnote text-hig-orange-deep">
            You already have a language with code{' '}
            <code className="font-mono">{subtag}</code> ({duplicate.name}).
          </p>
        )}
      </div>

      <LevelSelect value={band} onChange={setBand} />

      {vowelTerm !== null && (
        <div className="flex items-center gap-2 text-body">
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={vowelized}
              onChange={(event) => {
                setVowelized(event.target.checked);
                setVowelizedTouched(true);
              }}
              className="h-4 w-4 rounded border-input"
            />
            Include vowel marks ({vowelTerm})
          </label>
          <HelpTip text={VOWEL_MARKS_HELP} label="About vowel marks" />
        </div>
      )}

      <Button type="submit" disabled={pending}>
        {pending ? 'Adding…' : 'Add language'}
      </Button>
    </form>
  );
}
