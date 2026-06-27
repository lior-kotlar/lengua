/**
 * Shared "daily limit reached" panel — the dedicated, reusable 429 quota state (groups 4.5 + 4.7 +
 * 4.10.2).
 *
 * The LLM cost guard refuses generation once the per-user daily cap (`daily_cap_reached`) or the
 * global daily kill-switch (`daily_limit_reached`) is hit. That is a FRIENDLY, expected state — not
 * an error — so every LLM-bound screen (Generate, Discover, and any future one) renders THIS one
 * component instead of a generic error, keeping the messaging and styling consistent and the 429 UI
 * in a single place (group 4.10.2 asserts the sharing). It is tied to the quota-429 response shape
 * via {@link isDailyLimitError}.
 */
import { CalendarClock } from 'lucide-react';

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { isDailyLimitError } from '@/lib/llm-error';
import { cn } from '@/lib/utils';

export interface DailyLimitPanelProps {
  /**
   * The caught error. When provided, the panel renders ONLY if it is the quota-429 daily-limit
   * shape, so it can sit next to a generic-error branch without double-gating; when omitted the
   * caller has already decided to show it.
   */
  error?: unknown;
  className?: string;
}

/**
 * Render the daily-limit panel for the quota-429 shape.
 *
 * Returns `null` when an `error` is supplied that is NOT a daily-limit error (so it is inert for
 * other failures), and renders the friendly panel otherwise. A `role="status"` live region means
 * screen-reader users hear it when generation is refused.
 */
export function DailyLimitPanel({ error, className }: DailyLimitPanelProps) {
  if (error !== undefined && !isDailyLimitError(error)) {
    return null;
  }

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
        <CardDescription>
          You have reached the daily generation limit. Please try again
          tomorrow.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">
          This keeps the app affordable while it is in early access. Your typed
          words are kept, so you can come back tomorrow and pick up where you
          left off.
        </p>
      </CardContent>
    </Card>
  );
}
