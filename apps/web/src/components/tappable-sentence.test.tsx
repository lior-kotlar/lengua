import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Drive the real explain query against a mocked transport.
const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...actual, getApiClient: () => ({ POST: post }) };
});

import { TappableSentence } from '@/components/tappable-sentence';

interface ApiResult {
  data: unknown;
  error: unknown;
  response: Response;
}

function okResult(data: unknown): Promise<ApiResult> {
  return Promise.resolve({
    data,
    error: undefined,
    response: new Response(null, { status: 200 }),
  });
}

function failResult(status: number, code: string): Promise<ApiResult> {
  return Promise.resolve({
    data: undefined,
    error: { code, message: `failed: ${code}` },
    response: new Response(null, { status }),
  });
}

const SENTENCE = 'El gato duerme en la silla.';
const TRANSLATION = 'The cat sleeps on the chair.';

function renderSentence(
  props: Partial<React.ComponentProps<typeof TappableSentence>> = {},
) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <TappableSentence
        text={SENTENCE}
        translation={TRANSLATION}
        language={{ id: 2, code: 'es' }}
        explanations={null}
        showVowels={true}
        {...props}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('TappableSentence — rendering', () => {
  it('renders each word as a button and preserves the full sentence text', () => {
    const { container } = renderSentence();
    // Every meaningful word is a button (the trailing "." is part of "silla." → bare "silla").
    expect(screen.getByRole('button', { name: 'gato' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'silla.' })).toBeInTheDocument();
    // The visible text reproduces the sentence exactly (spacing + punctuation preserved).
    expect(container.textContent).toBe(SENTENCE);
  });
});

describe('TappableSentence — tap to explain (4.6.4)', () => {
  it('opens a popover with the fetched explanation and sends word + language', async () => {
    const user = userEvent.setup();
    post.mockReturnValue(
      okResult({ word: 'silla', explanation: 'a piece of furniture' }),
    );
    renderSentence();

    await user.click(screen.getByRole('button', { name: 'silla.' }));

    const popover = await screen.findByTestId('word-popover');
    expect(
      await within(popover).findByText('a piece of furniture'),
    ).toBeInTheDocument();
    // The bare word (punctuation stripped) and the active language are sent.
    expect(post).toHaveBeenCalledWith('/explain', {
      body: {
        language_id: 2,
        word: 'silla',
        sentence: SENTENCE,
        translation: TRANSLATION,
      },
    });
  });

  it('shows a loading state before the explanation resolves', async () => {
    const user = userEvent.setup();
    let resolve!: (value: ApiResult) => void;
    post.mockReturnValue(
      new Promise<ApiResult>((res) => {
        resolve = res;
      }),
    );
    renderSentence();

    await user.click(screen.getByRole('button', { name: 'gato' }));
    expect(await screen.findByText('Explaining…')).toBeInTheDocument();

    resolve({
      data: { word: 'gato', explanation: 'cat' },
      error: undefined,
      response: new Response(null, { status: 200 }),
    });
    expect(await screen.findByText('cat')).toBeInTheDocument();
  });

  it('serves a pre-generated card note instantly, without any request', async () => {
    const user = userEvent.setup();
    renderSentence({ explanations: { silla: 'a chair (from the card)' } });

    await user.click(screen.getByRole('button', { name: 'silla.' }));

    expect(
      await screen.findByText('a chair (from the card)'),
    ).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('renders a friendly message when the explanation request fails', async () => {
    const user = userEvent.setup();
    post.mockReturnValue(failResult(503, 'server_busy'));
    renderSentence();

    await user.click(screen.getByRole('button', { name: 'gato' }));
    expect(
      await screen.findByText(/couldn.t load an explanation/i),
    ).toBeInTheDocument();
  });
});

describe('TappableSentence — dismissal', () => {
  async function open() {
    const user = userEvent.setup();
    post.mockReturnValue(okResult({ word: 'gato', explanation: 'cat' }));
    renderSentence();
    await user.click(screen.getByRole('button', { name: 'gato' }));
    await screen.findByTestId('word-popover');
    return user;
  }

  it('toggles closed when the same word is tapped again', async () => {
    const user = await open();
    await user.click(screen.getByRole('button', { name: 'gato' }));
    expect(screen.queryByTestId('word-popover')).not.toBeInTheDocument();
  });

  it('closes via the close button', async () => {
    const user = await open();
    await user.click(
      screen.getByRole('button', { name: /close explanation/i }),
    );
    expect(screen.queryByTestId('word-popover')).not.toBeInTheDocument();
  });

  it('closes on Escape', async () => {
    const user = await open();
    await user.keyboard('{Escape}');
    expect(screen.queryByTestId('word-popover')).not.toBeInTheDocument();
  });

  it('closes when pointing down outside the sentence', async () => {
    await open();
    fireEvent.pointerDown(document.body);
    expect(screen.queryByTestId('word-popover')).not.toBeInTheDocument();
  });

  it('switches the popover to another word when a second word is tapped', async () => {
    const user = await open();
    post.mockReturnValue(okResult({ word: 'silla', explanation: 'chair' }));
    await user.click(screen.getByRole('button', { name: 'silla.' }));

    const popover = await screen.findByTestId('word-popover');
    // The popover now describes the new word.
    expect(within(popover).getByText('silla')).toBeInTheDocument();
  });
});

describe('TappableSentence — RTL (4.9.4)', () => {
  it('derives RTL + the Hebrew font from the language code and anchors the popover to the right', async () => {
    const user = userEvent.setup();
    post.mockReturnValue(okResult({ word: 'بيت', explanation: 'a house' }));
    renderSentence({
      text: 'هذا بيت كبير',
      translation: 'This is a big house',
      language: { id: 3, code: 'ar' },
    });

    // The sentence region is RTL and uses the Arabic script font.
    const paragraph = screen.getByRole('button', { name: 'هذا' }).closest('p');
    expect(paragraph).toHaveAttribute('dir', 'rtl');
    expect(paragraph?.className).toContain('font-arabic');

    // Tapping a word MID-sentence opens that exact word's popover (not a neighbour).
    await user.click(screen.getByRole('button', { name: 'بيت' }));
    const popover = await screen.findByTestId('word-popover');
    expect(popover).toHaveAttribute('dir', 'rtl');
    expect(popover.className).toContain('right-0');
    expect(post).toHaveBeenCalledWith('/explain', {
      body: {
        language_id: 3,
        word: 'بيت',
        sentence: 'هذا بيت كبير',
        translation: 'This is a big house',
      },
    });
  });
});

describe('TappableSentence — vowel-marks toggle (4.9.3)', () => {
  // Hebrew "שָׁלוֹם עוֹלָם" (with nikkud) → bare "שלום עולם".
  const VOWELIZED = 'שָׁלוֹם עוֹלָם';
  const BARE_FIRST = 'שלום';
  const VOWELIZED_FIRST = 'שָׁלוֹם';

  it('shows the marks when on, and the looked-up word still carries them', async () => {
    const user = userEvent.setup();
    post.mockReturnValue(
      okResult({ word: VOWELIZED_FIRST, explanation: 'hi' }),
    );
    renderSentence({
      text: VOWELIZED,
      translation: 'hello world',
      language: { id: 3, code: 'he' },
      showVowels: true,
    });

    await user.click(screen.getByRole('button', { name: VOWELIZED_FIRST }));
    expect(post).toHaveBeenCalledWith(
      '/explain',
      expect.objectContaining({
        body: expect.objectContaining({ word: VOWELIZED_FIRST }),
      }),
    );
  });

  it('strips the marks from the GLYPHS when off but looks up the canonical word', async () => {
    const user = userEvent.setup();
    renderSentence({
      text: VOWELIZED,
      translation: 'hello world',
      language: { id: 3, code: 'he' },
      showVowels: false,
      // Pre-generated note keyed by the canonical word (WITH marks) — must still match.
      explanations: { [VOWELIZED_FIRST]: 'a greeting' },
    });

    // The visible word is stripped …
    const button = screen.getByRole('button', { name: BARE_FIRST });
    expect(screen.queryByRole('button', { name: VOWELIZED_FIRST })).toBeNull();

    // … but tapping it serves the pre-generated note (keyed by the diacritized word) — no request.
    await user.click(button);
    expect(await screen.findByText('a greeting')).toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });
});
