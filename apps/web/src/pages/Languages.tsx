/**
 * Languages management screen (tasks 4.4.2 + 4.4.3) — the React port of the legacy "Manage
 * languages" sidebar section, restyled to the Apple grouped-list grammar (redesign PR5).
 *
 * Two columns on wide screens — the languages list + the add-language form — stacking on mobile.
 * The list is the active-language context's `GET /languages` cache the header picker shares, so a
 * create/remove here reflects everywhere; a freshly added language is also made active. Tapping a
 * row's name sets it active; each row carries a confirm-gated {@link RemoveLanguageDialog}.
 */
import { AddLanguageForm } from '@/components/add-language-form';
import { useActiveLanguage } from '@/components/active-language-context';
import { EmptyState } from '@/components/empty-state';
import { ErrorState } from '@/components/error-state';
import { LoadingState } from '@/components/loading-state';
import { RemoveLanguageDialog } from '@/components/remove-language-dialog';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import type { LanguageOut } from '@/lib/languages';

/** Two-letter avatar initials — the language code when set, otherwise its name. */
function languageInitials(language: LanguageOut): string {
  const source =
    language.code !== null && language.code.trim() !== ''
      ? language.code
      : language.name;
  return source.replace(/\s+/g, '').slice(0, 2).toUpperCase();
}

export default function Languages() {
  const {
    languages,
    activeLanguageId,
    setActiveLanguageId,
    isLoading,
    isError,
    refetch,
  } = useActiveLanguage();

  return (
    <section className="mx-auto max-w-5xl space-y-8">
      <div className="space-y-1">
        <h1 className="text-large-title">Languages</h1>
        <p className="text-subhead text-muted-foreground">
          Add or remove languages. Pick the active one from the header.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr,380px]">
        <div className="space-y-3">
          <h2 className="text-caption uppercase text-muted-foreground">
            Your languages
          </h2>

          {isLoading ? (
            <LoadingState label="Loading languages…" />
          ) : isError ? (
            <ErrorState
              title="Couldn't load your languages"
              description="Something went wrong loading your languages. Please refresh."
              onRetry={refetch}
            />
          ) : languages.length === 0 ? (
            <EmptyState
              title="No languages yet"
              description="You haven't added any languages yet. Add your first one to get started."
            />
          ) : (
            <ul className="divide-y overflow-hidden rounded-lg border bg-card shadow-card">
              {languages.map((language) => {
                const isActive = language.id === activeLanguageId;
                const hasCode = language.code !== null && language.code !== '';
                return (
                  <li
                    key={language.id}
                    className="flex h-14 items-center gap-3 px-5"
                  >
                    <button
                      type="button"
                      onClick={() => setActiveLanguageId(language.id)}
                      className="flex min-w-0 flex-1 items-center gap-3 text-left transition-opacity duration-150 hover:opacity-80"
                    >
                      <span
                        aria-hidden="true"
                        className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-secondary text-caption font-semibold text-muted-foreground"
                      >
                        {languageInitials(language)}
                      </span>
                      <span className="flex min-w-0 items-center gap-2">
                        <span className="truncate text-headline">
                          {language.name}
                        </span>
                        {hasCode && (
                          <span className="shrink-0 rounded bg-secondary px-1.5 text-caption uppercase text-muted-foreground">
                            {language.code}
                          </span>
                        )}
                        {isActive && (
                          <span className="shrink-0 rounded-full bg-primary/15 px-2 py-0.5 text-caption font-semibold text-hig-blue-deep">
                            Active
                          </span>
                        )}
                      </span>
                    </button>
                    <RemoveLanguageDialog language={language} />
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <Card className="h-fit">
          <CardHeader>
            <CardTitle>Add a language</CardTitle>
            <CardDescription>
              Choose a starting level — it adapts automatically as you review.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <AddLanguageForm
              onCreated={(language) => setActiveLanguageId(language.id)}
            />
          </CardContent>
        </Card>
      </div>
    </section>
  );
}
