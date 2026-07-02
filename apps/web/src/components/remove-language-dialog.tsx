/**
 * Remove-language confirm dialog (task 4.4.3).
 *
 * A destructive action behind an explicit confirmation: the trigger only OPENS the dialog; the
 * `DELETE /languages/{id}` mutation fires solely from the in-dialog "Remove" button, so a misclick
 * on the trigger never deletes anything. The body spells out the cascade (cards + progress are
 * deleted) since the backend removes them with the language.
 */
import { useState } from 'react';
import { Trash2 } from 'lucide-react';

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
import { toast } from '@/components/ui/use-toast';
import { isApiError } from '@/lib/api-client';
import { useRemoveLanguage, type LanguageOut } from '@/lib/languages';

export interface RemoveLanguageDialogProps {
  language: LanguageOut;
  /** Called after the language is successfully removed (e.g. to re-pick the active language). */
  onRemoved?: (language: LanguageOut) => void;
}

export function RemoveLanguageDialog({
  language,
  onRemoved,
}: RemoveLanguageDialogProps) {
  const [open, setOpen] = useState(false);
  const removeLanguage = useRemoveLanguage();

  function handleConfirm() {
    removeLanguage.mutate(language.id, {
      onSuccess: () => {
        setOpen(false);
        toast({
          title: 'Language removed',
          description: `${language.name} and its cards were deleted.`,
        });
        onRemoved?.(language);
      },
      onError: (error) => {
        toast({
          variant: 'destructive',
          title: 'Could not remove language',
          description: isApiError(error) ? error.message : 'Please try again.',
        });
      },
    });
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          aria-label={`Remove ${language.name}`}
        >
          <Trash2 className="h-4 w-4" aria-hidden="true" />
          Remove
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Remove {language.name}?</DialogTitle>
          <DialogDescription>
            This permanently deletes {language.name} along with all of its
            flashcards and your progress for it. This cannot be undone.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <DialogClose asChild>
            <Button variant="outline">Cancel</Button>
          </DialogClose>
          <Button
            variant="destructiveSolid"
            onClick={handleConfirm}
            disabled={removeLanguage.isPending}
          >
            {removeLanguage.isPending ? 'Removing…' : 'Remove'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
