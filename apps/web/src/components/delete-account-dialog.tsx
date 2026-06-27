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
import { useRef, useState } from 'react';
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
import { signOutLocal } from '@/lib/auth';

export function DeleteAccountDialog() {
  const [open, setOpen] = useState(false);
  const [phrase, setPhrase] = useState('');
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const deleteAccount = useDeleteAccount();
  // Synchronous in-flight latch: makes exactly-once independent of React render timing, so two
  // submit events in the SAME tick (synthetic/automation) can't both fire the irreversible DELETE.
  const inFlight = useRef(false);

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
    // even if a submit somehow fires while the button is disabled. `inFlight` guards the same-tick
    // case that `isPending` (render-time) can't.
    if (!confirmed || deleteAccount.isPending || inFlight.current) {
      return;
    }
    inFlight.current = true;
    deleteAccount.mutate(undefined, {
      onSuccess: async () => {
        // The irreversible step succeeded — the account is now gone server-side. Tear down the LOCAL
        // session (no network logout: it would fail on the deleted user and could leave the session
        // intact, which RedirectIfAuthed would bounce back into the app). A failed local sign-out
        // must NOT block teardown, so swallow it and always clear the cache + redirect.
        await signOutLocal().catch(() => undefined);
        queryClient.clear();
        navigate('/login', { replace: true });
      },
      onSettled: () => {
        // Release the latch so a failed (502) delete can be retried; harmless on success (unmounted).
        inFlight.current = false;
      },
    });
  }

  const error = deleteAccount.isError ? deleteAccount.error : null;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        // Don't let an Escape/overlay dismissal interrupt an in-flight delete: the irreversible call
        // is already on the wire, and closing would reset the mutation and silently drop a 502.
        if (deleteAccount.isPending) {
          return;
        }
        handleOpenChange(next);
      }}
    >
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
