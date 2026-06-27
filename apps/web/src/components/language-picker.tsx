/**
 * Active-language picker (task 4.4.1) — lives in the app-shell header so it is reachable on every
 * screen (and on mobile, where the sidebar is hidden). Switching the selection updates the
 * active-language context, which re-keys every language-scoped query so they refetch for the new
 * language.
 *
 * A native `<select>` is used deliberately over a custom Radix combobox: it is fully accessible,
 * trivial to drive in tests/Playwright, and gives the best native UX inside the Capacitor webview
 * (Phase 7). When the account has no languages yet, it degrades to a link to the management screen.
 */
import { Globe } from 'lucide-react';
import { Link } from 'react-router-dom';

import { useActiveLanguage } from '@/components/active-language-context';
import { cn } from '@/lib/utils';

export function LanguagePicker() {
  const { languages, activeLanguageId, setActiveLanguageId, isLoading } =
    useActiveLanguage();

  if (isLoading && languages.length === 0) {
    return (
      <span className="text-sm text-muted-foreground" aria-busy="true">
        Loading…
      </span>
    );
  }

  if (languages.length === 0) {
    return (
      <Link
        to="/languages"
        className="text-sm font-medium text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
      >
        Add a language
      </Link>
    );
  }

  return (
    <div className="flex items-center gap-2">
      <Globe className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
      <select
        aria-label="Active language"
        value={activeLanguageId ?? ''}
        onChange={(event) => setActiveLanguageId(Number(event.target.value))}
        className={cn(
          'h-9 rounded-md border border-input bg-background px-2 text-sm font-medium',
          'ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2',
        )}
      >
        {languages.map((language) => (
          <option key={language.id} value={language.id}>
            {language.name}
          </option>
        ))}
      </select>
    </div>
  );
}
