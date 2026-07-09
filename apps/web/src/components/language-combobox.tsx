/**
 * Language combobox (issue #95) — the searchable picker over the curated language list.
 *
 * An ARIA combobox: a search input (`role="combobox"`) wired to an always-open listbox
 * (`role="listbox"`). Filtering is a case-insensitive substring over each language's English name,
 * endonym, and code; an empty query shows the whole list. Each option shows the English name with
 * the endonym as muted secondary text, rendered in its own script (`scriptFontClass`) so the row
 * doubles as a script preview.
 *
 * The LAST row is always a "custom language" affordance (`Add "<query>" as a custom language…`)
 * — and the ONLY row when nothing matches — so the free-form path is always reachable.
 *
 * Presentational and callback-driven: it owns only the highlight/keyboard state, and reports a
 * choice through {@link onSelect} (a curated entry) or {@link onSelectCustom} (the custom row).
 * Keyboard: ↑/↓ move the active option, Enter selects it, Esc clears the query.
 */
import { useId, useMemo, useRef, useState } from 'react';

import {
  CURATED_LANGUAGES,
  type CuratedLanguage,
} from '@/lib/curated-languages';
import { scriptFontClass } from '@/lib/language-text';
import { cn } from '@/lib/utils';

export interface LanguageComboboxProps {
  /** Called when a curated language row is chosen. */
  onSelect: (language: CuratedLanguage) => void;
  /** Called when the custom row is chosen; receives the trimmed current query (may be empty). */
  onSelectCustom: (query: string) => void;
}

/** Case-insensitive substring match over English name, endonym, and code. */
function matches(language: CuratedLanguage, needle: string): boolean {
  if (needle === '') {
    return true;
  }
  return (
    language.name.toLowerCase().includes(needle) ||
    language.nativeName.toLowerCase().includes(needle) ||
    language.code.toLowerCase().includes(needle)
  );
}

/** The number of selectable rows: the filtered languages plus the always-present custom row. */
function rowCount(filteredLength: number): number {
  return filteredLength + 1;
}

export function LanguageCombobox({
  onSelect,
  onSelectCustom,
}: LanguageComboboxProps) {
  const [query, setQuery] = useState('');
  // Which option is highlighted for keyboard selection: an index into `filtered`, or the custom
  // row (index === filtered.length). Defaults to the first row.
  const [activeIndex, setActiveIndex] = useState(0);
  const listboxId = useId();
  const baseId = useId();
  const listRef = useRef<HTMLUListElement>(null);

  const trimmedQuery = query.trim();
  const needle = trimmedQuery.toLowerCase();

  const filtered = useMemo(
    () => CURATED_LANGUAGES.filter((lang) => matches(lang, needle)),
    [needle],
  );

  const customIndex = filtered.length;
  const total = rowCount(filtered.length);
  // Clamp the highlight into range whenever the filtered set shrinks (typing narrows the list).
  const active = Math.min(activeIndex, total - 1);

  const optionId = (index: number) => `${baseId}-option-${index}`;

  function move(delta: number) {
    setActiveIndex((current) => {
      const clamped = Math.min(current, total - 1);
      const next = (clamped + delta + total) % total;
      // Scroll the newly-active row into view so keyboard nav past the fold stays visible.
      // Guarded because jsdom (unit tests) doesn't implement Element.scrollIntoView.
      requestAnimationFrame(() => {
        const el = listRef.current?.querySelector<HTMLElement>(
          `#${CSS.escape(optionId(next))}`,
        );
        el?.scrollIntoView?.({ block: 'nearest' });
      });
      return next;
    });
  }

  function choose(index: number) {
    if (index >= filtered.length) {
      onSelectCustom(trimmedQuery);
      return;
    }
    onSelect(filtered[index]);
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        move(1);
        break;
      case 'ArrowUp':
        event.preventDefault();
        move(-1);
        break;
      case 'Enter':
        event.preventDefault();
        choose(active);
        break;
      case 'Escape':
        // Clear the query (and reset the highlight) rather than closing — the listbox is always open.
        if (query !== '') {
          event.preventDefault();
          setQuery('');
          setActiveIndex(0);
        }
        break;
      default:
        break;
    }
  }

  return (
    <div className="space-y-2">
      <label htmlFor={`${baseId}-input`} className="text-body font-medium">
        Language
      </label>
      <input
        id={`${baseId}-input`}
        type="text"
        role="combobox"
        aria-expanded="true"
        aria-controls={listboxId}
        aria-autocomplete="list"
        aria-activedescendant={optionId(active)}
        autoComplete="off"
        autoCorrect="off"
        spellCheck={false}
        placeholder="Search languages…"
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setActiveIndex(0);
        }}
        onKeyDown={handleKeyDown}
        className="flex h-10 w-full rounded-md border border-input bg-card px-3.5 text-body placeholder:text-muted-foreground transition-[border-color,box-shadow] duration-150 focus-visible:outline-none focus-visible:border-primary/60 focus-visible:ring-[3px] focus-visible:ring-primary/25"
      />
      <ul
        ref={listRef}
        id={listboxId}
        role="listbox"
        aria-label="Curated languages"
        className="max-h-64 overflow-y-auto rounded-md border bg-card shadow-card"
      >
        {filtered.map((language, index) => {
          const isActive = index === active;
          return (
            <li
              key={language.code}
              id={optionId(index)}
              role="option"
              aria-selected={isActive}
              // Highlight on hover so pointer + keyboard agree on the active row.
              onMouseMove={() => setActiveIndex(index)}
              onClick={() => choose(index)}
              className={cn(
                'flex cursor-pointer items-baseline justify-between gap-3 px-3.5 py-2 text-body',
                isActive && 'bg-secondary',
              )}
            >
              <span className="truncate">{language.name}</span>
              <span
                lang={language.code}
                className={cn(
                  'shrink-0 text-subhead text-muted-foreground',
                  scriptFontClass(language.code),
                )}
              >
                {language.nativeName}
              </span>
            </li>
          );
        })}
        <li
          key="__custom__"
          id={optionId(customIndex)}
          role="option"
          aria-selected={active === customIndex}
          onMouseMove={() => setActiveIndex(customIndex)}
          onClick={() => choose(customIndex)}
          className={cn(
            'cursor-pointer px-3.5 py-2 text-body text-muted-foreground',
            filtered.length > 0 && 'border-t',
            active === customIndex && 'bg-secondary',
          )}
        >
          {trimmedQuery === ''
            ? 'Add a custom language…'
            : `Add “${trimmedQuery}” as a custom language…`}
        </li>
      </ul>
    </div>
  );
}
