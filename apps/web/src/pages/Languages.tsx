/**
 * Languages management screen (tasks 4.4.2 + 4.4.3) — the React port of the legacy "Manage
 * languages" sidebar section.
 *
 * Lists the user's languages (each with a confirm-gated remove) and an add-language form. The list
 * comes from the active-language context (the same `GET /languages` cache the header picker uses), so
 * a create/remove here is reflected everywhere; a freshly added language is also made active.
 */
import { Loader2 } from 'lucide-react';

import { useActiveLanguage } from '@/components/active-language-context';
import { AddLanguageForm } from '@/components/add-language-form';
import { RemoveLanguageDialog } from '@/components/remove-language-dialog';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';

export default function Languages() {
  const {
    languages,
    activeLanguageId,
    setActiveLanguageId,
    isLoading,
    isError,
  } = useActiveLanguage();

  return (
    <section className="mx-auto max-w-2xl space-y-6">
      <div className="space-y-1">
        <h1 className="text-2xl font-bold tracking-tight">Languages</h1>
        <p className="text-sm text-muted-foreground">
          Add or remove languages. Pick the active one from the header.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Your languages</CardTitle>
          <CardDescription>
            The active language scopes Generate, Review and your level.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isLoading && (
            <p
              className="flex items-center gap-2 text-sm text-muted-foreground"
              aria-busy="true"
            >
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
              Loading languages…
            </p>
          )}

          {isError && (
            <p role="alert" className="text-sm text-destructive">
              Couldn&apos;t load your languages. Please refresh.
            </p>
          )}

          {!isLoading && !isError && languages.length === 0 && (
            <p className="text-sm text-muted-foreground">
              You haven&apos;t added any languages yet. Add your first one below
              to get started.
            </p>
          )}

          {languages.length > 0 && (
            <ul className="divide-y">
              {languages.map((language) => (
                <li
                  key={language.id}
                  className="flex items-center justify-between gap-2 py-2"
                >
                  <button
                    type="button"
                    onClick={() => setActiveLanguageId(language.id)}
                    className="flex items-center gap-2 text-left text-sm font-medium hover:underline"
                  >
                    {language.name}
                    {language.code !== null && language.code !== '' && (
                      <span className="rounded bg-muted px-1.5 py-0.5 text-xs font-normal uppercase text-muted-foreground">
                        {language.code}
                      </span>
                    )}
                    {language.id === activeLanguageId && (
                      <span className="text-xs font-normal text-muted-foreground">
                        active
                      </span>
                    )}
                  </button>
                  <RemoveLanguageDialog language={language} />
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
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
    </section>
  );
}
