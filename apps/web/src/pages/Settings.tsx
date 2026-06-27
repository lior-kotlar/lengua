/**
 * Settings screen (group 4.8) — the React port of the legacy Streamlit Settings page.
 *
 * Edits the three per-user preferences kept in the generic `{key: value}` settings store — the daily
 * new-card limit, the daily total-card limit, and the Discover default word count — and saves them
 * with `PUT /settings`. Each field is validated client-side against its bounds before save (see
 * `lib/settings.ts` for where those bounds come from), so the form never sends a value the server
 * would reject. Values seed from `GET /settings`, falling back to each field's default when unset.
 */
import { useState } from 'react';
import { Loader2, Save } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { toast } from '@/components/ui/use-toast';
import { apiErrorMessage } from '@/lib/api-client';
import {
  initialSettingValue,
  SETTINGS_FIELDS,
  useSettingsQuery,
  useUpdateSettings,
  validateSettingValue,
  type SettingsFieldDef,
  type SettingsOut,
} from '@/lib/settings';
import { cn } from '@/lib/utils';

export default function Settings() {
  const settings = useSettingsQuery();

  return (
    <section className="mx-auto max-w-2xl space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Tune your daily review limits and how many words Discover suggests.
        </p>
      </div>

      {settings.isPending ? (
        <p
          className="flex items-center gap-2 text-sm text-muted-foreground"
          aria-busy="true"
        >
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          Loading your settings…
        </p>
      ) : settings.isError ? (
        <Card role="alert" className="border-destructive/50">
          <CardHeader>
            <CardTitle className="text-lg">
              Could not load your settings
            </CardTitle>
            <CardDescription>
              Something went wrong fetching your preferences. Please try again.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {/* Refetching an errored, data-less query flips the query back to its pending state, so
                the loading branch above renders while the retry is in flight — this button itself
                never shows an in-flight label. */}
            <Button variant="outline" onClick={() => void settings.refetch()}>
              Retry
            </Button>
          </CardContent>
        </Card>
      ) : (
        <SettingsForm settings={settings.data} />
      )}
    </section>
  );
}

/** The editable settings form, seeded once from the loaded settings map. */
function SettingsForm({ settings }: { settings: SettingsOut }) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      SETTINGS_FIELDS.map((field) => [
        field.key,
        initialSettingValue(settings, field),
      ]),
    ),
  );

  const update = useUpdateSettings();

  // Pair every field with its current value + validation error (the value is always present — the
  // state is seeded with one entry per field). The Save button is gated on all being valid.
  const fields = SETTINGS_FIELDS.map((field) => {
    const value = values[field.key];
    return { field, value, error: validateSettingValue(field, value) };
  });
  const hasError = fields.some((entry) => entry.error !== null);

  function setValue(key: string, value: string) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (hasError || update.isPending) {
      return;
    }
    // Send all known fields (normalized to their trimmed integer string). PUT merges, so this never
    // disturbs other keys (e.g. the per-kind LLM caps) the user may have set elsewhere.
    const payload = Object.fromEntries(
      fields.map(({ field, value }) => [
        field.key,
        String(Number(value.trim())),
      ]),
    );
    update.mutate(payload, {
      onSuccess: () => {
        toast({
          title: 'Settings saved',
          description: 'Your preferences were updated.',
        });
      },
      onError: (error) => {
        toast({
          variant: 'destructive',
          title: 'Could not save settings',
          description: apiErrorMessage(error, 'Please try again.'),
        });
      },
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Review &amp; discovery</CardTitle>
        <CardDescription>
          These apply across all of your languages.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit} className="space-y-5" noValidate>
          {fields.map(({ field, value, error }) => (
            <SettingField
              key={field.key}
              field={field}
              value={value}
              error={error}
              disabled={update.isPending}
              onChange={(next) => setValue(field.key, next)}
            />
          ))}

          <Button type="submit" disabled={hasError || update.isPending}>
            {update.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                Saving…
              </>
            ) : (
              <>
                <Save className="h-4 w-4" aria-hidden="true" />
                Save settings
              </>
            )}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}

interface SettingFieldProps {
  field: SettingsFieldDef;
  value: string;
  error: string | null;
  disabled: boolean;
  onChange: (value: string) => void;
}

/** One labeled integer setting input with help text + inline validation. */
function SettingField({
  field,
  value,
  error,
  disabled,
  onChange,
}: SettingFieldProps) {
  const hintId = `${field.key}-hint`;
  const errorId = `${field.key}-error`;
  const invalid = error !== null;
  return (
    <div className="space-y-1.5">
      <label htmlFor={field.key} className="text-sm font-medium">
        {field.label}
      </label>
      <Input
        id={field.key}
        type="number"
        inputMode="numeric"
        min={field.min}
        max={field.max}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        aria-invalid={invalid || undefined}
        aria-describedby={invalid ? errorId : hintId}
        className={cn('max-w-[10rem]', invalid && 'border-destructive')}
      />
      {invalid ? (
        <p id={errorId} role="alert" className="text-xs text-destructive">
          {error}
        </p>
      ) : (
        <p id={hintId} className="text-xs text-muted-foreground">
          {field.description}
        </p>
      )}
    </div>
  );
}
