/**
 * Public account-deletion form (`/delete-account`, task 8.3.1) — the external deletion path Google
 * Play requires, usable WITHOUT signing in. Two modes:
 *
 *  - **Request** (no `?token`): submit your account email → `POST /account/deletion-request`. The
 *    server always answers the same generic acknowledgement (it never discloses whether the email is
 *    registered) and, if an account exists, emails a confirmation link.
 *  - **Confirm** (`?token=…` from that emailed link): `POST /account/deletion-confirm` runs the same
 *    permanent, cascading delete as the in-app flow.
 *
 * Rendered in the {@link StaticLayout}, so it works with no session and no `VITE_*` beyond the API
 * base URL (the API client is lazy and attaches no auth header when there is no session).
 */
import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { apiErrorMessage, getApiClient, unwrap } from '@/lib/api-client';

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-md space-y-6">
      <div className="space-y-2">
        <h1 className="text-large-title">Delete your account</h1>
        <p className="text-subhead text-muted-foreground">
          Permanently delete your Lengua account and all of your data. This
          cannot be undone.
        </p>
      </div>
      <div className="space-y-4 rounded-lg border bg-card p-6 shadow-card">
        {children}
      </div>
      <p className="text-center text-footnote text-muted-foreground">
        You can also delete your account from <em>Account → Delete account</em>{' '}
        inside the app. See our{' '}
        <Link to="/privacy" className="text-primary hover:underline">
          Privacy Policy
        </Link>
        .
      </p>
    </div>
  );
}

function RequestForm() {
  const [email, setEmail] = useState('');
  const request = useMutation({
    mutationFn: (address: string) =>
      unwrap(
        getApiClient().POST('/account/deletion-request', {
          body: { email: address },
        }),
      ),
  });

  if (request.isSuccess) {
    return (
      <Shell>
        <p role="status" className="text-body">
          {request.data.message}
        </p>
      </Shell>
    );
  }

  return (
    <Shell>
      <form
        className="space-y-4"
        onSubmit={(event) => {
          event.preventDefault();
          if (email.trim()) request.mutate(email.trim());
        }}
      >
        <div className="space-y-1.5">
          <label htmlFor="delete-email" className="text-subhead font-medium">
            Account email
          </label>
          <Input
            id="delete-email"
            type="email"
            autoComplete="email"
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@example.com"
          />
          <p className="text-footnote text-muted-foreground">
            We'll email a link to confirm and complete the deletion.
          </p>
        </div>
        {request.isError && (
          <p role="alert" className="text-subhead text-hig-red-deep">
            {apiErrorMessage(
              request.error,
              'Something went wrong. Please try again.',
            )}
          </p>
        )}
        <Button
          type="submit"
          variant="destructiveSolid"
          className="w-full"
          disabled={!email.trim() || request.isPending}
        >
          {request.isPending ? 'Sending…' : 'Request account deletion'}
        </Button>
      </form>
    </Shell>
  );
}

function ConfirmForm({ token }: { token: string }) {
  const confirm = useMutation({
    mutationFn: () =>
      unwrap(
        getApiClient().POST('/account/deletion-confirm', { body: { token } }),
      ),
  });

  if (confirm.isSuccess) {
    return (
      <Shell>
        <p role="status" className="text-body">
          {confirm.data.message}
        </p>
      </Shell>
    );
  }

  return (
    <Shell>
      <p className="text-body text-muted-foreground">
        Confirm that you want to permanently delete this account and all of its
        data. This action cannot be undone.
      </p>
      {confirm.isError && (
        <p role="alert" className="text-subhead text-hig-red-deep">
          {apiErrorMessage(
            confirm.error,
            'This link may be invalid or expired.',
          )}
        </p>
      )}
      <Button
        type="button"
        variant="destructiveSolid"
        className="w-full"
        disabled={confirm.isPending}
        onClick={() => confirm.mutate()}
      >
        {confirm.isPending ? 'Deleting…' : 'Delete my account permanently'}
      </Button>
    </Shell>
  );
}

export default function DeleteAccount() {
  const [params] = useSearchParams();
  const token = params.get('token');
  return token ? <ConfirmForm token={token} /> : <RequestForm />;
}
