import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { LanguageTiles } from '@/components/dashboard/language-tiles';
import type { LanguageTileModel } from '@/lib/dashboard';
import type { LanguageOut } from '@/lib/languages';

const SPANISH: LanguageOut = {
  id: 1,
  name: 'Spanish',
  code: 'es',
  vowelized: false,
};
const HEBREW: LanguageOut = {
  id: 3,
  name: 'Hebrew',
  code: 'he',
  vowelized: true,
};
const FRENCH: LanguageOut = {
  id: 7,
  name: 'French',
  code: 'fr',
  vowelized: false,
};
const ITALIAN: LanguageOut = {
  id: 9,
  name: 'Italian',
  code: 'it',
  vowelized: false,
};

/** A ready B1 tile with a mixed due/new batch; override per-case. */
function makeTile(
  overrides: Partial<LanguageTileModel> & { language: LanguageOut },
): LanguageTileModel {
  return {
    isActive: false,
    totals: { due: 0, fresh: 0, total: 0 },
    dueLoading: false,
    dueError: false,
    band: 'B1',
    progress: 0.62,
    ...overrides,
  };
}

function renderTiles(tiles: LanguageTileModel[]) {
  const onSelectLanguage = vi.fn();
  render(
    <MemoryRouter>
      <LanguageTiles tiles={tiles} onSelectLanguage={onSelectLanguage} />
    </MemoryRouter>,
  );
  return { onSelectLanguage };
}

/** The tile is a link named for its language; scope assertions inside it. */
function tileFor(name: RegExp) {
  return screen.getByRole('link', { name });
}

/**
 * A text matcher that matches an element by its *own* combined text content — the caption splits
 * the percent into a `tabular-nums` <span> ("62" · "%" · " to " · "B2"), so a plain string/regex
 * (which matches a single text node) never sees the whole phrase. Matching the leaf-most element
 * whose full text matches avoids the "multiple elements" trap of matching ancestors too.
 */
function withText(pattern: RegExp) {
  return (_content: string, node: Element | null): boolean => {
    if (node === null) {
      return false;
    }
    const matches = pattern.test(node.textContent ?? '');
    const childMatches = Array.from(node.children).some((child) =>
      pattern.test(child.textContent ?? ''),
    );
    return matches && !childMatches;
  };
}

describe('LanguageTiles — progress caption ("% to next level")', () => {
  it('shows "{p}% to {next}" with the rounded percent under the bar', () => {
    renderTiles([makeTile({ language: SPANISH, band: 'B1', progress: 0.62 })]);
    // 0.62 → 62%, next band above B1 is B2.
    expect(
      within(tileFor(/Spanish/)).getByText(withText(/^62% to B2$/)),
    ).toBeInTheDocument();
  });

  it('rounds the fraction to a whole percent', () => {
    renderTiles([makeTile({ language: SPANISH, band: 'A2', progress: 0.555 })]);
    // 0.555 → 56%, next band above A2 is B1.
    expect(
      within(tileFor(/Spanish/)).getByText(withText(/^56% to B1$/)),
    ).toBeInTheDocument();
  });

  it('shows "Top level (C2)" — with no percent — at the top band', () => {
    renderTiles([makeTile({ language: SPANISH, band: 'C2', progress: 0.9 })]);
    const tile = tileFor(/Spanish/);
    expect(within(tile).getByText('Top level (C2)')).toBeInTheDocument();
    expect(within(tile).queryByText(/% to/)).not.toBeInTheDocument();
  });

  it('hides the bar + caption entirely when the level is unknown (band null)', () => {
    renderTiles([makeTile({ language: SPANISH, band: null, progress: 0 })]);
    const tile = tileFor(/Spanish/);
    expect(within(tile).queryByText(/% to/)).not.toBeInTheDocument();
    expect(within(tile).queryByText(/Top level/)).not.toBeInTheDocument();
  });
});

describe('LanguageTiles — due badge ("{due} due · {fresh} new")', () => {
  it('breaks the batch down as "{due} due · {fresh} new" when cards await', () => {
    renderTiles([
      makeTile({
        language: SPANISH,
        totals: { due: 4, fresh: 2, total: 6 },
      }),
    ]);
    expect(
      within(tileFor(/Spanish/)).getByText('4 due · 2 new'),
    ).toBeInTheDocument();
  });

  it('shows "Done" (not a breakdown) when nothing is due', () => {
    renderTiles([
      makeTile({ language: HEBREW, totals: { due: 0, fresh: 0, total: 0 } }),
    ]);
    const tile = tileFor(/Hebrew/);
    expect(within(tile).getByText('Done')).toBeInTheDocument();
    expect(within(tile).queryByText(/due · /)).not.toBeInTheDocument();
  });

  it('degrades a failed due batch to a muted dash, not a breakdown', () => {
    renderTiles([
      makeTile({
        language: ITALIAN,
        totals: null,
        dueError: true,
      }),
    ]);
    const tile = tileFor(/Italian/);
    expect(within(tile).getByText('—')).toBeInTheDocument();
    expect(within(tile).queryByText(/due · /)).not.toBeInTheDocument();
    expect(within(tile).queryByText('Done')).not.toBeInTheDocument();
  });

  it('shows a loading skeleton (no copy) while the due batch is pending', () => {
    renderTiles([
      makeTile({ language: FRENCH, totals: null, dueLoading: true }),
    ]);
    const tile = tileFor(/French/);
    expect(within(tile).queryByText(/due · /)).not.toBeInTheDocument();
    expect(within(tile).queryByText('Done')).not.toBeInTheDocument();
    expect(within(tile).queryByText('—')).not.toBeInTheDocument();
  });
});

describe('LanguageTiles — contract (unchanged roles/routes)', () => {
  it('links each tile to Review and sets the language active on tap', () => {
    const { onSelectLanguage } = renderTiles([
      makeTile({ language: HEBREW, isActive: true }),
    ]);
    const tile = tileFor(/Hebrew/);
    expect(tile).toHaveAttribute('href', '/review');
    fireEvent.click(tile);
    expect(onSelectLanguage).toHaveBeenCalledWith(3);
  });

  it('keeps the "Manage" link to /languages and the section label', () => {
    renderTiles([makeTile({ language: SPANISH })]);
    expect(screen.getByRole('link', { name: 'Manage' })).toHaveAttribute(
      'href',
      '/languages',
    );
    expect(
      screen.getByRole('region', { name: 'Your languages' }),
    ).toBeInTheDocument();
  });

  it('renders the band chip + "Active" chip for the active language', () => {
    renderTiles([makeTile({ language: SPANISH, isActive: true, band: 'B1' })]);
    const tile = tileFor(/Spanish/);
    expect(within(tile).getByText('B1')).toBeInTheDocument();
    expect(within(tile).getByText('Active')).toBeInTheDocument();
  });
});
