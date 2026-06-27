/**
 * Log-in screen (task 4.3.2): email + password via supabase-js, with friendly error states for bad
 * credentials and an unverified email (which offers a resend link), a "forgot password?" link, and
 * the Google/Apple OAuth buttons.
 *
 * On success this form does NOT navigate itself — establishing the session flips the auth context,
 * and the `RedirectIfAuthed` guard wrapping this route sends the user into the app (preserving any
 * originally-requested location). That keeps a single redirect path for password, OAuth, and
 * already-signed-in visits alike.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { FormField } from '@/components/form-field';
import { OAuthButtons } from '@/components/oauth-buttons';
import { AuthCard } from '@/components/auth-card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { resendVerificationEmail, signInWithEmail } from '@/lib/auth';

export default function Login() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unverified, setUnverified] = useState(false);
  const [resendState, setResendState] = useState<
    'idle' | 'sending' | 'sent' | 'error'
  >('idle');

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    setUnverified(false);
    setResendState('idle');
    setSubmitting(true);
    const result = await signInWithEmail(email, password);
    setSubmitting(false);
    if (result.error !== null) {
      setError(result.error);
      setUnverified(result.code === 'email_not_confirmed');
    }
  }

  async function handleResend() {
    setResendState('sending');
    const result = await resendVerificationEmail(email);
    setResendState(result.error === null ? 'sent' : 'error');
  }

  return (
    <AuthCard title="Log in" description="Welcome back to Lengua.">
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <FormField
          id="email"
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          required
        />
        <div className="space-y-1.5">
          <div className="flex items-center justify-between">
            <label htmlFor="password" className="text-sm font-medium">
              Password
            </label>
            <Link
              to="/forgot-password"
              className="text-sm font-medium underline underline-offset-4"
            >
              Forgot password?
            </Link>
          </div>
          <Input
            id="password"
            type="password"
            autoComplete="current-password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </div>

        {error !== null && (
          <div role="alert" className="space-y-2 text-sm text-destructive">
            <p>{error}</p>
            {unverified && resendState !== 'sent' && (
              <Button
                type="button"
                variant="link"
                className="h-auto p-0 text-sm"
                onClick={() => void handleResend()}
                disabled={resendState === 'sending'}
              >
                {resendState === 'sending'
                  ? 'Sending…'
                  : 'Resend verification email'}
              </Button>
            )}
            {resendState === 'sent' && (
              <p className="text-muted-foreground">
                Verification email sent — check your inbox.
              </p>
            )}
            {resendState === 'error' && (
              <p>Could not resend the email. Please try again shortly.</p>
            )}
          </div>
        )}

        <Button type="submit" className="w-full" disabled={submitting}>
          {submitting ? 'Logging in…' : 'Log in'}
        </Button>
      </form>

      <div className="mt-4">
        <OAuthButtons disabled={submitting} />
      </div>

      <p className="mt-6 text-center text-sm text-muted-foreground">
        Need an account?{' '}
        <Link to="/signup" className="font-medium underline underline-offset-4">
          Sign up
        </Link>
      </p>
    </AuthCard>
  );
}
