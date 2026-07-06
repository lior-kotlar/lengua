/**
 * The site footer: links to the published Privacy policy and Support pages (task 8.1.2), shown on
 * every web surface — the authenticated app shell, the auth screens, and the public static pages —
 * so the store-required legal/support URLs are always one click away.
 *
 * Uses plain links inside the `<footer>` (contentinfo) landmark rather than a nested `<nav>`, so it
 * never adds a second navigation landmark (the app keeps exactly one `nav[aria-label="Primary"]`).
 */
import { Link } from 'react-router-dom';

import { cn } from '@/lib/utils';

const LINK_CLASS =
  'rounded-sm underline-offset-4 transition-colors hover:text-foreground hover:underline ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 ' +
  'focus-visible:ring-offset-background';

export function Footer({ className }: { className?: string }) {
  return (
    <footer
      className={cn('border-t px-4 py-6 sm:px-6', className)}
      data-testid="site-footer"
    >
      <div className="mx-auto flex max-w-4xl flex-col items-center gap-2 text-footnote text-muted-foreground sm:flex-row sm:justify-between">
        <p>© Lengua</p>
        <div className="flex items-center gap-5">
          <Link to="/privacy" className={LINK_CLASS}>
            Privacy
          </Link>
          <Link to="/support" className={LINK_CLASS}>
            Support
          </Link>
        </div>
      </div>
    </footer>
  );
}
