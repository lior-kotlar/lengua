/**
 * Discover screen (group 4.7) — the React port of the legacy Streamlit "discover" page.
 *
 * Flow: pick how many new words (defaulting to the user's `discover_count` setting) + an optional
 * topic → `POST /discover` previews vocabulary the learner does NOT already know → accept the set
 * (handed off into the existing Generate flow, group 4.5, so the words are reviewed + saved there —
 * the generate UI is NOT duplicated here) or reroll for a fresh set. Discover shares the quota path
 * with Generate, so the friendly cost-guard states — the shared {@link DailyLimitPanel} for the
 * daily-limit 429, and inline transient/verify states — are first-class here too (via the shared
 * {@link LlmErrorState}).
 */
import { useState } from 'react';
import { ArrowRight, Compass, Loader2 } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';

import { useActiveLanguage } from '@/components/active-language-context';
import { LanguageText } from '@/components/language-text';
import { LlmErrorState } from '@/components/llm-error-state';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { useVowelMarks } from '@/components/vowel-marks-context';
import { VowelMarksToggle } from '@/components/vowel-marks-toggle';
import {
  clampDiscoverCount,
  DISCOVER_COUNT_MAX,
  DISCOVER_COUNT_MIN,
  resolveDiscoverCount,
  useDiscover,
} from '@/lib/discover';
import { handOffWords } from '@/lib/generate-handoff';
import { directionForCode } from '@/lib/language-text';
import { fallbackLanguage, type LanguageOut } from '@/lib/languages';
import { useSettingsQuery } from '@/lib/settings';

export default function Discover() {
  const { activeLanguageId, activeLanguage, isLoading } = useActiveLanguage();
  const { showVowels } = useVowelMarks();

  return (
    <section
      dir={directionForCode(activeLanguage?.code)}
      data-testid="discover-content"
      className="mx-auto max-w-2xl space-y-6"
    >
      <div className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Discover</h1>
        <p className="text-sm text-muted-foreground">
          Lengua picks new vocabulary you have not seen yet and turns it into
          example sentences
          {activeLanguage !== null ? ` in ${activeLanguage.name}` : ''}.
        </p>
      </div>

      <VowelMarksToggle />

      {isLoading ? (
        <LoadingNote>Loading your languages…</LoadingNote>
      ) : activeLanguageId === null ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Add a language first</CardTitle>
            <CardDescription>
              You need a language before you can discover new words.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild>
              <Link to="/languages">Add a language</Link>
            </Button>
          </CardContent>
        </Card>
      ) : (
        // Re-mount per language so a switch resets the count/topic/suggestions cleanly.
        <DiscoverWorkspace
          key={activeLanguageId}
          language={activeLanguage ?? fallbackLanguage(activeLanguageId)}
          showVowels={showVowels}
        />
      )}
    </section>
  );
}

/**
 * Loads the user's settings to seed the default word count, then mounts the interactive session.
 * Gating the session on the settings load means the count input shows the user's preference from the
 * first render (no flash of the fallback default); a settings error degrades to the server default.
 */
function DiscoverWorkspace({
  language,
  showVowels,
}: {
  language: LanguageOut;
  showVowels: boolean;
}) {
  const settings = useSettingsQuery();

  if (settings.isLoading) {
    return <LoadingNote>Loading your preferences…</LoadingNote>;
  }

  return (
    <DiscoverSession
      language={language}
      showVowels={showVowels}
      initialCount={resolveDiscoverCount(settings.data)}
    />
  );
}

interface DiscoverSessionProps {
  language: LanguageOut;
  showVowels: boolean;
  initialCount: number;
}

/** The discover → preview → accept/reroll workflow for a known language + resolved default count. */
function DiscoverSession({
  language,
  showVowels,
  initialCount,
}: DiscoverSessionProps) {
  const languageId = language.id;
  const navigate = useNavigate();
  const [count, setCount] = useState(() => String(initialCount));
  const [topic, setTopic] = useState('');
  const [suggested, setSuggested] = useState<string[] | null>(null);

  const discover = useDiscover();

  // A whole number within the request bounds. Out of range → the form blocks + warns (the server
  // would otherwise 422); on submit we send the clamped value defensively.
  const countValid =
    /^\d+$/.test(count.trim()) &&
    Number(count) >= DISCOVER_COUNT_MIN &&
    Number(count) <= DISCOVER_COUNT_MAX;

  function runDiscover() {
    const topicValue = topic.trim() === '' ? null : topic.trim();
    discover.mutate(
      {
        languageId,
        count: clampDiscoverCount(Number(count)),
        topic: topicValue,
      },
      { onSuccess: (words) => setSuggested(words) },
    );
  }

  function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    if (!countValid) {
      return;
    }
    runDiscover();
  }

  /** Accept the suggested words: hand them to the Generate flow (group 4.5), don't save here. */
  function handleAccept(words: string[]) {
    handOffWords(words);
    navigate('/generate');
  }

  /** Back to the form to change the count/topic; clears the suggestions + any error. */
  function startOver() {
    setSuggested(null);
    discover.reset();
  }

  // Only surface a settled error (not the spinner-in-flight one) — and it applies to both the
  // initial discover and a reroll, so the daily-limit panel shows in either state.
  const error = discover.isPending ? null : (discover.error ?? null);

  return (
    <div className="space-y-4">
      {suggested === null ? (
        <DiscoverForm
          count={count}
          onCountChange={setCount}
          topic={topic}
          onTopicChange={setTopic}
          countValid={countValid}
          isDiscovering={discover.isPending}
          onSubmit={handleSubmit}
        />
      ) : (
        <SuggestionsPanel
          words={suggested}
          language={language}
          showVowels={showVowels}
          isRerolling={discover.isPending}
          onAccept={handleAccept}
          onReroll={runDiscover}
          onStartOver={startOver}
        />
      )}

      {error !== null && (
        <LlmErrorState
          error={error}
          transientHint="Your topic and count are kept — press Discover to try again."
        />
      )}
    </div>
  );
}

interface DiscoverFormProps {
  count: string;
  onCountChange: (value: string) => void;
  topic: string;
  onTopicChange: (value: string) => void;
  countValid: boolean;
  isDiscovering: boolean;
  onSubmit: (event: React.FormEvent) => void;
}

function DiscoverForm({
  count,
  onCountChange,
  topic,
  onTopicChange,
  countValid,
  isDiscovering,
  onSubmit,
}: DiscoverFormProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Find new words</CardTitle>
        <CardDescription>
          Lengua picks vocabulary you have not seen yet, at your current level.
          Add a topic to steer the theme, or leave it blank.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <div className="space-y-1.5">
            <label htmlFor="discover-count" className="text-sm font-medium">
              How many words
            </label>
            <Input
              id="discover-count"
              type="number"
              inputMode="numeric"
              min={DISCOVER_COUNT_MIN}
              max={DISCOVER_COUNT_MAX}
              value={count}
              onChange={(event) => onCountChange(event.target.value)}
              disabled={isDiscovering}
              className="max-w-[8rem]"
              aria-describedby="discover-count-hint"
            />
            <p
              id="discover-count-hint"
              className={
                countValid
                  ? 'text-xs text-muted-foreground'
                  : 'text-xs text-destructive'
              }
              role={countValid ? undefined : 'alert'}
            >
              Between {DISCOVER_COUNT_MIN} and {DISCOVER_COUNT_MAX} words.
            </p>
          </div>

          <div className="space-y-1.5">
            <label htmlFor="discover-topic" className="text-sm font-medium">
              Topic (optional)
            </label>
            <Input
              id="discover-topic"
              type="text"
              value={topic}
              onChange={(event) => onTopicChange(event.target.value)}
              disabled={isDiscovering}
              placeholder="e.g. food, travel, work"
            />
          </div>

          <div className="flex items-center gap-3">
            <Button type="submit" disabled={!countValid || isDiscovering}>
              {isDiscovering ? (
                <>
                  <Loader2
                    className="h-4 w-4 animate-spin"
                    aria-hidden="true"
                  />
                  Finding words…
                </>
              ) : (
                <>
                  <Compass className="h-4 w-4" aria-hidden="true" />
                  Discover
                </>
              )}
            </Button>
            {isDiscovering && (
              <span
                className="text-sm text-muted-foreground"
                aria-live="polite"
              >
                Choosing new vocabulary… this can take a few seconds.
              </span>
            )}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

interface SuggestionsPanelProps {
  words: string[];
  language: LanguageOut;
  showVowels: boolean;
  isRerolling: boolean;
  onAccept: (words: string[]) => void;
  onReroll: () => void;
  onStartOver: () => void;
}

function SuggestionsPanel({
  words,
  language,
  showVowels,
  isRerolling,
  onAccept,
  onReroll,
  onStartOver,
}: SuggestionsPanelProps) {
  if (words.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">No new words found</CardTitle>
          <CardDescription>
            Lengua could not find new vocabulary for that request. Try a
            different topic or count.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex items-center gap-3">
          <Button variant="outline" onClick={onReroll} disabled={isRerolling}>
            {isRerolling ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                Finding…
              </>
            ) : (
              'Try again'
            )}
          </Button>
          <Button variant="ghost" onClick={onStartOver} disabled={isRerolling}>
            Change topic
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Suggested words</CardTitle>
        <CardDescription>
          New vocabulary at your level. Use these to generate sentences, or try
          a different set.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <ul
          data-testid="discover-suggestions"
          aria-label="Suggested words"
          className="flex flex-wrap gap-2"
        >
          {words.map((word, index) => (
            <li
              key={`${word}-${index}`}
              className="rounded-full bg-muted px-3 py-1 text-sm"
            >
              <LanguageText
                as="span"
                text={word}
                language={language}
                showVowels={showVowels}
              />
            </li>
          ))}
        </ul>

        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={() => onAccept(words)} disabled={isRerolling}>
            Use these words
            <ArrowRight className="h-4 w-4" aria-hidden="true" />
          </Button>
          <Button variant="outline" onClick={onReroll} disabled={isRerolling}>
            {isRerolling ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                Finding…
              </>
            ) : (
              'Try different words'
            )}
          </Button>
          <Button variant="ghost" onClick={onStartOver} disabled={isRerolling}>
            Start over
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

/** A small inline "loading…" line with a spinner, used by the language + settings gates. */
function LoadingNote({ children }: { children: React.ReactNode }) {
  return (
    <p
      className="flex items-center gap-2 text-sm text-muted-foreground"
      aria-busy="true"
    >
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
      {children}
    </p>
  );
}
