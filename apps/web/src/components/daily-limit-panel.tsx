/**
 * Shared "daily limit reached" panel — the dedicated, reusable 429 quota state (groups 4.5 + 4.7 +
 * 4.10.2).
 *
 * The LLM cost guard refuses an LLM-bound call once the per-user daily cap (`daily_cap_reached`) or
 * the global daily kill-switch (`daily_limit_reached`) is hit. That is a FRIENDLY, expected state —
 * not an error — so every LLM-bound screen (Generate, Discover, and any future one) renders THIS one
 * component instead of a generic error, keeping the messaging and styling consistent and the 429 UI
 * in a single place (group 4.10.2 asserts the sharing). It is tied to the quota-429 response shape
 * via {@link isDailyLimitError}.
 *
 * The copy adapts to WHICH limit was hit (rather than always saying "generation"): the global
 * kill-switch reads as an everyone-affecting pause, and the per-user cap names the offending action
 * (generating / discovering) from the response body's `kind`. Anything we cannot pin down falls back
 * to kind-agnostic copy, so a Discover or kill-switch 429 is never mislabelled as a generation limit.
 */
import { CalendarClock } from 'lucide-react';

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { isApiError } from '@/lib/api-client';
import { isDailyLimitError } from '@/lib/llm-error';
import { cn } from '@/lib/utils';

export interface DailyLimitPanelProps {
  /**
   * The caught error. When provided, the panel renders ONLY if it is the quota-429 daily-limit
   * shape, so it can sit next to a generic-error branch without double-gating; when omitted the
   * caller has already decided to show it. It is also what the copy is keyed off (see
   * {@link limitScope}).
   */
  error?: unknown;
  className?: string;
}

/** Which flavour of the daily-limit copy to show. */
type LimitScope = 'generate' | 'discover' | 'global' | 'default';

/**
 * Classify a daily-limit error into the copy variant it should render.
 *
 * The two cost-guard 429 shapes differ in WHAT is exhausted:
 *  - the global kill-switch (`daily_limit_reached`) caps the whole app for everyone → `global`;
 *  - the per-user cap (`daily_cap_reached`) caps one action for one user and carries the offending
 *    `kind` (`generate` / `discover` / …) in its body → that kind.
 *
 * Anything we cannot pin down — a caller-pre-gated render with no `error`, an unrecognised `kind`
 * (e.g. tap-a-word `explain`), or a non-API value — falls back to kind-agnostic `default` copy.
 */
function limitScope(error: unknown): LimitScope {
  if (!isApiError(error)) {
    return 'default';
  }
  if (error.code === 'daily_limit_reached') {
    return 'global';
  }
  const kind =
    error.body !== null && typeof error.body === 'object'
      ? (error.body as { kind?: unknown }).kind
      : undefined;
  if (kind === 'generate' || kind === 'discover') {
    return kind;
  }
  return 'default';
}

/**
 * Per-scope copy. The title is always "Daily limit reached"; only the one-line description and the
 * reassurance paragraph vary. Every description ends with "try again tomorrow", and none assumes a
 * particular screen unless the scope is known.
 */
const LIMIT_COPY: Record<LimitScope, { description: string; body: string }> = {
  generate: {
    description:
      'You have reached your daily limit for generating sentences. Please try again tomorrow.',
    body: 'This keeps the app affordable while it is in early access. Your typed words are kept, so you can come back tomorrow and pick up where you left off.',
  },
  discover: {
    description:
      'You have reached your daily limit for discovering words. Please try again tomorrow.',
    body: 'This keeps the app affordable while it is in early access. Come back tomorrow to discover more words.',
  },
  global: {
    description:
      'The app has reached its daily limit for everyone. Please try again tomorrow.',
    body: 'This keeps the app affordable while it is in early access. Your work is saved, so you can come back tomorrow and pick up where you left off.',
  },
  default: {
    description: 'You have reached the daily limit. Please try again tomorrow.',
    body: 'This keeps the app affordable while it is in early access. Your work is saved, so you can come back tomorrow and pick up where you left off.',
  },
};

/**
 * Render the daily-limit panel for the quota-429 shape.
 *
 * Returns `null` when an `error` is supplied that is NOT a daily-limit error (so it is inert for
 * other failures), and renders the friendly panel otherwise. A `role="status"` live region means
 * screen-reader users hear it when the call is refused.
 */
export function DailyLimitPanel({ error, className }: DailyLimitPanelProps) {
  if (error !== undefined && !isDailyLimitError(error)) {
    return null;
  }

  const { description, body } = LIMIT_COPY[limitScope(error)];

  return (
    <Card
      role="status"
      data-testid="daily-limit-panel"
      className={cn('border-amber-500/50', className)}
    >
      <CardHeader>
        <div className="flex items-center gap-2">
          <CalendarClock
            className="h-5 w-5 shrink-0 text-amber-500"
            aria-hidden="true"
          />
          <CardTitle className="text-lg">Daily limit reached</CardTitle>
        </div>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">{body}</p>
      </CardContent>
    </Card>
  );
}
