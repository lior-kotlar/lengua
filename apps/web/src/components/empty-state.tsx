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

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
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
      className={cn(tone === 'success' && 'border-green-500/50', className)}
    >
      <CardHeader>
        <div className="flex items-center gap-2">
          {Icon !== undefined && (
            <Icon
              className={cn(
                'h-5 w-5 shrink-0',
                tone === 'success' ? 'text-green-500' : 'text-muted-foreground',
              )}
              aria-hidden="true"
            />
          )}
          <CardTitle className="text-lg">{title}</CardTitle>
        </div>
        {description !== undefined && (
          <CardDescription>{description}</CardDescription>
        )}
      </CardHeader>
      {children !== undefined && (
        <CardContent className="flex flex-wrap items-center gap-3">
          {children}
        </CardContent>
      )}
    </Card>
  );
}
