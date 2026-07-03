/**
 * Settings screen (group 4.8) — the React port of the legacy Streamlit Settings page, restyled to
 * the Apple grouped-list grammar (redesign PR5).
 *
 * Edits the three per-user preferences kept in the generic `{key: value}` settings store — the daily
 * new-card limit, the daily total-card limit, and the Discover default word count — and saves them
 * with `PUT /settings`. Each field is validated client-side against its bounds before save (see
 * `lib/settings.ts` for where those bounds come from), so the form never sends a value the server
 * would reject. Values seed from `GET /settings`, falling back to each field's default when unset.
 */
import { useState } from 'react';
import { Loader2, Save } from 'lucide-react';

import { AnalyticsConsentToggle } from '@/components/analytics-consent-toggle';
import { ErrorState } from '@/components/error-state';
import { LoadingState } from '@/components/loading-state';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { toast } from '@/components/ui/use-toast';
import { apiErrorMessage } from '@/lib/api-client';
import {
  crossFieldSettingError,
  DAILY_NEW_LIMIT_KEY,
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
    <section className="mx-auto max-w-2xl space-y-8">
      <div className="space-y-1">
        <h1 className="text-large-title">Settings</h1>
        <p className="text-subhead text-muted-foreground">
          Tune your daily review limits and how many words Discover suggests.
        </p>
      </div>

      {settings.isPending ? (
        <LoadingState label="Loading your settings…" />
      ) : settings.isError ? (
        // Refetching an errored, data-less query flips it back to its pending state, so the loading
        // branch above renders while the retry is in flight — this button never shows an in-flight label.
        <ErrorState
          title="Could not load your settings"
          description="Something went wrong fetching your preferences. Please try again."
          retryLabel="Retry"
          onRetry={() => void settings.refetch()}
        />
      ) : (
        <SettingsForm settings={settings.data} />
      )}

      {/* Product-analytics consent toggle (5.9.1) — independent of the settings load above. */}
      <AnalyticsConsentToggle />
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
  // state is seeded with one entry per field). The cross-field rule (new ≤ total) attaches to the
  // new-cards field, but only once that field passes its own per-field checks, so the more specific
  // error shows first. The Save button is gated on every field being valid.
  const crossError = crossFieldSettingError(values);
  const fields = SETTINGS_FIELDS.map((field) => {
    const value = values[field.key];
    const fieldError = validateSettingValue(field, value);
    const error =
      fieldError === null && field.key === DAILY_NEW_LIMIT_KEY
        ? crossError
        : fieldError;
    return { field, value, error };
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
    <form onSubmit={handleSubmit} className="space-y-5" noValidate>
      <div className="space-y-1">
        <p className="text-caption uppercase text-muted-foreground">
          Review &amp; discovery
        </p>
        <p className="text-footnote text-muted-foreground">
          These apply across all of your languages.
        </p>
      </div>

      {/* Grouped list — one hairline-divided row per setting. */}
      <div className="divide-y overflow-hidden rounded-lg border bg-card shadow-card">
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
      </div>

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
  );
}

interface SettingFieldProps {
  field: SettingsFieldDef;
  value: string;
  error: string | null;
  disabled: boolean;
  onChange: (value: string) => void;
}

/** One setting as a grouped-list row: label + description on the left, numeric input on the right. */
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
    <div className="px-5 py-4">
      <div className="flex items-center justify-between gap-4">
        <div className="min-w-0 space-y-0.5">
          <label htmlFor={field.key} className="text-body font-medium">
            {field.label}
          </label>
          <p id={hintId} className="text-footnote text-muted-foreground">
            {field.description}
          </p>
        </div>
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
          className={cn(
            'h-9 w-24 shrink-0 text-right tabular-nums',
            invalid && 'border-destructive',
          )}
        />
      </div>
      {invalid && (
        <p
          id={errorId}
          role="alert"
          className="mt-2 text-footnote text-destructive"
        >
          {error}
        </p>
      )}
    </div>
  );
}
