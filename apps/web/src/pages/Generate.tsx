/**
 * Generate screen (group 4.5) — the React port of the legacy Streamlit "generate" page.
 *
 * Flow: paste vocabulary words for the ACTIVE language -> `POST /generate` builds an example
 * sentence (recognition + production card pair) for each -> review them grouped back into
 * sentences -> select which to keep (all by default) -> `POST /cards/save` persists the chosen
 * ones. Generation is slow and quota-bounded, so the in-progress state and the friendly 429
 * daily-limit state (the shared {@link DailyLimitPanel}) are first-class here; other cost-guard
 * states (rate-limited / server-busy / verify-email) render friendly inline messages too, never a
 * raw error.
 */
import { useMemo, useState } from 'react';
import { CheckCircle2, Loader2, Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';

import { useActiveLanguage } from '@/components/active-language-context';
import { DailyLimitPanel } from '@/components/daily-limit-panel';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { toast } from '@/components/ui/use-toast';
import { apiErrorMessage } from '@/lib/api-client';
import {
  cardsForSentences,
  groupSentences,
  parseWords,
  useGenerate,
  useSaveCards,
  WORDS_PER_REQUEST_CAP,
  type GeneratedCard,
  type GeneratedSentence,
} from '@/lib/generate';
import {
  classifyLlmError,
  describeLlmError,
  isDailyLimitError,
} from '@/lib/llm-error';
import { cn } from '@/lib/utils';

export default function Generate() {
  const { activeLanguageId, activeLanguage, isLoading } = useActiveLanguage();

  return (
    <section className="mx-auto max-w-2xl space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Generate</h1>
        <p className="text-sm text-muted-foreground">
          Paste vocabulary words and generate natural example sentences
          {activeLanguage !== null ? ` in ${activeLanguage.name}` : ''}.
        </p>
      </div>

      {isLoading ? (
        <p
          className="flex items-center gap-2 text-sm text-muted-foreground"
          aria-busy="true"
        >
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          Loading your languages…
        </p>
      ) : activeLanguageId === null ? (
        <Card>
          <CardHeader>
            <CardTitle className="text-lg">Add a language first</CardTitle>
            <CardDescription>
              You need a language before you can generate sentences.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild>
              <Link to="/languages">Add a language</Link>
            </Button>
          </CardContent>
        </Card>
      ) : (
        // Re-mount the workspace per language so its draft/results never leak across a switch.
        <GenerateWorkspace
          key={activeLanguageId}
          languageId={activeLanguageId}
        />
      )}
    </section>
  );
}

/** The generate -> review -> save workflow for a known (non-null) active language. */
function GenerateWorkspace({ languageId }: { languageId: number }) {
  const [rawWords, setRawWords] = useState('');
  const [sentences, setSentences] = useState<GeneratedSentence[] | null>(null);
  const [savedCount, setSavedCount] = useState<number | null>(null);

  const generate = useGenerate();
  const save = useSaveCards();

  const words = useMemo(() => parseWords(rawWords), [rawWords]);
  const overCap = words.length > WORDS_PER_REQUEST_CAP;
  const canGenerate = words.length > 0 && !overCap && !generate.isPending;

  function handleGenerate(event: React.FormEvent) {
    event.preventDefault();
    if (words.length === 0 || overCap) {
      return;
    }
    // Re-running clears any prior saved confirmation / stale save error.
    setSavedCount(null);
    save.reset();
    generate.mutate(
      { languageId, words },
      {
        onSuccess: (cards) => {
          setSentences(groupSentences(cards));
        },
      },
    );
  }

  function handleSave(cards: GeneratedCard[]) {
    save.mutate(
      { languageId, cards },
      {
        onSuccess: (saved) => {
          setSavedCount(saved.length);
          setSentences(null);
          toast({
            title: 'Cards saved',
            description: `${saved.length} card${
              saved.length === 1 ? '' : 's'
            } added to your deck.`,
          });
        },
        onError: (error) => {
          toast({
            variant: 'destructive',
            title: 'Could not save cards',
            description: apiErrorMessage(error, 'Please try again.'),
          });
        },
      },
    );
  }

  /** Return to the word form. `clearWords` starts fresh (after a save); otherwise keeps the words. */
  function startOver(clearWords: boolean) {
    generate.reset();
    save.reset();
    setSentences(null);
    setSavedCount(null);
    if (clearWords) {
      setRawWords('');
    }
  }

  if (savedCount !== null) {
    return (
      <SavedConfirmation
        count={savedCount}
        onGenerateMore={() => startOver(true)}
      />
    );
  }

  if (sentences !== null) {
    return (
      <ResultsPanel
        sentences={sentences}
        onSave={handleSave}
        onStartOver={() => startOver(false)}
        isSaving={save.isPending}
      />
    );
  }

  return (
    <WordForm
      rawWords={rawWords}
      onRawWordsChange={setRawWords}
      words={words}
      overCap={overCap}
      canGenerate={canGenerate}
      isGenerating={generate.isPending}
      onSubmit={handleGenerate}
      error={generate.isPending ? null : (generate.error ?? null)}
    />
  );
}

interface WordFormProps {
  rawWords: string;
  onRawWordsChange: (value: string) => void;
  words: string[];
  overCap: boolean;
  canGenerate: boolean;
  isGenerating: boolean;
  onSubmit: (event: React.FormEvent) => void;
  error: unknown;
}

function WordForm({
  rawWords,
  onRawWordsChange,
  words,
  overCap,
  canGenerate,
  isGenerating,
  onSubmit,
  error,
}: WordFormProps) {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">Your words</CardTitle>
          <CardDescription>
            One word or phrase per line (or comma-separated). Up to{' '}
            {WORDS_PER_REQUEST_CAP} at a time.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4" noValidate>
            <div className="space-y-1.5">
              <label htmlFor="generate-words" className="text-sm font-medium">
                Words
              </label>
              <textarea
                id="generate-words"
                value={rawWords}
                onChange={(event) => onRawWordsChange(event.target.value)}
                disabled={isGenerating}
                rows={5}
                placeholder={'casa\nperro\nbuenos días'}
                aria-describedby="generate-words-count"
                className="flex min-h-[7rem] w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              />
              <p
                id="generate-words-count"
                className={cn(
                  'text-xs',
                  overCap ? 'text-destructive' : 'text-muted-foreground',
                )}
              >
                {words.length} / {WORDS_PER_REQUEST_CAP} words
              </p>
            </div>

            {words.length > 0 && (
              <ul className="flex flex-wrap gap-1.5" aria-label="Parsed words">
                {words.map((word, index) => (
                  <li
                    key={`${word}-${index}`}
                    className="rounded-full bg-muted px-2.5 py-0.5 text-xs text-muted-foreground"
                  >
                    {word}
                  </li>
                ))}
              </ul>
            )}

            {overCap && (
              <p role="alert" className="text-sm text-destructive">
                Too many words. Remove {words.length - WORDS_PER_REQUEST_CAP} to
                generate up to {WORDS_PER_REQUEST_CAP} at a time.
              </p>
            )}

            <div className="flex items-center gap-3">
              <Button type="submit" disabled={!canGenerate}>
                {isGenerating ? (
                  <>
                    <Loader2
                      className="h-4 w-4 animate-spin"
                      aria-hidden="true"
                    />
                    Generating…
                  </>
                ) : (
                  <>
                    <Sparkles className="h-4 w-4" aria-hidden="true" />
                    Generate
                  </>
                )}
              </Button>
              {isGenerating && (
                <span
                  className="text-sm text-muted-foreground"
                  aria-live="polite"
                >
                  Generating sentences… this can take a few seconds.
                </span>
              )}
            </div>
          </form>
        </CardContent>
      </Card>

      {error !== null && <GenerateError error={error} />}
    </div>
  );
}

/** Render the friendly state for a failed generate: the shared daily-limit panel, or an inline note. */
function GenerateError({ error }: { error: unknown }) {
  if (isDailyLimitError(error)) {
    return <DailyLimitPanel error={error} />;
  }
  const { title, description } = describeLlmError(error);
  // rate-limited / server-busy are transient; the form below is ready for an immediate retry.
  const kind = classifyLlmError(error);
  const transient = kind === 'rate_limited' || kind === 'server_busy';
  return (
    <Card role="alert" className="border-destructive/50">
      <CardHeader>
        <CardTitle className="text-lg">{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      {transient && (
        <CardContent>
          <p className="text-sm text-muted-foreground">
            Your words are kept — press Generate to try again.
          </p>
        </CardContent>
      )}
    </Card>
  );
}

interface ResultsPanelProps {
  sentences: GeneratedSentence[];
  onSave: (cards: GeneratedCard[]) => void;
  onStartOver: () => void;
  isSaving: boolean;
}

function ResultsPanel({
  sentences,
  onSave,
  onStartOver,
  isSaving,
}: ResultsPanelProps) {
  // Default to all selected (the common case is "keep them all"). Owned here so it resets whenever
  // a fresh result set mounts this panel.
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(
    () => new Set(sentences.map((sentence) => sentence.key)),
  );

  function toggle(key: string) {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }

  const selected = sentences.filter((sentence) =>
    selectedKeys.has(sentence.key),
  );
  const allSelected = selected.length === sentences.length;

  function toggleAll() {
    setSelectedKeys(
      allSelected ? new Set() : new Set(sentences.map((s) => s.key)),
    );
  }

  if (sentences.length === 0) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-lg">No sentences generated</CardTitle>
          <CardDescription>
            Nothing came back for those words. Try different ones.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button variant="outline" onClick={onStartOver}>
            Back to words
          </Button>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-lg">Review &amp; save</CardTitle>
        <CardDescription>
          Pick the sentences to add to your deck. Each becomes two flashcards
          (reading + writing).
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between border-b pb-2">
          <label className="flex items-center gap-2 text-sm font-medium">
            <input
              type="checkbox"
              checked={allSelected}
              onChange={toggleAll}
              className="h-4 w-4 rounded border-input"
              aria-label="Select all sentences"
            />
            Select all
          </label>
          <span className="text-sm text-muted-foreground">
            {selected.length} of {sentences.length} selected
          </span>
        </div>

        <ul className="space-y-3">
          {sentences.map((sentence) => {
            const checked = selectedKeys.has(sentence.key);
            return (
              <li
                key={sentence.key}
                className={cn(
                  'flex gap-3 rounded-md border p-3',
                  checked ? 'border-primary/40 bg-accent/40' : 'border-border',
                )}
              >
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={() => toggle(sentence.key)}
                  className="mt-1 h-4 w-4 shrink-0 rounded border-input"
                  aria-label={`Save this card — ${sentence.translation}`}
                />
                <div className="min-w-0 space-y-1">
                  <p className="font-medium">{sentence.sentence}</p>
                  <p className="text-sm text-muted-foreground">
                    {sentence.translation}
                  </p>
                  {sentence.usedWords.length > 0 && (
                    <ul className="flex flex-wrap gap-1.5 pt-1">
                      {sentence.usedWords.map((word, index) => (
                        <li
                          key={`${word}-${index}`}
                          className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
                        >
                          {word}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </li>
            );
          })}
        </ul>

        <div className="flex items-center gap-3">
          <Button
            onClick={() => onSave(cardsForSentences(selected))}
            disabled={selected.length === 0 || isSaving}
          >
            {isSaving ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
                Saving…
              </>
            ) : (
              `Save ${selected.length} ${
                selected.length === 1 ? 'sentence' : 'sentences'
              }`
            )}
          </Button>
          <Button variant="ghost" onClick={onStartOver} disabled={isSaving}>
            Start over
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

interface SavedConfirmationProps {
  count: number;
  onGenerateMore: () => void;
}

function SavedConfirmation({ count, onGenerateMore }: SavedConfirmationProps) {
  return (
    <Card className="border-green-500/50">
      <CardHeader>
        <div className="flex items-center gap-2">
          <CheckCircle2
            className="h-5 w-5 shrink-0 text-green-500"
            aria-hidden="true"
          />
          <CardTitle className="text-lg">
            Saved {count} {count === 1 ? 'card' : 'cards'}
          </CardTitle>
        </div>
        <CardDescription>
          They are in your deck and due for review now.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex items-center gap-3">
        <Button onClick={onGenerateMore}>Generate more</Button>
        <Button variant="outline" asChild>
          <Link to="/review">Review now</Link>
        </Button>
      </CardContent>
    </Card>
  );
}
