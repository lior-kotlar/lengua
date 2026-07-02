/**
 * CEFR level panel (tasks 4.4.4 + 4.4.5) — the sidebar level widget, ported from the legacy
 * Streamlit `_render_level`.
 *
 * For the active language it shows the current CEFR band, a coloured progress bar toward the next
 * band (red / orange / blue / green over a neutral track, by tier), and a manual override select.
 * The level is read from `GET /proficiency/{language_id}`; the override `PUT`s a new band and
 * invalidates the proficiency query so the panel re-renders at the new level (which also re-levels
 * future generation on the backend).
 */
import { Loader2 } from 'lucide-react';

import { useActiveLanguage } from '@/components/active-language-context';
import { toast } from '@/components/ui/use-toast';
import {
  CEFR_BANDS,
  cefrBandColor,
  nextBand,
  progressPercent,
} from '@/lib/cefr';
import { useProficiencyQuery, useSetProficiencyBand } from '@/lib/proficiency';
import { cn } from '@/lib/utils';

export function CefrPanel() {
  const { activeLanguageId, activeLanguage } = useActiveLanguage();

  if (activeLanguageId === null) {
    return (
      <section aria-label="Proficiency level" className="px-3 py-2">
        <p className="text-footnote text-muted-foreground">
          Add a language to track your level.
        </p>
      </section>
    );
  }

  return (
    <CefrLevel
      languageId={activeLanguageId}
      languageName={activeLanguage?.name ?? ''}
    />
  );
}

interface CefrLevelProps {
  languageId: number;
  languageName: string;
}

function CefrLevel({ languageId, languageName }: CefrLevelProps) {
  const { data, isLoading, isError } = useProficiencyQuery(languageId);
  const setBand = useSetProficiencyBand(languageId);

  function handleOverride(band: string) {
    setBand.mutate(band, {
      onError: () => {
        toast({
          variant: 'destructive',
          title: 'Could not update level',
          description: 'Please try again.',
        });
      },
    });
  }

  return (
    <section
      aria-label="Proficiency level"
      className="space-y-2 rounded-lg border bg-card p-3 shadow-card"
    >
      <div className="flex items-center justify-between">
        <h2 className="text-caption uppercase text-muted-foreground">Level</h2>
        {languageName !== '' && (
          <span className="max-w-[8rem] truncate text-footnote text-muted-foreground">
            {languageName}
          </span>
        )}
      </div>

      {isLoading && (
        <p
          className="flex items-center gap-2 text-subhead text-muted-foreground"
          aria-busy="true"
        >
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          Loading level…
        </p>
      )}

      {isError && (
        <p role="alert" className="text-subhead text-hig-red-deep">
          Couldn&apos;t load your level.
        </p>
      )}

      {data !== undefined && (
        <>
          <BandProgress band={data.band} progress={data.progress} />

          <div className="space-y-1.5 pt-1">
            <label
              htmlFor="cefr-override"
              className="text-footnote font-medium text-muted-foreground"
            >
              Override level
            </label>
            <select
              id="cefr-override"
              value={data.band}
              disabled={setBand.isPending}
              onChange={(event) => handleOverride(event.target.value)}
              className="select-chevron h-9 w-full rounded-md border border-input bg-card px-3 pr-8 text-body transition-[border-color,box-shadow] duration-150 focus-visible:border-primary/60 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-primary/25 disabled:opacity-50"
            >
              {CEFR_BANDS.map((band) => (
                <option key={band} value={band}>
                  {band}
                </option>
              ))}
            </select>
            <p className="text-footnote text-muted-foreground">
              Auto-adjusts as you review; override it if it&apos;s off.
            </p>
          </div>
        </>
      )}
    </section>
  );
}

interface BandProgressProps {
  band: string;
  progress: number;
}

function BandProgress({ band, progress }: BandProgressProps) {
  const percent = progressPercent(progress);
  const upcoming = nextBand(band);

  return (
    <div className="space-y-1">
      <div className="flex items-baseline justify-between">
        <span data-testid="cefr-band" className="text-title2 font-bold">
          {band}
        </span>
        <span className="text-subhead tabular-nums text-muted-foreground">
          {percent}%
        </span>
      </div>
      <div
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={
          upcoming !== null ? `Progress to ${upcoming}` : 'Top level reached'
        }
        className="h-1.5 w-full overflow-hidden rounded-full bg-muted"
      >
        <div
          className={cn('h-full rounded-full', cefrBandColor(band))}
          style={{ width: `${percent}%` }}
        />
      </div>
      <p className="text-footnote text-muted-foreground">
        {upcoming !== null ? `Progress to ${upcoming}` : 'Top level (C2)'}
      </p>
    </div>
  );
}
