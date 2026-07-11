/**
 * HelpTip — a small inline help affordance that explains an adjacent option in one short line.
 *
 * An info-icon button that opens the explanation in a Popover on click / tap / Enter (so it works on
 * touch and keyboard), plus a native `title` for a plain mouse-hover tooltip. Reuses the existing
 * Popover primitive — no new dependency. Sits next to the vowel-marks checkbox (add-language form)
 * and the vowel-marks toggle (study screens).
 */
import { Info } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from '@/components/ui/popover';

/** Shared copy for the vowel-marks help tip, so every call site stays in sync. */
export const VOWEL_MARKS_HELP =
  'Optional pronunciation guides — beginners keep them on, fluent readers turn them off.';

export interface HelpTipProps {
  /** One short line explaining the adjacent option. Also the native hover title. */
  text: string;
  /** Accessible name for the trigger, e.g. "About vowel marks". */
  label?: string;
}

export function HelpTip({ text, label = 'More information' }: HelpTipProps) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          // Sits inside <form>s — must never submit them.
          type="button"
          variant="ghost"
          size="icon"
          className="h-6 w-6 text-muted-foreground"
          aria-label={label}
          title={text}
        >
          <Info aria-hidden="true" className="h-4 w-4" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        role="note"
        className="w-64 p-3 text-footnote text-muted-foreground"
      >
        {text}
      </PopoverContent>
    </Popover>
  );
}
