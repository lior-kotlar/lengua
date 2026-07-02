/**
 * Account screen (group 4.8) — profile, data export, sign out, and account deletion.
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
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
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
    <section className="mx-auto max-w-2xl space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Account</h1>
        <p className="text-sm text-muted-foreground">
          Manage your profile, export your data, or delete your account.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Profile</CardTitle>
          <CardDescription>The account you are signed in with.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1">
            <p className="text-sm font-medium">Email</p>
            <p
              className="text-sm text-muted-foreground"
              data-testid="account-email"
            >
              {user?.email ?? 'Not signed in'}
            </p>
          </div>
          <Button
            variant="outline"
            onClick={() => void handleSignOut()}
            disabled={signingOut}
          >
            <LogOut className="h-4 w-4" aria-hidden="true" />
            {signingOut ? 'Signing out…' : 'Sign out'}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Export your data</CardTitle>
          <CardDescription>
            Download everything in your account — languages, flashcards, review
            history, and progress — as a JSON file.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button onClick={handleExport} disabled={exportAccount.isPending}>
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
        </CardContent>
      </Card>

      <Card className="border-destructive/50">
        <CardHeader>
          <CardTitle>Delete account</CardTitle>
          <CardDescription>
            Permanently delete your account and all of your data. This cannot be
            undone.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <DeleteAccountDialog />
        </CardContent>
      </Card>
    </section>
  );
}
