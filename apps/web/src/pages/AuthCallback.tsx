/**
 * Auth callback / email-verification landing route (task 4.3.3).
 *
 * Both the email-verification link and the OAuth round-trip redirect here. supabase-js (with
 * `detectSessionInUrl`) consumes the token from the URL and establishes the session, which flips the
 * auth context — so on success we simply route the user into the app. If verification failed (an
 * error came back in the redirect, or no session could be established) we surface a resend action.
 */
import { useState } from 'react';
import { Loader2 } from 'lucide-react';
import { Link, Navigate } from 'react-router-dom';

import { useAuth } from '@/components/auth-context';
import { AuthCard } from '@/components/auth-card';
import { FormField } from '@/components/form-field';
import { Button } from '@/components/ui/button';
import { readAuthRedirectError, resendVerificationEmail } from '@/lib/auth';
import { validateEmail } from '@/lib/auth-validation';

export default function AuthCallback() {
  const { session, loading } = useAuth();
  const [linkError] = useState(() => readAuthRedirectError());

  const [email, setEmail] = useState('');
  const [emailError, setEmailError] = useState<string | null>(null);
  const [resendState, setResendState] = useState<
    'idle' | 'sending' | 'sent' | 'error'
  >('idle');

  // Success: the verification/OAuth redirect established a session → into the app.
  if (session !== null) {
    return <Navigate to="/" replace />;
  }

  // Still consuming the token from the URL.
  if (loading && linkError === null) {
    return (
      <div
        role="status"
        aria-label="Verifying"
        className="flex flex-col items-center gap-3 py-8 text-center text-sm text-muted-foreground"
      >
        <Loader2 className="h-6 w-6 animate-spin" />
        <p>Verifying your email…</p>
      </div>
    );
  }

  async function handleResend(event: React.FormEvent) {
    event.preventDefault();
    const validationError = validateEmail(email);
    setEmailError(validationError);
    if (validationError !== null) {
      return;
    }
    setResendState('sending');
    const result = await resendVerificationEmail(email);
    setResendState(result.error === null ? 'sent' : 'error');
  }

  // Failure: no session established (link expired/invalid, or already used) → offer a resend.
  return (
    <AuthCard title="Verification failed">
      <div className="space-y-4">
        <p className="text-sm text-muted-foreground">
          {linkError?.description ??
            "We couldn't verify your email. The link may have expired or already been used. Enter your email to get a new verification link."}
        </p>

        {resendState === 'sent' ? (
          <p className="text-sm">
            Verification email sent — check your inbox, then{' '}
            <Link
              to="/login"
              className="font-medium underline underline-offset-4"
            >
              log in
            </Link>
            .
          </p>
        ) : (
          <form onSubmit={handleResend} className="space-y-4" noValidate>
            <FormField
              id="email"
              label="Email"
              type="email"
              autoComplete="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              error={emailError}
              required
            />
            {resendState === 'error' && (
              <p role="alert" className="text-sm text-destructive">
                Could not resend the email. Please try again shortly.
              </p>
            )}
            <Button
              type="submit"
              className="w-full"
              disabled={resendState === 'sending'}
            >
              {resendState === 'sending'
                ? 'Sending…'
                : 'Resend verification email'}
            </Button>
          </form>
        )}
      </div>
    </AuthCard>
  );
}
