/**
 * Dashboard "Quick actions" (Apple redesign PR4, spec §5.4) — two shortcut cards to the generative
 * halves of the loop (Generate / Discover) for when nothing is due but the user wants to add more.
 * Both are plain links (scoped away from the Primary nav, so nav-scoped e2e queries stay unambiguous).
 */
import { Compass, Sparkles } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { Link } from 'react-router-dom';

interface QuickAction {
  to: string;
  label: string;
  description: string;
  icon: LucideIcon;
}

const QUICK_ACTIONS: QuickAction[] = [
  {
    to: '/generate',
    label: 'Generate',
    description: 'Turn your words into sentences',
    icon: Sparkles,
  },
  {
    to: '/discover',
    label: 'Discover',
    description: 'Let Lengua pick new words',
    icon: Compass,
  },
];

/** The two quick-action shortcut cards. */
export function QuickActions() {
  return (
    <section
      aria-label="Quick actions"
      className="grid max-w-md grid-cols-2 gap-4"
    >
      {QUICK_ACTIONS.map((action) => (
        <Link
          key={action.to}
          to={action.to}
          className="flex items-center gap-3 rounded-lg border bg-card p-4 shadow-card transition-all [transition-duration:250ms] ease-apple hover:-translate-y-px hover:shadow-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
        >
          <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary/15 text-primary">
            <action.icon className="h-5 w-5" aria-hidden="true" />
          </span>
          <span className="min-w-0">
            <span className="block text-headline">{action.label}</span>
            <span className="block truncate text-subhead text-muted-foreground">
              {action.description}
            </span>
          </span>
        </Link>
      ))}
    </section>
  );
}
