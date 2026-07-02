/**
 * Shared loading state (group 4.10.1) — a content skeleton with an accessible status.
 *
 * The single loading placeholder every data screen (Generate / Review / Discover) renders while its
 * query is in flight, replacing the bespoke per-screen spinner lines so the loading affordance is
 * consistent. It renders a few pulsing {@link Skeleton} bars (so the layout doesn't jump) inside a
 * `role="status"` region, and carries a visually-hidden `label` so screen-reader users hear what is
 * loading (the label is also matchable in tests).
 */
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

export interface LoadingStateProps {
  /** Accessible label announced to assistive tech (rendered visually-hidden). */
  label?: string;
  className?: string;
}

/** A skeleton placeholder with an accessible, screen-reader-only label. */
export function LoadingState({
  label = 'Loading…',
  className,
}: LoadingStateProps) {
  return (
    <div
      role="status"
      aria-busy="true"
      data-testid="loading-skeleton"
      className={cn(
        'space-y-3 rounded-lg border bg-card p-5 shadow-card',
        className,
      )}
    >
      <span className="sr-only">{label}</span>
      <Skeleton className="h-5 w-1/3" aria-hidden="true" />
      <Skeleton className="h-4 w-full" aria-hidden="true" />
      <Skeleton className="h-4 w-full" aria-hidden="true" />
      <Skeleton className="h-4 w-2/3" aria-hidden="true" />
    </div>
  );
}
