/**
 * Shared error state (group 4.10.1) — a retryable error card.
 *
 * The single failure affordance the data screens render when a query errors (the languages list, the
 * due batch). It is an `role="alert"` card with a friendly title + description and, when an `onRetry`
 * handler is supplied, a "Try again" button that re-runs the failed query — so a transient network
 * blip is one click to recover from, consistently across screens.
 *
 * This is for GENERIC query failures. LLM-bound calls (`/generate`, `/discover`) classify their
 * cost-guard errors through {@link import('@/components/llm-error-state').LlmErrorState} instead (the
 * friendly quota-429 / rate-limit / server-busy states), so those never surface as this raw error.
 */
import { RotateCcw } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

export interface ErrorStateProps {
  title?: string;
  description?: string;
  /** Retry handler. When provided, renders a "Try again" button that calls it. */
  onRetry?: () => void;
  /** Label for the retry button. */
  retryLabel?: string;
  className?: string;
}

/** A retryable error card for a failed query. */
export function ErrorState({
  title = 'Something went wrong',
  description = 'Please try again.',
  onRetry,
  retryLabel = 'Try again',
  className,
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      data-testid="error-state"
      className={cn(
        'space-y-3 rounded-lg border border-hig-red/25 bg-hig-red/[0.06] p-5',
        className,
      )}
    >
      <div className="space-y-1">
        <p className="text-body font-semibold">{title}</p>
        <p className="text-subhead text-muted-foreground">{description}</p>
      </div>
      {onRetry !== undefined && (
        <Button variant="destructive" size="sm" onClick={onRetry}>
          <RotateCcw className="h-4 w-4" aria-hidden="true" />
          {retryLabel}
        </Button>
      )}
    </div>
  );
}
