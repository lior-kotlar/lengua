/**
 * Reset-with-token screen (task 4.3.4): the landing page for the password-recovery email link.
 *
 * supabase-js (with `detectSessionInUrl`) consumes the recovery token in the URL and establishes a
 * transient session, after which `updateUser({ password })` sets the new password. If the link is
 * expired/invalid, GoTrue reports it via the redirect URL — we surface that with a path back to
 * requesting a fresh link. This route is intentionally NOT behind `RedirectIfAuthed` so the
 * recovery session doesn't bounce the user away before they can set a new password.
 */
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { AuthCard } from '@/components/auth-card';
import { FormField } from '@/components/form-field';
import { Button } from '@/components/ui/button';
import { readAuthRedirectError, updatePassword } from '@/lib/auth';
import {
  isValid,
  validateCredentials,
  type CredentialErrors,
} from '@/lib/auth-validation';

export default function ResetPassword() {
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [fieldErrors, setFieldErrors] = useState<CredentialErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  // Computed once: did the recovery link itself come back with an error (expired / invalid)?
  const [linkError] = useState(() => readAuthRedirectError());

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setError(null);
    const errors = validateCredentials({ password, confirmPassword });
    setFieldErrors(errors);
    if (!isValid(errors)) {
      return;
    }

    setSubmitting(true);
    const result = await updatePassword(password);
    setSubmitting(false);
    if (result.error !== null) {
      setError(result.error);
      return;
    }
    setDone(true);
  }

  if (linkError !== null) {
    return (
      <AuthCard title="Link expired">
        <div className="space-y-4 text-body">
          <p>
            {linkError.description ??
              'This password-reset link is invalid or has expired.'}
          </p>
          <p>
            <Link
              to="/forgot-password"
              className="font-medium text-primary underline-offset-4 hover:underline"
            >
              Request a new reset link
            </Link>
          </p>
        </div>
      </AuthCard>
    );
  }

  if (done) {
    return (
      <AuthCard title="Password updated">
        <div className="space-y-4 text-body">
          <p>Your password has been changed. You&apos;re all set.</p>
          <Button asChild className="h-11 w-full">
            <Link to="/">Continue to Lengua</Link>
          </Button>
        </div>
      </AuthCard>
    );
  }

  return (
    <AuthCard title="Set a new password">
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        <FormField
          id="password"
          label="New password"
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
          label="Confirm new password"
          type="password"
          autoComplete="new-password"
          value={confirmPassword}
          onChange={(event) => setConfirmPassword(event.target.value)}
          error={fieldErrors.confirmPassword}
          className="h-11"
          required
        />

        {error !== null && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}

        <Button type="submit" className="h-11 w-full" disabled={submitting}>
          {submitting ? 'Saving…' : 'Update password'}
        </Button>
      </form>
    </AuthCard>
  );
}
