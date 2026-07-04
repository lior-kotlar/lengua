import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/button';

/**
 * 404 route — rendered outside BOTH the app shell and the auth shell (it is the catch-all `*`). Uses
 * the shared EmptyState grammar (a centered card on the grouped background with a soft radial wash)
 * fronted by a tinted 404 numeral and a filled pill back to the Dashboard. Title/description are
 * non-heading <p>s (EmptyState convention), so this terminal page adds no stray heading.
 */
export default function NotFound() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-background bg-[radial-gradient(60%_50%_at_50%_0%,hsl(var(--primary)/0.06),transparent)] bg-fixed p-6 text-foreground">
      <div className="flex w-full max-w-[400px] flex-col items-center rounded-lg border bg-card px-6 py-10 text-center text-card-foreground shadow-card">
        <p className="text-[3.5rem] font-bold leading-none tracking-[-0.03em] text-hig-blue-deep tabular-nums">
          404
        </p>
        <p className="mt-4 text-headline">Page not found</p>
        <p className="mt-1 max-w-sm text-subhead text-muted-foreground">
          The page you requested could not be found.
        </p>
        <Button asChild className="mt-6">
          <Link to="/">Dashboard</Link>
        </Button>
      </div>
    </div>
  );
}
