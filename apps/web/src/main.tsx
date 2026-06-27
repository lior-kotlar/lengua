import { StrictMode, Suspense, lazy } from 'react';
import { createRoot } from 'react-dom/client';
import { QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';

import App from '@/App';
import { AnalyticsConsentBanner } from '@/components/analytics-consent-banner';
import { AnalyticsConsentProvider } from '@/components/analytics-consent-provider';
import { AuthProvider } from '@/components/auth-provider';
import { DebugErrorButton } from '@/components/debug-error-button';
import { ThemeProvider } from '@/components/theme-provider';
import { Toaster } from '@/components/ui/toaster';
import { initErrorTracking } from '@/lib/error-tracking';
import { registerPostHogAnalytics } from '@/lib/posthog';
import { createQueryClient } from '@/lib/query-client';
import '@/index.css';
// Self-hosted diacritic-correct fonts for the complex scripts (group 4.9.2). Bundled by Vite (no
// runtime CDN — mobile-webview-safe): Noto Naskh Arabic positions harakat, Noto Sans Hebrew positions
// nikkud. Only the script subset of each is imported; `font-arabic` / `font-hebrew` (tailwind.config)
// select them for the matching language regions.
import '@fontsource/noto-naskh-arabic/arabic-400.css';
import '@fontsource/noto-naskh-arabic/arabic-700.css';
import '@fontsource/noto-sans-hebrew/hebrew-400.css';
import '@fontsource/noto-sans-hebrew/hebrew-700.css';

// Initialise Sentry error tracking before render so early errors are captured. A no-op unless
// VITE_SENTRY_DSN_WEB is set (dev/CI/E2E load nothing, zero egress) — see lib/error-tracking.
initErrorTracking();

// Register the PostHog analytics adapter behind the consent seam. This wires the loader only;
// posthog-js is lazily imported and nothing loads/sends until the user opts in AND VITE_POSTHOG_KEY
// is configured (so dev/CI/E2E with no key load nothing) — see lib/posthog + lib/analytics.
registerPostHogAnalytics();

const queryClient = createQueryClient();

// Devtools are dev-only: in a production build `import.meta.env.DEV` is false, so the dynamic
// import lives in dead code and is tree-shaken out of the bundle entirely.
const ReactQueryDevtools = import.meta.env.DEV
  ? lazy(() =>
      import('@tanstack/react-query-devtools').then((m) => ({
        default: m.ReactQueryDevtools,
      })),
    )
  : null;

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <AnalyticsConsentProvider>
          <BrowserRouter>
            <AuthProvider>
              <App />
            </AuthProvider>
          </BrowserRouter>
          <Toaster />
          {/* First-run analytics-consent banner (4.10.3): app-global, outside the route tree, so it
              shows on first load regardless of auth state and never reappears after a decision. */}
          <AnalyticsConsentBanner />
          {/* Hidden Sentry debug-error trigger (5.4.2): renders null unless VITE_ENABLE_DEBUG_TOOLS
              is set, so it never appears in a production build. */}
          <DebugErrorButton />
          {ReactQueryDevtools && (
            <Suspense fallback={null}>
              <ReactQueryDevtools initialIsOpen={false} />
            </Suspense>
          )}
        </AnalyticsConsentProvider>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
);
