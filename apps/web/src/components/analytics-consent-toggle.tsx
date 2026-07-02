/**
 * Analytics consent toggle (group 5.9.1) — a Settings Card that flips product-analytics consent
 * on/off AFTER the first-run banner.
 *
 * It drives the same `useAnalyticsConsent()` seam as the banner, so turning it ON grants consent
 * (the provider boots PostHog / opts the live SDK back in) and turning it OFF denies it (the
 * provider opts the live SDK out). The choice is persisted, so it survives reloads. With no
 * `VITE_POSTHOG_KEY` configured (dev/CI/E2E) flipping it still loads/sends nothing — a clean seam.
 */
import { useAnalyticsConsent } from '@/components/analytics-consent-context';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';

export function AnalyticsConsentToggle() {
  const { decision, grant, deny } = useAnalyticsConsent();
  // Treat only an explicit grant as "on"; undecided (null) or denied are both "off".
  const enabled = decision === 'granted';

  return (
    <Card>
      <CardHeader>
        <CardTitle>Privacy &amp; analytics</CardTitle>
        <CardDescription>
          Lengua can use privacy-friendly, EU-hosted product analytics (PostHog)
          to understand how the app is used and improve it. We never collect
          your name, email, or the words you study — and you can change this any
          time.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="flex items-center justify-between gap-4">
          <div className="space-y-0.5">
            <p id="analytics-toggle-label" className="text-body font-medium">
              Share anonymous usage analytics
            </p>
            <p
              id="analytics-toggle-hint"
              className="text-footnote text-muted-foreground"
            >
              {enabled ? 'On — thank you!' : 'Off'}
            </p>
          </div>
          <Switch
            checked={enabled}
            onCheckedChange={(checked) => (checked ? grant() : deny())}
            aria-labelledby="analytics-toggle-label"
            aria-describedby="analytics-toggle-hint"
          />
        </div>
      </CardContent>
    </Card>
  );
}
