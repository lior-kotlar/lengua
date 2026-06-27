/**
 * Delete-account confirm dialog (task 4.8.3) — the irreversible account hard-delete.
 *
 * Deletion is permanent (the backend hard-deletes the Supabase auth user, which cascades away ALL
 * of the user's data), so this is guarded to make an accidental delete impossible:
 *
 *  - The trigger only OPENS the dialog; deletion is never fired from it.
 *  - The confirm button stays DISABLED until the user types the exact {@link DELETE_CONFIRM_PHRASE}.
 *  - Confirming calls `DELETE /account` EXACTLY ONCE (the button + the submit handler both gate on
 *    "confirmed and not already in flight"), then tears down the local session: sign out (clears the
 *    Supabase session), clear the TanStack Query cache, and redirect to `/login`.
 *  - A partial-failure **502** is surfaced as a friendly, retryable message with the dialog left open
 *    (nothing was deleted server-side, so retrying is safe).
 *
 * Closing the dialog resets the typed phrase and any error, so a stale confirmation can never linger.
 * The session token is never logged.
 */
import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Trash2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { apiErrorMessage } from '@/lib/api-client';
import { DELETE_CONFIRM_PHRASE, useDeleteAccount } from '@/lib/account';
import { signOut } from '@/lib/auth';

export function DeleteAccountDialog() {
  const [open, setOpen] = useState(false);
  const [phrase, setPhrase] = useState('');
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const deleteAccount = useDeleteAccount();

  // Exact match (after trimming surrounding whitespace) — the single gate on firing deletion.
  const confirmed = phrase.trim() === DELETE_CONFIRM_PHRASE;

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) {
      // Reset on close so reopening starts clean and no stale confirmation/error remains.
      setPhrase('');
      deleteAccount.reset();
    }
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    // Defense in depth: never delete unless the phrase matches and no delete is already in flight,
    // even if a submit somehow fires while the button is disabled.
    if (!confirmed || deleteAccount.isPending) {
      return;
    }
    deleteAccount.mutate(undefined, {
      onSuccess: async () => {
        // The irreversible step succeeded. Tear down the local session + cached data, then redirect.
        await signOut();
        queryClient.clear();
        navigate('/login', { replace: true });
      },
    });
  }

  const error = deleteAccount.isError ? deleteAccount.error : null;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant="destructive">
          <Trash2 className="h-4 w-4" aria-hidden="true" />
          Delete account
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete your account?</DialogTitle>
          <DialogDescription>
            This permanently deletes your account and all of your data —
            languages, flashcards, review history, and progress — on every
            device. This cannot be undone.
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-3" noValidate>
          <div className="space-y-1.5">
            <label htmlFor="delete-confirm" className="text-sm font-medium">
              Type{' '}
              <span className="font-mono font-semibold">
                {DELETE_CONFIRM_PHRASE}
              </span>{' '}
              to confirm
            </label>
            <Input
              id="delete-confirm"
              value={phrase}
              onChange={(event) => setPhrase(event.target.value)}
              disabled={deleteAccount.isPending}
              autoComplete="off"
              autoCapitalize="none"
              spellCheck={false}
              aria-describedby={error !== null ? 'delete-error' : undefined}
            />
            {error !== null && (
              <p
                id="delete-error"
                role="alert"
                className="text-sm text-destructive"
              >
                {apiErrorMessage(
                  error,
                  'Account deletion failed. Please try again.',
                )}
              </p>
            )}
          </div>

          <DialogFooter>
            <DialogClose asChild>
              <Button
                type="button"
                variant="outline"
                disabled={deleteAccount.isPending}
              >
                Cancel
              </Button>
            </DialogClose>
            <Button
              type="submit"
              variant="destructive"
              disabled={!confirmed || deleteAccount.isPending}
            >
              {deleteAccount.isPending ? 'Deleting…' : 'Delete account'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
