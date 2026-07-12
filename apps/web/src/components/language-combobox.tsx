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
 *
 * As-built keyboard model (a deliberate deviation from the retired #95 design spec's "Esc
 * closes" — the spec lives in git history): the listbox is ALWAYS open (this is an inline in-card
 * picker, not a popover), so `aria-expanded` is always `true` and there is nothing to collapse.
 * ↑/↓ move the active option, Enter selects it, and Escape clears the query instead of closing.
 * IME composition is respected — the Enter/Arrows that drive a CJK candidate list never leak into
 * option navigation.
 */
import { useEffect, useId, useMemo, useRef, useState } from 'react';

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
  /**
   * Focus the search input on mount. Left off on the page's first render (so the picker doesn't
   * steal focus on load), set when returning to the picker from a form step so keyboard/SR users
   * land back on the search input rather than at `<body>`.
   */
  autoFocus?: boolean;
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
  autoFocus = false,
}: LanguageComboboxProps) {
  const [query, setQuery] = useState('');
  // Which option is highlighted for keyboard selection: an index into `filtered`, or the custom
  // row (index === filtered.length). Defaults to the first row.
  const [activeIndex, setActiveIndex] = useState(0);
  const listboxId = useId();
  const baseId = useId();
  const listRef = useRef<HTMLUListElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (autoFocus) {
      inputRef.current?.focus();
    }
    // Only on mount — `autoFocus` reflects why this instance was rendered (fresh vs. returned-to).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  // Per-row ids are keyed by a STABLE token (the language code, or "custom"), not the row index —
  // so `aria-activedescendant` changes value when filtering re-targets the active row and screen
  // readers actually announce the newly-highlighted language (a positional id would stay the same
  // string while naming a different row, and NVDA/JAWS/VoiceOver would say nothing).
  const optionToken = (index: number) =>
    index >= filtered.length ? 'custom' : filtered[index].code;
  const optionId = (token: string) => `${baseId}-option-${token}`;
  const activeOptionId = optionId(optionToken(active));

  function move(delta: number) {
    setActiveIndex((current) => {
      const clamped = Math.min(current, total - 1);
      const next = (clamped + delta + total) % total;
      // Scroll the newly-active row into view so keyboard nav past the fold stays visible.
      // Guarded because jsdom (unit tests) doesn't implement Element.scrollIntoView.
      requestAnimationFrame(() => {
        const el = listRef.current?.querySelector<HTMLElement>(
          `#${CSS.escape(optionId(optionToken(next)))}`,
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
    // Respect IME composition: the Enter that COMMITS a CJK candidate (and the arrows that walk the
    // candidate list) must not leak into option navigation — otherwise composing an endonym like
    // 日本語 would yank the user into the custom form. `isComposing` is true until the composition
    // ends. `keyCode === 229` is the legacy signal some IMEs still send.
    if (event.nativeEvent.isComposing || event.keyCode === 229) {
      return;
    }
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
        ref={inputRef}
        id={`${baseId}-input`}
        type="text"
        role="combobox"
        aria-expanded="true"
        aria-controls={listboxId}
        aria-autocomplete="list"
        aria-activedescendant={activeOptionId}
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
              id={optionId(language.code)}
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
          id={optionId('custom')}
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
