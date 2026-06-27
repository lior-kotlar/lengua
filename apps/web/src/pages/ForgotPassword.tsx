/**
 * Request-password-reset screen (task 4.3.4): enter an email; supabase-js sends a reset link that
 * lands on the reset-with-token screen. We always show the same confirmation on success regardless
 * of whether the address exists (avoids account enumeration — GoTrue behaves the same way).
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { AuthCard } from '@/components/auth-card';
import { FormField } from '@/components/form-field';
import { Button } from '@/components/ui/button';
import { requestPasswordReset } from '@/lib/auth';
import { validateEmail } from '@/lib/auth-validation';

export default function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [emailError, setEmailError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sent, setSent] = useState(false);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    const validationError = validateEmail(email);
    setEmailError(validationError);
    if (validationError !== null) {
      return;
    }

    setSubmitting(true);
    const result = await requestPasswordReset(email);
    setSubmitting(false);
    if (result.error !== null) {
      setError(result.error);
      return;
    }
    setSent(true);
  }

  if (sent) {
    return (
      <AuthCard title="Check your email">
        <div className="space-y-4 text-sm">
          <p>
            If an account exists for{' '}
            <span className="font-medium">{email}</span>, we&apos;ve sent a
            password-reset link. Follow it to choose a new password.
          </p>
          <p>
            <Link
              to="/login"
              className="font-medium underline underline-offset-4"
            >
              Back to log in
            </Link>
          </p>
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard
      title="Reset password"
      description="Enter your email and we'll send you a reset link."
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
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

        {error !== null && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}

        <Button type="submit" className="w-full" disabled={submitting}>
          {submitting ? 'Sending…' : 'Send reset link'}
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-muted-foreground">
        Remembered it?{' '}
        <Link to="/login" className="font-medium underline underline-offset-4">
          Log in
        </Link>
      </p>
    </AuthCard>
  );
}
