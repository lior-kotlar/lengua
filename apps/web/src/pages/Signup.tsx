/**
 * Sign-up screen (task 4.3.1): email + password (+ confirm) via supabase-js, with client-side
 * validation mirroring the server password policy and a "check your email to verify" confirmation
 * state on success. Google/Apple OAuth buttons are offered as an alternative.
 */
import { useState } from 'react';
import { MailCheck } from 'lucide-react';
import { Link } from 'react-router-dom';

import { AuthCard } from '@/components/auth-card';
import { FormField } from '@/components/form-field';
import { OAuthButtons } from '@/components/oauth-buttons';
import { Button } from '@/components/ui/button';
import { trackSignup } from '@/lib/analytics-events';
import { signUpWithEmail } from '@/lib/auth';
import {
  isValid,
  validateCredentials,
  type CredentialErrors,
} from '@/lib/auth-validation';

export default function Signup() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [fieldErrors, setFieldErrors] = useState<CredentialErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submittedEmail, setSubmittedEmail] = useState<string | null>(null);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    const errors = validateCredentials({ email, password, confirmPassword });
    setFieldErrors(errors);
    if (!isValid(errors)) {
      return;
    }

    setSubmitting(true);
    const result = await signUpWithEmail(email, password);
    setSubmitting(false);
    if (result.error !== null) {
      setError(result.error);
      return;
    }
    // Activation-funnel event (5.9.2): consent-gated, no PII (just the sign-up method).
    trackSignup('email');
    // Email confirmation is required, so a successful sign-up leaves the user unauthenticated until
    // they click the verification link. Show the confirmation notice.
    setSubmittedEmail(email);
  }

  if (submittedEmail !== null) {
    return (
      <AuthCard title="Check your email">
        <div className="space-y-4 text-body">
          <MailCheck className="h-10 w-10 text-primary" aria-hidden="true" />
          <p>
            We sent a verification link to{' '}
            <span className="font-medium">{submittedEmail}</span>. Click it to
            activate your account, then come back to log in.
          </p>
          <p className="text-muted-foreground">
            Didn&apos;t get it? Check your spam folder, or{' '}
            <Link
              to="/login"
              className="font-medium text-primary underline-offset-4 hover:underline"
            >
              return to log in
            </Link>{' '}
            to resend it.
          </p>
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard title="Sign up" description="Start learning with Lengua.">
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <FormField
          id="email"
          label="Email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          error={fieldErrors.email}
          className="h-11"
          required
        />
        <FormField
          id="password"
          label="Password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          error={fieldErrors.password}
          className="h-11"
          required
        />
        <FormField
          id="confirm-password"
          label="Confirm password"
          type="password"
          autoComplete="new-password"
          value={confirmPassword}
          onChange={(event) => setConfirmPassword(event.target.value)}
          error={fieldErrors.confirmPassword}
          className="h-11"
          required
        />

        {error !== null && (
          <p role="alert" className="text-footnote text-destructive">
            {error}
          </p>
        )}

        <Button type="submit" className="h-11 w-full" disabled={submitting}>
          {submitting ? 'Creating account…' : 'Create account'}
        </Button>
      </form>

      <div className="mt-4">
        <OAuthButtons disabled={submitting} />
      </div>

      <p className="mt-6 text-center text-subhead text-muted-foreground">
        Already have an account?{' '}
        <Link
          to="/login"
          className="font-medium text-primary underline-offset-4 hover:underline"
        >
          Log in
        </Link>
      </p>
    </AuthCard>
  );
}
