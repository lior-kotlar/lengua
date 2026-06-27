import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Drive the real generate/save hooks against a mocked transport, and spy on the toast queue.
const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...actual, getApiClient: () => ({ POST: post }) };
});
const { toast } = vi.hoisted(() => ({ toast: vi.fn() }));
vi.mock('@/components/ui/use-toast', () => ({ toast }));

import {
  ActiveLanguageContext,
  type ActiveLanguageState,
} from '@/components/active-language-context';
import { handOffWords, takeHandedOffWords } from '@/lib/generate-handoff';
import type { LanguageOut } from '@/lib/languages';
import Generate from '@/pages/Generate';

const SPANISH: LanguageOut = {
  id: 1,
  name: 'Spanish',
  code: 'es',
  vowelized: false,
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

function failResult(
  status: number,
  code: string,
  retryAfter?: number,
): Promise<ApiResult> {
  const headers =
    retryAfter !== undefined
      ? { 'Retry-After': String(retryAfter) }
      : undefined;
  return Promise.resolve({
    data: undefined,
    error: { code, message: `failed: ${code}` },
    response: new Response(null, { status, headers }),
  });
}

function card(direction: string, front: string, back: string, used: string[]) {
  return {
    direction,
    front,
    back,
    used_words: used,
    word_explanations:
      direction === 'production' ? { [used[0]]: 'note' } : null,
    gen_level: null,
  };
}

// Two example sentences as the backend returns them: a recognition + production pair each.
const S1 = { sentence: 'Hola mundo', translation: 'Hello world', word: 'hola' };
const S2 = {
  sentence: 'Buenos dias',
  translation: 'Good morning',
  word: 'dias',
};
const TWO_SENTENCES = [
  card('recognition', S1.sentence, S1.translation, [S1.word]),
  card('production', S1.translation, S1.sentence, [S1.word]),
  card('recognition', S2.sentence, S2.translation, [S2.word]),
  card('production', S2.translation, S2.sentence, [S2.word]),
];

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
    ...overrides,
  };
}

function renderGenerate(value: ActiveLanguageState = makeValue()) {
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
          <Generate />
        </ActiveLanguageContext.Provider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function setWords(value: string) {
  fireEvent.change(screen.getByLabelText('Words'), { target: { value } });
}

function generateButton() {
  return screen.getByRole('button', { name: 'Generate' });
}

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  // The Discover → Generate handoff is module state; drain it so it never leaks between tests.
  takeHandedOffWords();
});

describe('Generate — language gating', () => {
  it('shows a loading state while languages load', () => {
    renderGenerate(
      makeValue({
        isLoading: true,
        activeLanguageId: null,
        activeLanguage: null,
      }),
    );
    expect(screen.getByText(/loading your languages/i)).toBeInTheDocument();
  });

  it('prompts to add a language when the user has none', () => {
    renderGenerate(makeValue({ activeLanguageId: null, activeLanguage: null }));
    expect(screen.getByText('Add a language first')).toBeInTheDocument();
    expect(
      screen.getByRole('link', { name: /add a language/i }),
    ).toHaveAttribute('href', '/languages');
  });

  it('names the active language in the intro copy', () => {
    renderGenerate();
    expect(
      screen.getByText(/example sentences in Spanish/i),
    ).toBeInTheDocument();
  });
});

describe('Generate — word form (4.5.1)', () => {
  it('disables Generate until at least one word is entered, then enables it', async () => {
    const user = userEvent.setup();
    renderGenerate();

    expect(generateButton()).toBeDisabled();
    expect(screen.getByText('0 / 30 words')).toBeInTheDocument();

    await user.type(screen.getByLabelText('Words'), 'casa');
    expect(generateButton()).toBeEnabled();
    expect(screen.getByText('1 / 30 words')).toBeInTheDocument();
  });

  it('warns and blocks generation past the per-request word cap', () => {
    renderGenerate();
    setWords(Array.from({ length: 31 }, (_, index) => `w${index}`).join(', '));

    expect(screen.getByRole('alert')).toHaveTextContent(/too many words/i);
    expect(screen.getByText('31 / 30 words')).toBeInTheDocument();
    expect(generateButton()).toBeDisabled();

    // Submitting anyway is a no-op (the handler guards the cap).
    fireEvent.submit(screen.getByLabelText('Words').closest('form')!);
    expect(post).not.toHaveBeenCalled();
  });

  it('blocks an empty submit', () => {
    renderGenerate();
    fireEvent.submit(screen.getByLabelText('Words').closest('form')!);
    expect(post).not.toHaveBeenCalled();
  });

  it('prefills the word input from a Discover → Generate handoff (consumed once)', () => {
    // Discover's "accept" stashes the suggested words; the Generate workspace picks them up on mount.
    handOffWords(['casa', 'perro']);
    renderGenerate();
    expect(screen.getByLabelText('Words')).toHaveValue('casa\nperro');
    // One-shot: the handoff was consumed, so nothing remains for the next mount.
    expect(takeHandedOffWords()).toBeNull();
  });
});

describe('Generate — generating + results (4.5.2)', () => {
  it('shows the in-progress state while generating', async () => {
    const user = userEvent.setup();
    let resolve!: (value: ApiResult) => void;
    post.mockReturnValue(
      new Promise<ApiResult>((res) => {
        resolve = res;
      }),
    );
    renderGenerate();

    await user.type(screen.getByLabelText('Words'), 'casa');
    await user.click(generateButton());

    expect(
      screen.getByRole('button', { name: /generating/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/this can take a few seconds/i),
    ).toBeInTheDocument();
    expect(screen.getByLabelText('Words')).toBeDisabled();

    resolve({
      data: TWO_SENTENCES,
      error: undefined,
      response: new Response(null, { status: 200 }),
    });
    expect(await screen.findByText(S1.sentence)).toBeInTheDocument();
  });

  it('renders each generated sentence with its translation and used-word chips', async () => {
    const user = userEvent.setup();
    post.mockReturnValue(okResult(TWO_SENTENCES));
    renderGenerate();

    await user.type(screen.getByLabelText('Words'), 'hola, dias');
    await user.click(generateButton());

    expect(await screen.findByText(S1.sentence)).toBeInTheDocument();
    expect(screen.getByText(S1.translation)).toBeInTheDocument();
    expect(screen.getByText(S2.sentence)).toBeInTheDocument();
    expect(screen.getByText(S2.translation)).toBeInTheDocument();
    // The used-word chips for both sentences render.
    expect(screen.getByText(S1.word)).toBeInTheDocument();
    expect(screen.getByText(S2.word)).toBeInTheDocument();
    expect(post).toHaveBeenCalledWith('/generate', {
      body: { language_id: 1, words: ['hola', 'dias'] },
    });
  });

  it('shows an empty state when nothing comes back, and returns to the form', async () => {
    const user = userEvent.setup();
    post.mockReturnValue(okResult([]));
    renderGenerate();

    await user.type(screen.getByLabelText('Words'), 'casa');
    await user.click(generateButton());

    expect(
      await screen.findByText(/no sentences generated/i),
    ).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: /back to words/i }));
    expect(screen.getByLabelText('Words')).toBeInTheDocument();
  });
});

describe('Generate — select & save (4.5.3)', () => {
  it('saves only the selected sentences and shows a success confirmation', async () => {
    const user = userEvent.setup();
    const savedCards = [{ id: 10 }, { id: 11 }];
    post.mockImplementation((path: string) =>
      path === '/generate' ? okResult(TWO_SENTENCES) : okResult(savedCards),
    );
    renderGenerate();

    await user.type(screen.getByLabelText('Words'), 'hola, dias');
    await user.click(generateButton());
    await screen.findByText(S1.sentence);

    // Both selected by default → "Save 2 sentences".
    expect(
      screen.getByRole('button', { name: 'Save 2 sentences' }),
    ).toBeInTheDocument();

    // Deselect sentence 2; only sentence 1 should be saved.
    await user.click(
      screen.getByRole('checkbox', {
        name: `Save this card — ${S2.translation}`,
      }),
    );
    expect(screen.getByText('1 of 2 selected')).toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'Save 1 sentence' }));

    const saveCall = post.mock.calls.find((call) => call[0] === '/cards/save');
    expect(saveCall).toBeDefined();
    const body = saveCall![1].body as { language_id: number; cards: unknown[] };
    expect(body.language_id).toBe(1);
    expect(body.cards).toHaveLength(2); // sentence 1's recognition + production
    const json = JSON.stringify(body.cards);
    expect(json).toContain(S1.sentence);
    expect(json).not.toContain(S2.sentence);

    expect(await screen.findByText('Saved 2 cards')).toBeInTheDocument();
    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Cards saved' }),
    );
  });

  it('toggles all selections off and on, gating Save when none are selected', async () => {
    const user = userEvent.setup();
    post.mockReturnValue(okResult(TWO_SENTENCES));
    renderGenerate();

    await user.type(screen.getByLabelText('Words'), 'hola, dias');
    await user.click(generateButton());
    await screen.findByText(S1.sentence);

    const selectAll = screen.getByRole('checkbox', {
      name: 'Select all sentences',
    });
    expect(selectAll).toBeChecked();

    await user.click(selectAll);
    expect(screen.getByText('0 of 2 selected')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /save 0/i })).toBeDisabled();

    await user.click(selectAll);
    expect(screen.getByText('2 of 2 selected')).toBeInTheDocument();
  });

  it('re-selects an individual sentence after deselecting it', async () => {
    const user = userEvent.setup();
    post.mockReturnValue(okResult(TWO_SENTENCES));
    renderGenerate();

    await user.type(screen.getByLabelText('Words'), 'hola, dias');
    await user.click(generateButton());
    await screen.findByText(S1.sentence);

    const checkbox = screen.getByRole('checkbox', {
      name: `Save this card — ${S2.translation}`,
    });
    await user.click(checkbox); // off
    expect(screen.getByText('1 of 2 selected')).toBeInTheDocument();
    await user.click(checkbox); // back on
    expect(screen.getByText('2 of 2 selected')).toBeInTheDocument();
  });

  it('shows a pending Saving… state while the save is in flight', async () => {
    const user = userEvent.setup();
    let resolveSave!: (value: ApiResult) => void;
    post.mockImplementation((path: string) =>
      path === '/generate'
        ? okResult(TWO_SENTENCES)
        : new Promise<ApiResult>((res) => {
            resolveSave = res;
          }),
    );
    renderGenerate();

    await user.type(screen.getByLabelText('Words'), 'hola, dias');
    await user.click(generateButton());
    await screen.findByText(S1.sentence);
    await user.click(screen.getByRole('button', { name: 'Save 2 sentences' }));

    const saving = await screen.findByRole('button', { name: /saving/i });
    expect(saving).toBeDisabled();

    resolveSave({
      data: [{ id: 1 }, { id: 2 }],
      error: undefined,
      response: new Response(null, { status: 200 }),
    });
    expect(await screen.findByText('Saved 2 cards')).toBeInTheDocument();
  });

  it('uses singular copy when a single card is saved', async () => {
    const user = userEvent.setup();
    post.mockImplementation((path: string) =>
      path === '/generate' ? okResult(TWO_SENTENCES) : okResult([{ id: 1 }]),
    );
    renderGenerate();

    await user.type(screen.getByLabelText('Words'), 'hola');
    await user.click(generateButton());
    await screen.findByText(S1.sentence);

    await user.click(screen.getByRole('button', { name: 'Save 2 sentences' }));
    expect(await screen.findByText('Saved 1 card')).toBeInTheDocument();
    // "Generate more" resets to an empty form.
    await user.click(screen.getByRole('button', { name: /generate more/i }));
    expect(screen.getByLabelText('Words')).toHaveValue('');
  });

  it('keeps the typed words when starting over from results', async () => {
    const user = userEvent.setup();
    post.mockReturnValue(okResult(TWO_SENTENCES));
    renderGenerate();

    await user.type(screen.getByLabelText('Words'), 'hola, dias');
    await user.click(generateButton());
    await screen.findByText(S1.sentence);

    await user.click(screen.getByRole('button', { name: /start over/i }));
    expect(screen.getByLabelText('Words')).toHaveValue('hola, dias');
  });

  it('surfaces a destructive toast and keeps the results when saving fails', async () => {
    const user = userEvent.setup();
    post.mockImplementation((path: string) =>
      path === '/generate' ? okResult(TWO_SENTENCES) : failResult(500, 'oops'),
    );
    renderGenerate();

    await user.type(screen.getByLabelText('Words'), 'hola, dias');
    await user.click(generateButton());
    await screen.findByText(S1.sentence);

    await user.click(screen.getByRole('button', { name: 'Save 2 sentences' }));

    await vi.waitFor(() =>
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({
          variant: 'destructive',
          title: 'Could not save cards',
        }),
      ),
    );
    // Still on the results view (not the saved confirmation).
    expect(screen.getByText('Review & save')).toBeInTheDocument();
  });
});

describe('Generate — friendly error states (4.5.4 + cost guard)', () => {
  it('renders the shared daily-limit panel for a quota 429, keeping the words', async () => {
    const user = userEvent.setup();
    post.mockReturnValue(failResult(429, 'daily_cap_reached'));
    renderGenerate();

    await user.type(screen.getByLabelText('Words'), 'casa, perro');
    await user.click(generateButton());

    expect(await screen.findByTestId('daily-limit-panel')).toBeInTheDocument();
    // NOT a generic error.
    expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument();
    // Typed words are preserved.
    expect(screen.getByLabelText('Words')).toHaveValue('casa, perro');
  });

  it('renders the daily-limit panel for the global kill-switch shape too', async () => {
    const user = userEvent.setup();
    post.mockReturnValue(failResult(429, 'daily_limit_reached'));
    renderGenerate();

    await user.type(screen.getByLabelText('Words'), 'casa');
    await user.click(generateButton());
    expect(await screen.findByTestId('daily-limit-panel')).toBeInTheDocument();
  });

  it('renders a friendly transient state for server_busy (not the daily panel)', async () => {
    const user = userEvent.setup();
    post.mockReturnValue(failResult(503, 'server_busy', 3));
    renderGenerate();

    await user.type(screen.getByLabelText('Words'), 'casa');
    await user.click(generateButton());

    expect(await screen.findByText('The server is busy')).toBeInTheDocument();
    expect(
      screen.getByText(/press Generate to try again/i),
    ).toBeInTheDocument();
    expect(screen.queryByTestId('daily-limit-panel')).not.toBeInTheDocument();
  });

  it('renders a friendly rate-limited state', async () => {
    const user = userEvent.setup();
    post.mockReturnValue(failResult(429, 'rate_limited', 2));
    renderGenerate();

    await user.type(screen.getByLabelText('Words'), 'casa');
    await user.click(generateButton());

    expect(await screen.findByText('Too many requests')).toBeInTheDocument();
  });

  it('renders a generic error for an unclassified failure', async () => {
    const user = userEvent.setup();
    post.mockReturnValue(failResult(500, 'kaboom'));
    renderGenerate();

    await user.type(screen.getByLabelText('Words'), 'casa');
    await user.click(generateButton());

    const alert = await screen.findByRole('alert');
    expect(within(alert).getByText('Something went wrong')).toBeInTheDocument();
  });
});
