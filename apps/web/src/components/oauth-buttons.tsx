/**
 * Google + Apple OAuth buttons (task 4.3.5), shared by the log-in and sign-up screens.
 *
 * Each enabled button calls `supabase.auth.signInWithOAuth` (via `signInWithProvider`) with the web
 * origin redirect, which navigates the browser to the provider. Live OAuth credentials are
 * OWNER-ONLY (Google client id/secret; Apple needs a paid Developer account) — see
 * `infra/supabase/oauth-setup.md`. Until they are wired:
 *  - if the provider isn't enabled (via `VITE_OAUTH_PROVIDERS`), the button renders disabled with a
 *    small "coming soon" note;
 *  - if it is enabled but the backend provider is unconfigured, the click surfaces a friendly inline
 *    error instead of a raw GoTrue failure.
 * The committed default enables ONLY Google (`enabledProviders()` → `['google']`). Apple is left out
 * on purpose: Supabase has `external.apple=false`, so a real "Continue with Apple" navigation would
 * leave the app and dead-end the user on a raw GoTrue 400 page (no in-app error branch can fire once
 * the browser has navigated away). With Google-only, Apple instead renders DISABLED with the "(soon)"
 * treatment. To re-enable Apple per environment once it's actually configured in Supabase, set
 * `VITE_OAUTH_PROVIDERS=google,apple` (the override accepts any comma-separated subset, or empty to
 * hide all OAuth buttons).
 */
import { useState } from 'react';
import type { Provider } from '@supabase/supabase-js';

import { Button } from '@/components/ui/button';
import { signInWithProvider } from '@/lib/auth';
import { cn } from '@/lib/utils';

interface ProviderConfig {
  id: Provider;
  label: string;
  icon: React.ReactNode;
}

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" aria-hidden="true" className="h-4 w-4">
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.76h3.56c2.08-1.92 3.28-4.74 3.28-8.09Z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.56-2.76c-.98.66-2.23 1.06-3.72 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A11 11 0 0 0 12 23Z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.11a6.6 6.6 0 0 1 0-4.22V7.05H2.18a11 11 0 0 0 0 9.9l3.66-2.84Z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1A11 11 0 0 0 2.18 7.05l3.66 2.84C6.71 7.31 9.14 5.38 12 5.38Z"
      />
    </svg>
  );
}

function AppleIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden="true"
      className="h-4 w-4 fill-current"
    >
      <path d="M16.37 12.78c.03 2.9 2.55 3.86 2.58 3.87-.02.07-.4 1.38-1.33 2.73-.8 1.17-1.63 2.33-2.94 2.36-1.29.02-1.7-.76-3.18-.76-1.47 0-1.93.74-3.15.78-1.26.05-2.22-1.26-3.03-2.43-1.65-2.4-2.91-6.77-1.22-9.72.84-1.47 2.35-2.4 3.98-2.42 1.24-.03 2.42.84 3.18.84.76 0 2.19-1.03 3.69-.88.63.03 2.4.25 3.53 1.92-.09.06-2.11 1.24-2.09 3.7M13.9 4.6c.67-.81 1.12-1.94.99-3.06-.96.04-2.13.64-2.82 1.45-.62.72-1.17 1.87-1.02 2.97 1.07.08 2.17-.55 2.85-1.36" />
    </svg>
  );
}

const PROVIDERS: ProviderConfig[] = [
  { id: 'google', label: 'Google', icon: <GoogleIcon /> },
  { id: 'apple', label: 'Apple', icon: <AppleIcon /> },
];

/** Providers enabled for this build (default: Google only). Override via `VITE_OAUTH_PROVIDERS`. */
function enabledProviders(): ReadonlySet<string> {
  const raw = import.meta.env.VITE_OAUTH_PROVIDERS;
  if (raw === undefined) {
    // Google-only by default: Apple isn't configured in Supabase (external.apple=false), so a real
    // Apple sign-in would dead-end on a raw 400 — it stays disabled "(soon)" until an env re-enables
    // it via VITE_OAUTH_PROVIDERS=google,apple.
    return new Set(['google']);
  }
  return new Set(
    raw
      .split(',')
      .map((value) => value.trim().toLowerCase())
      .filter((value) => value !== ''),
  );
}

export interface OAuthButtonsProps {
  /** Disable the buttons (e.g. while the email form is submitting). */
  disabled?: boolean;
}

export function OAuthButtons({ disabled = false }: OAuthButtonsProps) {
  const [pending, setPending] = useState<Provider | null>(null);
  const [error, setError] = useState<string | null>(null);
  const enabled = enabledProviders();

  async function handleClick(provider: Provider) {
    setError(null);
    setPending(provider);
    const result = await signInWithProvider(provider);
    if (result.error !== null) {
      // On success the browser is already navigating to the provider; only failures land here.
      setError(result.error);
      setPending(null);
    }
  }

  return (
    <div className="space-y-3">
      <div className="relative">
        <div className="absolute inset-0 flex items-center">
          <span className="w-full border-t" />
        </div>
        <div className="relative flex justify-center text-xs uppercase">
          <span className="bg-background px-2 text-muted-foreground">
            Or continue with
          </span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        {PROVIDERS.map((provider) => {
          const isEnabled = enabled.has(provider.id);
          return (
            <Button
              key={provider.id}
              type="button"
              variant="outline"
              aria-label={`Continue with ${provider.label}`}
              disabled={!isEnabled || disabled || pending !== null}
              onClick={
                isEnabled ? () => void handleClick(provider.id) : undefined
              }
              className={cn('w-full', !isEnabled && 'opacity-70')}
            >
              {provider.icon}
              <span>{provider.label}</span>
              {!isEnabled && (
                <span className="text-xs text-muted-foreground">(soon)</span>
              )}
            </Button>
          );
        })}
      </div>

      {error !== null && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}
