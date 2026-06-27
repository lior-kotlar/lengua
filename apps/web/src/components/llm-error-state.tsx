/**
 * Shared friendly error state for LLM-bound calls (Generate group 4.5; Discover group 4.7).
 *
 * Both screens classify a failed `/generate` or `/discover` the same way (via `lib/llm-error.ts`)
 * and must render FRIENDLY, ACTIONABLE states instead of a raw error. This one component is that
 * rendering, so the two screens never duplicate it:
 *
 *  - the quota-429 "daily limit reached" case → the dedicated, reusable {@link DailyLimitPanel}
 *    (the single shared 429 panel the cross-cutting contract requires; group 4.10.2 verifies it);
 *  - every other case (rate-limited / server-busy / verify-email / generic) → a friendly inline
 *    card whose title + body come from {@link describeLlmError}, with an optional `transientHint`
 *    shown for the transient (retryable-now) states so the caller can tell the user their input is
 *    kept and to just try again.
 */
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { DailyLimitPanel } from '@/components/daily-limit-panel';
import {
  classifyLlmError,
  describeLlmError,
  isDailyLimitError,
} from '@/lib/llm-error';

export interface LlmErrorStateProps {
  /** The caught error from an LLM-bound call (a typed `ApiError`, or anything else). */
  error: unknown;
  /**
   * A short reassurance shown only for the transient states (rate-limited / server-busy), e.g.
   * "Your words are kept — press Generate to try again." Omitted → no hint paragraph.
   */
  transientHint?: string;
}

/** Render the right friendly state for a failed LLM-bound call (never a raw error). */
export function LlmErrorState({ error, transientHint }: LlmErrorStateProps) {
  if (isDailyLimitError(error)) {
    return <DailyLimitPanel error={error} />;
  }

  const { title, description } = describeLlmError(error);
  const kind = classifyLlmError(error);
  const transient = kind === 'rate_limited' || kind === 'server_busy';

  return (
    <Card role="alert" className="border-destructive/50">
      <CardHeader>
        <CardTitle className="text-lg">{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      {transient && transientHint !== undefined && (
        <CardContent>
          <p className="text-sm text-muted-foreground">{transientHint}</p>
        </CardContent>
      )}
    </Card>
  );
}
