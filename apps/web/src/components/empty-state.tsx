/**
 * Shared empty state (group 4.10.1) — a friendly "there is nothing here yet" card.
 *
 * The single empty-data affordance the data screens render when a query succeeds but has no content
 * to show (no languages yet, an empty due batch, no suggested words), so the messaging and styling
 * stay consistent. An optional `icon` is the lightweight illustration; `children` carry the call to
 * action (e.g. a link to add a language or generate). `tone="success"` is the celebratory variant
 * used for the "all caught up" review state (green accent).
 */
import type { LucideIcon } from 'lucide-react';

import { Card } from '@/components/ui/card';
import { cn } from '@/lib/utils';

export interface EmptyStateProps {
  /** Optional illustration icon shown next to the title. */
  icon?: LucideIcon;
  title: string;
  description?: string;
  /** Optional action(s) — typically a button or link. */
  children?: React.ReactNode;
  /** Visual tone: neutral `default`, or the celebratory `success` (green accent). */
  tone?: 'default' | 'success';
  className?: string;
}

/** A neutral (or celebratory) empty-data card with an optional icon + action. */
export function EmptyState({
  icon: Icon,
  title,
  description,
  children,
  tone = 'default',
  className,
}: EmptyStateProps) {
  return (
    <Card
      data-testid="empty-state"
      className={cn(
        'flex flex-col items-center px-6 py-10 text-center',
        className,
      )}
    >
      {Icon !== undefined && (
        <div
          className={cn(
            'mb-4 flex h-10 w-10 shrink-0 items-center justify-center rounded-full',
            tone === 'success' ? 'bg-hig-green/15' : 'bg-secondary',
          )}
        >
          <Icon
            className={cn(
              'h-5 w-5',
              tone === 'success'
                ? 'text-hig-green-deep'
                : 'text-muted-foreground',
            )}
            aria-hidden="true"
          />
        </div>
      )}
      <p className="text-headline">{title}</p>
      {description !== undefined && (
        <p className="mt-1 max-w-sm text-subhead text-muted-foreground">
          {description}
        </p>
      )}
      {children !== undefined && (
        <div className="mt-5 flex flex-wrap items-center justify-center gap-3">
          {children}
        </div>
      )}
    </Card>
  );
}
