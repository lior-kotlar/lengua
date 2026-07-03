/**
 * Experimental "word of the day" card — ships DARK behind the `word_of_the_day` feature flag (6.9.2).
 *
 * Renders nothing unless the flag resolves on (via {@link useFeatureFlag}, which fails safe to off),
 * so the surface is genuinely absent in the prod build until an operator flips the flag — no web
 * redeploy. This is the UI half of the dark-launch; the API half is the flag-gated
 * `GET /experimental/word-of-the-day` route (404 until the flag is on).
 */
import { useFeatureFlag, WORD_OF_THE_DAY_FLAG } from '@/lib/feature-flags';

export function WordOfTheDay() {
  const enabled = useFeatureFlag(WORD_OF_THE_DAY_FLAG);
  if (!enabled) {
    return null;
  }
  return (
    <section
      aria-labelledby="word-of-the-day-heading"
      className="space-y-1 rounded-lg border bg-card p-5 text-card-foreground shadow-card"
    >
      <h2 id="word-of-the-day-heading" className="text-headline">
        Word of the day
      </h2>
      <p className="text-subhead text-muted-foreground">
        Experimental preview — the full “word of the day” feature is coming
        soon.
      </p>
    </section>
  );
}
