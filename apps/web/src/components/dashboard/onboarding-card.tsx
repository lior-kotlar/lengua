/**
 * Dashboard fresh-user onboarding card (Apple redesign PR4, spec §5.6).
 *
 * When the user has no languages yet, the whole home screen below the h1 collapses to this single
 * card: a welcome title, the three-step path (add a language → generate → review), and one filled
 * "Add a language" pill (same accessible name the Review empty state uses). Carries the pinned
 * `data-testid="empty-state"` so the fresh-user surface stays assertable.
 */
import { Link } from 'react-router-dom';

import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

const STEPS: string[] = [
  'Add a language',
  'Generate sentences from your words',
  'Review them as flashcards',
];

/** The first-run three-step onboarding card. */
export function OnboardingCard() {
  return (
    <Card data-testid="empty-state" className="p-6 sm:p-8">
      <div className="space-y-1">
        <h2 className="text-title2">Welcome to Lengua</h2>
        <p className="text-subhead text-muted-foreground">
          Three steps to your first review.
        </p>
      </div>
      <ol className="mt-6 divide-y">
        {STEPS.map((step, index) => (
          <li key={step} className="flex items-center gap-3 py-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/15 text-caption font-semibold tabular-nums text-primary">
              {index + 1}
            </span>
            <span className="text-body">{step}</span>
          </li>
        ))}
      </ol>
      <div className="mt-6">
        <Button asChild>
          <Link to="/languages">Add a language</Link>
        </Button>
      </div>
    </Card>
  );
}
