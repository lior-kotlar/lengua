/**
 * Account screen (group 4.8) — profile, data export, sign out, and account deletion, restyled to
 * the Apple grouped-list grammar (redesign PR5).
 *
 * Ports the legacy Streamlit account controls onto the Phase 2 endpoints:
 *  - Profile: the signed-in email (read from the auth context) + a sign-out action.
 *  - Data export (4.8.2): `GET /account/export` → download the bundle as a JSON file.
 *  - Delete account (4.8.3): the confirm-typed {@link DeleteAccountDialog} (irreversible hard-delete).
 *
 * Export + delete derive the user solely from the JWT (no user-id is ever sent), so they can only
 * ever act on the caller's own account.
 */
import { useState } from 'react';
import { Download, Loader2, LogOut } from 'lucide-react';

import { useAuth } from '@/components/auth-context';
import { DeleteAccountDialog } from '@/components/delete-account-dialog';
import { Button } from '@/components/ui/button';
import { toast } from '@/components/ui/use-toast';
import {
  ACCOUNT_EXPORT_FILENAME,
  downloadJson,
  useExportAccount,
} from '@/lib/account';
import { apiErrorMessage } from '@/lib/api-client';
import { signOut } from '@/lib/auth';

export default function Account() {
  const { user } = useAuth();
  const [signingOut, setSigningOut] = useState(false);
  const exportAccount = useExportAccount();

  async function handleSignOut() {
    setSigningOut(true);
    try {
      // The SIGNED_OUT event drives the cache reset + redirect to /login (AuthProvider + guards).
      await signOut();
    } finally {
      setSigningOut(false);
    }
  }

  function handleExport() {
    exportAccount.mutate(undefined, {
      onSuccess: (data) => {
        downloadJson(ACCOUNT_EXPORT_FILENAME, data);
        toast({
          title: 'Export ready',
          description: 'Your data was downloaded as a JSON file.',
        });
      },
      onError: (error) => {
        toast({
          variant: 'destructive',
          title: 'Could not export your data',
          description: apiErrorMessage(error, 'Please try again.'),
        });
      },
    });
  }

  return (
    <section className="mx-auto max-w-2xl space-y-8">
      <div className="space-y-1">
        <h1 className="text-large-title">Account</h1>
        <p className="text-subhead text-muted-foreground">
          Manage your profile, export your data, or delete your account.
        </p>
      </div>

      {/* Profile — a grouped list (Email) with the page-level Sign out below it. */}
      <div className="space-y-3">
        <p className="text-caption uppercase text-muted-foreground">Profile</p>
        <div className="overflow-hidden rounded-lg border bg-card shadow-card">
          <div className="flex items-center justify-between gap-4 px-5 py-4">
            <p className="shrink-0 text-body font-medium">Email</p>
            <p
              className="min-w-0 truncate text-right text-subhead text-muted-foreground"
              data-testid="account-email"
            >
              {user?.email ?? 'Not signed in'}
            </p>
          </div>
        </div>
        <Button
          variant="outline"
          onClick={() => void handleSignOut()}
          disabled={signingOut}
        >
          <LogOut className="h-4 w-4" aria-hidden="true" />
          {signingOut ? 'Signing out…' : 'Sign out'}
        </Button>
      </div>

      {/* Data export */}
      <div className="space-y-3">
        <p className="text-caption uppercase text-muted-foreground">
          Your data
        </p>
        <div className="space-y-3 rounded-lg border bg-card p-5 shadow-card">
          <div className="space-y-1">
            <p className="text-body font-medium">Export your data</p>
            <p className="text-subhead text-muted-foreground">
              Download everything in your account — languages, flashcards,
              review history, and progress — as a JSON file.
            </p>
          </div>
          <Button
            variant="outline"
            onClick={handleExport}
            disabled={exportAccount.isPending}
          >
            {exportAccount.isPending ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                Preparing…
              </>
            ) : (
              <>
                <Download className="h-4 w-4" aria-hidden="true" />
                Export my data
              </>
            )}
          </Button>
        </div>
      </div>

      {/* Danger zone — tinted-red frame; the Delete trigger is tinted destructive, its dialog
          confirm the solid destructive (both wired inside DeleteAccountDialog). */}
      <div className="space-y-3 rounded-lg border border-hig-red/25 bg-card p-5 shadow-card">
        <p className="text-caption uppercase text-hig-red-deep">Danger zone</p>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="min-w-0 space-y-1">
            <p className="text-body font-medium">Delete account</p>
            <p className="text-subhead text-muted-foreground">
              Permanently delete your account and all of your data. This cannot
              be undone.
            </p>
          </div>
          <DeleteAccountDialog />
        </div>
      </div>
    </section>
  );
}
