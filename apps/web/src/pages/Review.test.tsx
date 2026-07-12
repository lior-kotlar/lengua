import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Drive the real due/grade/explain hooks against a mocked transport; spy on the toast queue.
const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...actual, getApiClient: () => ({ GET: get, POST: post }) };
});
const { toast } = vi.hoisted(() => ({ toast: vi.fn() }));
vi.mock('@/components/ui/use-toast', () => ({ toast }));

import {
  ActiveLanguageContext,
  type ActiveLanguageState,
} from '@/components/active-language-context';
import { VowelMarksProvider } from '@/components/vowel-marks-provider';
import type { LanguageOut } from '@/lib/languages';
import type { CardOut } from '@/lib/review';
import Review from '@/pages/Review';

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

const ARABIC: LanguageOut = {
  id: 5,
  name: 'Arabic',
  code: 'ar',
  vowelized: true,
};

interface ApiResult {
  data: unknown;
  error: unknown;
  response: Response;
}

function okResult(data: unknown, status = 200): Promise<ApiResult> {
  return Promise.resolve({
    data,
    error: undefined,
    response: new Response(null, { status }),
  });
}

function failResult(status: number, code: string): Promise<ApiResult> {
  return Promise.resolve({
    data: undefined,
    error: { code, message: `failed: ${code}` },
    response: new Response(null, { status }),
  });
}

function makeCard(
  id: number,
  direction: string,
  front: string,
  back: string,
  extra: Partial<CardOut> = {},
): CardOut {
  return {
    id,
    language_id: 1,
    direction,
    front,
    back,
    used_words: [],
    word_explanations: null,
    gen_level: null,
    saved: true,
    due: null,
    ...extra,
  };
}

function due(newCards: CardOut[], dueCards: CardOut[]) {
  return { new: newCards, due: dueCards };
}

function makeValue(
  overrides: Partial<ActiveLanguageState> = {},
): ActiveLanguageState {
  return {
    languages: [SPANISH],
    activeLanguageId: 1,
    activeLanguage: SPANISH,
    setActiveLanguageId: vi.fn(),
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
    ...overrides,
  };
}

function renderReview(value: ActiveLanguageState = makeValue()) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <ActiveLanguageContext.Provider value={value}>
          <VowelMarksProvider>
            <Review />
          </VowelMarksProvider>
        </ActiveLanguageContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/** Find a rating button by its FSRS grade value (1..4) via the `data-rating` attribute. */
function ratingButton(value: number): HTMLButtonElement {
  const el = document.querySelector(`[data-rating="${value}"]`);
  if (el === null) {
    throw new Error(`rating button ${value} not found`);
  }
  return el as HTMLButtonElement;
}

beforeEach(() => {
  vi.clearAllMocks();
  // The real VowelMarksProvider persists to localStorage — reset so the toggle state never leaks.
  localStorage.clear();
});

describe('Review — RTL & vowel marks (4.9)', () => {
  it('sets dir on the content region from the language code (4.9.1)', () => {
    get.mockReturnValue(okResult(due([], [])));
    const view = renderReview(
      makeValue({
        languages: [ARABIC],
        activeLanguageId: 5,
        activeLanguage: ARABIC,
      }),
    );
    expect(screen.getByTestId('review-content')).toHaveAttribute('dir', 'rtl');
    view.unmount();

    renderReview(); // default Spanish (LTR)
    expect(screen.getByTestId('review-content')).toHaveAttribute('dir', 'ltr');
  });

  it('strips and restores the diacritics in the rendered prompt when the toggle flips (4.9.3)', async () => {
    const user = userEvent.setup();
    get.mockReturnValue(
      okResult(
        due([makeCard(1, 'recognition', 'שָׁלוֹם עוֹלָם', 'hello world')], []),
      ),
    );
    renderReview(
      makeValue({
        languages: [HEBREW],
        activeLanguageId: 3,
        activeLanguage: HEBREW,
      }),
    );

    // The vowelized prompt renders first (marks shown by default).
    expect(await screen.findByText('שָׁלוֹם עוֹלָם')).toBeInTheDocument();

    // Accessible name = the language-aware visible label (WCAG 2.5.3 label-in-name; Hebrew → nikkud).
    const toggle = screen.getByRole('switch', { name: 'Vowel marks (nikkud)' });
    await user.click(toggle); // marks off → stripped glyphs
    expect(screen.getByText('שלום עולם')).toBeInTheDocument();
    expect(screen.queryByText('שָׁלוֹם עוֹלָם')).toBeNull();

    await user.click(toggle); // marks on → restored
    expect(screen.getByText('שָׁלוֹם עוֹלָם')).toBeInTheDocument();
  });

  it('renders a recognition answer (English) as plain text, not the RTL target script (S13)', async () => {
    const user = userEvent.setup();
    get.mockReturnValue(
      okResult(
        due([makeCard(1, 'recognition', 'مرحبا بالعالم', 'hello world')], []),
      ),
    );
    renderReview(
      makeValue({
        languages: [ARABIC],
        activeLanguageId: 5,
        activeLanguage: ARABIC,
      }),
    );

    // The Arabic PROMPT is target text, so it keeps the RTL script font.
    const prompt = await screen.findByText('مرحبا بالعالم');
    expect(prompt).toHaveClass('font-arabic');

    await user.click(screen.getByRole('button', { name: 'Show translation' }));

    // The English ANSWER must NOT inherit the script font / explicit dir="rtl" that LanguageText
    // applies to target text — that treatment hid the translation on an RTL deck. It is plain text,
    // exactly like a production card's English front.
    const answer = screen.getByTestId('card-answer');
    expect(answer).toHaveTextContent('hello world');
    const english = screen.getByText('hello world');
    expect(english).not.toHaveClass('font-arabic');
    expect(english).not.toHaveAttribute('dir', 'rtl');
  });
});

describe('Review — language gating', () => {
  it('shows a loading state while languages load', () => {
    renderReview(
      makeValue({
        isLoading: true,
        activeLanguageId: null,
        activeLanguage: null,
      }),
    );
    expect(screen.getByTestId('loading-skeleton')).toBeInTheDocument();
    expect(screen.getByText(/loading your languages/i)).toBeInTheDocument();
  });

  it('prompts to add a language when the user has none', () => {
    renderReview(makeValue({ activeLanguageId: null, activeLanguage: null }));
    expect(screen.getByTestId('empty-state')).toBeInTheDocument();
    expect(screen.getByText('Add a language first')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /add a language/i }),
    ).toHaveAttribute('href', '/languages');
  });

  it('shows a retryable error when the languages query fails', async () => {
    const user = userEvent.setup();
    const refetch = vi.fn();
    renderReview(
      makeValue({
        isError: true,
        activeLanguageId: null,
        activeLanguage: null,
        refetch,
      }),
    );
    expect(screen.getByTestId('error-state')).toBeInTheDocument();
    expect(
      screen.getByText(/couldn.t load your languages/i),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /try again/i }));
    expect(refetch).toHaveBeenCalledTimes(1);
  });
});

describe('Review — batch loading states (4.6.1)', () => {
  it('shows a loading state while the due batch loads', () => {
    get.mockReturnValue(new Promise(() => {})); // never resolves
    renderReview();
    expect(screen.getByTestId('loading-skeleton')).toBeInTheDocument();
    expect(screen.getByText(/loading your due cards/i)).toBeInTheDocument();
  });

  it('shows a retryable error when the batch fails to load', async () => {
    get.mockReturnValue(failResult(500, 'kaboom'));
    renderReview();
    expect(await screen.findByTestId('error-state')).toBeInTheDocument();
    expect(screen.getByText(/couldn.t load your cards/i)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /try again/i }),
    ).toBeInTheDocument();
  });

  it('shows the all-caught-up empty state when nothing is due', async () => {
    get.mockReturnValue(okResult(due([], [])));
    renderReview();
    expect(await screen.findByTestId('empty-state')).toBeInTheDocument();
    expect(
      await screen.findByText(/you.re all caught up/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /generate sentences/i }),
    ).toHaveAttribute('href', '/generate');
  });

  it('renders the new/due counts header and the first card front', async () => {
    get.mockReturnValue(
      okResult(
        due(
          [makeCard(1, 'recognition', 'Hola', 'Hello')],
          [
            makeCard(2, 'recognition', 'Adiós', 'Goodbye'),
            makeCard(3, 'recognition', 'Gracias', 'Thanks'),
          ],
        ),
      ),
    );
    renderReview();

    const counts = await screen.findByTestId('review-counts');
    expect(counts).toHaveTextContent('1 new');
    expect(counts).toHaveTextContent('2 due');
    expect(counts).toHaveTextContent('Card 1 of 3');
    // First card front: DUE cards are walked before new ones, so the first due card ('Adiós')
    // leads and the new card ('Hola') is buried at the back of the batch.
    expect(screen.getByText('Adiós')).toBeInTheDocument();
    expect(screen.queryByText('Hola')).not.toBeInTheDocument();
    // Its answer is not shown yet.
    expect(screen.queryByText('Goodbye')).not.toBeInTheDocument();
  });
});

describe('Review — reveal interaction (4.6.2)', () => {
  it('hides the answer and rating buttons until reveal, then shows both', async () => {
    const user = userEvent.setup();
    get.mockReturnValue(
      okResult(due([makeCard(1, 'recognition', 'Hola', 'Hello')], [])),
    );
    renderReview();

    await screen.findByText('Hola');
    // Hidden before reveal.
    expect(screen.queryByText('Hello')).not.toBeInTheDocument();
    expect(ratingButtonExists(1)).toBe(false);

    await user.click(screen.getByRole('button', { name: 'Show translation' }));

    // Answer + all four rating buttons appear.
    expect(screen.getByTestId('card-answer')).toHaveTextContent('Hello');
    for (const value of [1, 2, 3, 4]) {
      expect(ratingButtonExists(value)).toBe(true);
    }
  });

  it('labels the prompt + reveal by direction and makes production answers tappable', async () => {
    const user = userEvent.setup();
    get.mockReturnValue(
      okResult(due([], [makeCard(5, 'production', 'The chair', 'La silla')])),
    );
    renderReview();

    // Production prompt + reveal label.
    expect(
      await screen.findByText(/build the sentence in spanish/i),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Show answer' }));

    // The answer renders the target sentence as tappable words.
    const answer = screen.getByTestId('card-answer');
    expect(
      within(answer).getByRole('button', { name: 'silla' }),
    ).toBeInTheDocument();
  });
});

describe('Review — rating (4.6.3)', () => {
  it('colours each rating button in the locked red/orange/blue/green', async () => {
    const user = userEvent.setup();
    get.mockReturnValue(
      okResult(due([makeCard(1, 'recognition', 'Hola', 'Hello')], [])),
    );
    renderReview();
    await screen.findByText('Hola');
    await user.click(screen.getByRole('button', { name: 'Show translation' }));

    expect(ratingButton(1).className).toContain('bg-hig-red/15'); // Again
    expect(ratingButton(2).className).toContain('bg-hig-orange/15'); // Hard
    expect(ratingButton(3).className).toContain('bg-hig-blue/15'); // Good
    expect(ratingButton(4).className).toContain('bg-hig-green/15'); // Easy
  });

  it('posts the chosen grade and advances to the next card', async () => {
    const user = userEvent.setup();
    get.mockReturnValue(
      okResult(
        due(
          [makeCard(11, 'recognition', 'Hola', 'Hello')],
          [makeCard(22, 'recognition', 'Adiós', 'Goodbye')],
        ),
      ),
    );
    post.mockReturnValue(
      okResult({
        card_id: 22,
        due: '2026-07-01T00:00:00Z',
        score: 1,
        score_changed: false,
      }),
    );
    renderReview();

    // Due cards come first, so the due card ('Adiós', id 22) is graded before the new one.
    await screen.findByText('Adiós');
    await user.click(screen.getByRole('button', { name: 'Show translation' }));
    await user.click(ratingButton(3)); // Good

    expect(post).toHaveBeenCalledWith('/review/{card_id}/grade', {
      params: { path: { card_id: 22 } },
      body: { rating: 3 },
    });
    // Advanced to the new card (front shown, answer hidden again).
    expect(await screen.findByText('Hola')).toBeInTheDocument();
    expect(screen.queryByText('Hello')).not.toBeInTheDocument();
  });

  it('reaches the done state after the last card and can check for more', async () => {
    const user = userEvent.setup();
    get.mockReturnValue(
      okResult(due([makeCard(1, 'recognition', 'Hola', 'Hello')], [])),
    );
    post.mockReturnValue(
      okResult({ card_id: 1, due: 'x', score: 0, score_changed: false }),
    );
    renderReview();

    await screen.findByText('Hola');
    await user.click(screen.getByRole('button', { name: 'Show translation' }));
    await user.click(ratingButton(4));

    expect(await screen.findByText(/done for today/i)).toBeInTheDocument();
    expect(screen.getByText(/you reviewed 1 card\b/i)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /check for more/i }),
    ).toBeInTheDocument();
  });

  it('surfaces a destructive toast and keeps the card when grading fails', async () => {
    const user = userEvent.setup();
    get.mockReturnValue(
      okResult(due([makeCard(1, 'recognition', 'Hola', 'Hello')], [])),
    );
    post.mockReturnValue(failResult(500, 'oops'));
    renderReview();

    await screen.findByText('Hola');
    await user.click(screen.getByRole('button', { name: 'Show translation' }));
    await user.click(ratingButton(2));

    await vi.waitFor(() =>
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({
          variant: 'destructive',
          title: 'Could not save your answer',
        }),
      ),
    );
    // Still on the same card, still revealed.
    expect(screen.getByTestId('card-answer')).toHaveTextContent('Hello');
  });
});

describe('Review — keyboard shortcuts (4.6.5)', () => {
  it('reveals with space and with enter', async () => {
    get.mockReturnValue(
      okResult(due([makeCard(1, 'recognition', 'Hola', 'Hello')], [])),
    );
    const { unmount } = renderReview();
    await screen.findByText('Hola');

    fireEvent.keyDown(document.body, { key: ' ' });
    expect(await screen.findByTestId('card-answer')).toHaveTextContent('Hello');
    unmount();

    // A fresh mount reveals with Enter instead.
    get.mockReturnValue(
      okResult(due([makeCard(2, 'recognition', 'Sí', 'Yes')], [])),
    );
    renderReview();
    await screen.findByText('Sí');
    fireEvent.keyDown(document.body, { key: 'Enter' });
    expect(await screen.findByTestId('card-answer')).toHaveTextContent('Yes');
  });

  it('maps digits 1–4 to the matching grade while walking the batch', async () => {
    get.mockReturnValue(
      okResult(
        due(
          [],
          [
            makeCard(10, 'recognition', 'one', 'uno'),
            makeCard(20, 'recognition', 'two', 'dos'),
            makeCard(30, 'recognition', 'three', 'tres'),
            makeCard(40, 'recognition', 'four', 'cuatro'),
          ],
        ),
      ),
    );
    post.mockImplementation(() =>
      okResult({ card_id: 0, due: 'x', score: 0, score_changed: false }),
    );
    renderReview();
    await screen.findByText('one');

    // Reveal + rate each card with its position's digit; each should advance.
    fireEvent.keyDown(document.body, { key: ' ' });
    await screen.findByTestId('card-answer');
    fireEvent.keyDown(document.body, { key: '1' });

    expect(await screen.findByText('two')).toBeInTheDocument();
    fireEvent.keyDown(document.body, { key: ' ' });
    await screen.findByTestId('card-answer');
    fireEvent.keyDown(document.body, { key: '2' });

    expect(await screen.findByText('three')).toBeInTheDocument();
    fireEvent.keyDown(document.body, { key: ' ' });
    await screen.findByTestId('card-answer');
    fireEvent.keyDown(document.body, { key: '3' });

    expect(await screen.findByText('four')).toBeInTheDocument();
    fireEvent.keyDown(document.body, { key: ' ' });
    await screen.findByTestId('card-answer');
    fireEvent.keyDown(document.body, { key: '4' });

    await screen.findByText(/done for today/i);

    // Each card was graded with the digit pressed (cards in due order 10,20,30,40).
    const grades = post.mock.calls
      .filter((call) => call[0] === '/review/{card_id}/grade')
      .map((call) => [call[1].params.path.card_id, call[1].body.rating]);
    expect(grades).toEqual([
      [10, 1],
      [20, 2],
      [30, 3],
      [40, 4],
    ]);
  });

  it('does not reveal on an unrelated key', async () => {
    get.mockReturnValue(
      okResult(due([makeCard(1, 'recognition', 'Hola', 'Hello')], [])),
    );
    renderReview();
    await screen.findByText('Hola');

    fireEvent.keyDown(document.body, { key: 'x' });
    expect(screen.queryByTestId('card-answer')).not.toBeInTheDocument();
  });

  it('ignores shortcuts pressed with a modifier key', async () => {
    get.mockReturnValue(
      okResult(due([makeCard(1, 'recognition', 'Hola', 'Hello')], [])),
    );
    renderReview();
    await screen.findByText('Hola');

    // Ctrl+Space (e.g. an OS/browser shortcut) must not reveal the card.
    fireEvent.keyDown(document.body, { key: ' ', ctrlKey: true });
    expect(screen.queryByTestId('card-answer')).not.toBeInTheDocument();
  });

  it('ignores a second grade while one is already in flight', async () => {
    get.mockReturnValue(
      okResult(
        due(
          [
            makeCard(11, 'recognition', 'Hola', 'Hello'),
            makeCard(22, 'recognition', 'Adiós', 'Bye'),
          ],
          [],
        ),
      ),
    );
    let resolveGrade!: (value: ApiResult) => void;
    post.mockReturnValue(
      new Promise<ApiResult>((res) => {
        resolveGrade = res;
      }),
    );
    renderReview();

    await screen.findByText('Hola');
    fireEvent.keyDown(document.body, { key: ' ' });
    await screen.findByTestId('card-answer');
    fireEvent.keyDown(document.body, { key: '1' }); // starts grading card 11
    // Wait until the first grade is in flight (pending), then try to grade again.
    await vi.waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    fireEvent.keyDown(document.body, { key: '2' }); // ignored — a grade is in flight

    expect(post).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenCalledWith('/review/{card_id}/grade', {
      params: { path: { card_id: 11 } },
      body: { rating: 1 },
    });

    // Let it settle to advance (and avoid act warnings).
    resolveGrade({
      data: { card_id: 11, due: 'x', score: 0, score_changed: false },
      error: undefined,
      response: new Response(null, { status: 200 }),
    });
    expect(await screen.findByText('Adiós')).toBeInTheDocument();
  });

  it('ignores shortcuts while typing in a form control', async () => {
    get.mockReturnValue(
      okResult(due([makeCard(1, 'recognition', 'Hola', 'Hello')], [])),
    );
    renderReview();
    await screen.findByText('Hola');

    // A space typed into an input (e.g. the header language picker) must not reveal the card.
    const input = document.createElement('input');
    document.body.appendChild(input);
    fireEvent.keyDown(input, { key: ' ' });
    expect(screen.queryByTestId('card-answer')).not.toBeInTheDocument();
    input.remove();
  });
});

describe('Review — recovery + restart paths', () => {
  it('retries the batch from the error state', async () => {
    get.mockReturnValueOnce(failResult(500, 'boom'));
    get.mockReturnValue(
      okResult(due([makeCard(1, 'recognition', 'Hola', 'Hello')], [])),
    );
    const user = userEvent.setup();
    renderReview();

    await screen.findByText(/couldn.t load your cards/i);
    await user.click(screen.getByRole('button', { name: /try again/i }));
    expect(await screen.findByText('Hola')).toBeInTheDocument();
  });

  it('checks for more cards from the done state, refetching a fresh batch', async () => {
    get.mockReturnValue(
      okResult(due([makeCard(1, 'recognition', 'Hola', 'Hello')], [])),
    );
    post.mockReturnValue(
      okResult({ card_id: 1, due: 'x', score: 0, score_changed: false }),
    );
    const user = userEvent.setup();
    renderReview();

    await screen.findByText('Hola');
    await user.click(screen.getByRole('button', { name: 'Show translation' }));
    await user.click(ratingButton(3));
    await screen.findByText(/done for today/i);

    // A fresh batch is waiting on the next fetch.
    get.mockReturnValue(
      okResult(due([], [makeCard(2, 'recognition', 'Nuevo', 'New')])),
    );
    await user.click(screen.getByRole('button', { name: /check for more/i }));
    expect(await screen.findByText('Nuevo')).toBeInTheDocument();
  });
});

describe('Review — without a resolved language name (defensive)', () => {
  // The active id can momentarily be set before the language object resolves.
  const noName = makeValue({ activeLanguage: null });

  it('omits the language from the empty state copy', async () => {
    get.mockReturnValue(okResult(due([], [])));
    renderReview(noName);
    expect(
      await screen.findByText(/no cards are due\s+right now/i),
    ).toBeInTheDocument();
  });

  it('omits the language from a production prompt', async () => {
    get.mockReturnValue(
      okResult(due([], [makeCard(9, 'production', 'The chair', 'La silla')])),
    );
    renderReview(noName);
    expect(await screen.findByText('Build the sentence')).toBeInTheDocument();
  });
});

describe('Review — commit flash (PR3)', () => {
  it('flashes the chosen pill solid and dims its siblings while the grade posts', async () => {
    const user = userEvent.setup();
    get.mockReturnValue(
      okResult(due([makeCard(1, 'recognition', 'Hola', 'Hello')], [])),
    );
    post.mockReturnValue(new Promise(() => {})); // hold the grade in flight
    renderReview();

    await screen.findByText('Hola');
    await user.click(screen.getByRole('button', { name: 'Show translation' }));
    fireEvent.click(ratingButton(1)); // Again → flashes solid red

    // The chosen pill fills solid (white text on the vivid hue) and is NOT dimmed.
    expect(ratingButton(1).className).toContain('text-white');
    expect(ratingButton(1).className).not.toContain('opacity-40');
    // Its three siblings recede.
    for (const value of [2, 3, 4]) {
      expect(ratingButton(value).className).toContain('opacity-40');
    }
  });

  it('clears the flash and keeps the card when the grade fails', async () => {
    const user = userEvent.setup();
    get.mockReturnValue(
      okResult(due([makeCard(1, 'recognition', 'Hola', 'Hello')], [])),
    );
    post.mockReturnValue(failResult(500, 'oops'));
    renderReview();

    await screen.findByText('Hola');
    await user.click(screen.getByRole('button', { name: 'Show translation' }));
    fireEvent.click(ratingButton(1));

    // RTL waitFor flushes the async onError state update inside act().
    await waitFor(() => expect(toast).toHaveBeenCalled());
    // Back to the resting tinted pill; nothing is left dimmed, and the card stays revealed.
    expect(ratingButton(1).className).toContain('bg-hig-red/15');
    expect(ratingButton(1).className).not.toContain('text-white');
    for (const value of [1, 2, 3, 4]) {
      expect(ratingButton(value).className).not.toContain('opacity-40');
    }
    expect(screen.getByTestId('card-answer')).toHaveTextContent('Hello');
  });

  it('fires a short haptic when grading on a coarse (touch) pointer', async () => {
    const user = userEvent.setup();
    const vibrate = vi.fn();
    Object.defineProperty(navigator, 'vibrate', {
      value: vibrate,
      configurable: true,
      writable: true,
    });
    const originalMatchMedia = window.matchMedia;
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes('coarse'), // report a coarse pointer, nothing else
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));
    get.mockReturnValue(
      okResult(due([makeCard(1, 'recognition', 'Hola', 'Hello')], [])),
    );
    post.mockReturnValue(new Promise(() => {}));

    try {
      renderReview();
      await screen.findByText('Hola');
      await user.click(
        screen.getByRole('button', { name: 'Show translation' }),
      );
      fireEvent.click(ratingButton(1));
      expect(vibrate).toHaveBeenCalledWith(10);
    } finally {
      window.matchMedia = originalMatchMedia;
      delete (navigator as { vibrate?: unknown }).vibrate;
    }
  });

  it('does not vibrate when grading on a fine (mouse) pointer', async () => {
    const user = userEvent.setup();
    const vibrate = vi.fn();
    Object.defineProperty(navigator, 'vibrate', {
      value: vibrate,
      configurable: true,
      writable: true,
    });
    // The default matchMedia mock reports every query as non-matching → the pointer is fine.
    get.mockReturnValue(
      okResult(due([makeCard(1, 'recognition', 'Hola', 'Hello')], [])),
    );
    post.mockReturnValue(new Promise(() => {}));

    try {
      renderReview();
      await screen.findByText('Hola');
      await user.click(
        screen.getByRole('button', { name: 'Show translation' }),
      );
      fireEvent.click(ratingButton(1));
      expect(vibrate).not.toHaveBeenCalled();
    } finally {
      delete (navigator as { vibrate?: unknown }).vibrate;
    }
  });
});

describe('Review — accessible-name locks (PR3, kbd chips are decorative)', () => {
  it('keeps the reveal button name exact despite the Space chip ("Show translation")', async () => {
    get.mockReturnValue(
      okResult(due([makeCard(1, 'recognition', 'Hola', 'Hello')], [])),
    );
    renderReview();
    await screen.findByText('Hola');
    // The <Kbd>Space</Kbd> is aria-hidden, so the accessible name stays exactly "Show translation".
    expect(
      screen.getByRole('button', { name: 'Show translation' }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /^Show (answer|translation)$/ }),
    ).toBeInTheDocument();
  });

  it('keeps the reveal button name exact on a production card ("Show answer")', async () => {
    get.mockReturnValue(
      okResult(due([], [makeCard(5, 'production', 'The chair', 'La silla')])),
    );
    renderReview();
    await screen.findByText(/build the sentence/i);
    expect(
      screen.getByRole('button', { name: 'Show answer' }),
    ).toBeInTheDocument();
  });

  it('keeps the rating names exactly Again/Hard/Good/Easy despite the digit chips', async () => {
    const user = userEvent.setup();
    get.mockReturnValue(
      okResult(due([makeCard(1, 'recognition', 'Hola', 'Hello')], [])),
    );
    renderReview();
    await screen.findByText('Hola');
    await user.click(screen.getByRole('button', { name: 'Show translation' }));
    // Exact names (the aria-hidden digit chip is excluded from the accessible name).
    for (const label of ['Again', 'Hard', 'Good', 'Easy']) {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    }
  });
});

/** Whether a rating button for the given grade value is currently mounted. */
function ratingButtonExists(value: number): boolean {
  return document.querySelector(`[data-rating="${value}"]`) !== null;
}
