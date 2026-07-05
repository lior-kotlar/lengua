/**
 * First-run analytics-consent banner (group 4.10.3).
 *
 * Shows once, on first load, while the user has not yet decided about product analytics. Choosing
 * Accept opts in (and boots analytics via the provider); Decline opts out. Either choice is
 * persisted, so the banner never reappears after a decision (it renders `null` once `decision` is
 * set). It is rendered app-globally (outside the route tree), so it appears regardless of auth state
 * and stays out of the screens' own layout.
 */
import { useAnalyticsConsent } from '@/components/analytics-consent-context';
import { Button } from '@/components/ui/button';

export function AnalyticsConsentBanner() {
  const { decision, grant, deny } = useAnalyticsConsent();

  // Decided already (this load or a previous one) → never prompt again.
  if (decision !== null) {
    return null;
  }

  return (
    <div
      role="region"
      aria-label="Analytics consent"
      data-testid="analytics-consent"
      // Below `sm` the app shell pins a 49px tab bar to the bottom edge; the banner sits above it
      // so it never covers Primary navigation. (On tab-bar-less screens it floats a little high —
      // harmless for a one-shot prompt.)
      className="fixed inset-x-0 bottom-[calc(49px+env(safe-area-inset-bottom))] z-50 border-t bg-background p-4 shadow-lg sm:bottom-0"
    >
      <div className="mx-auto flex max-w-3xl flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-subhead text-muted-foreground">
          Lengua can use privacy-friendly product analytics to understand how
          the app is used and improve it. Nothing is collected until you opt in,
          and you can change your mind any time.
        </p>
        <div className="flex shrink-0 items-center gap-2">
          <Button variant="outline" size="sm" onClick={deny}>
            Decline
          </Button>
          <Button size="sm" onClick={grant}>
            Accept
          </Button>
        </div>
      </div>
    </div>
  );
}
