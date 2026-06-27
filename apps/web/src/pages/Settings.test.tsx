import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Drive the real settings hooks against a mocked transport (GET + PUT /settings).
const { get, put } = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }));
vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...actual, getApiClient: () => ({ GET: get, PUT: put }) };
});
const { toast } = vi.hoisted(() => ({ toast: vi.fn() }));
vi.mock('@/components/ui/use-toast', () => ({ toast }));

import Settings from '@/pages/Settings';

interface ApiResult {
  data: unknown;
  error: unknown;
  response: Response;
}

function ok(data: unknown, status = 200): Promise<ApiResult> {
  return Promise.resolve({
    data,
    error: undefined,
    response: new Response(null, { status }),
  });
}

function fail(status: number): Promise<ApiResult> {
  return Promise.resolve({
    data: undefined,
    error: { detail: 'boom' },
    response: new Response(null, { status }),
  });
}

function renderSettings() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <Settings />
    </QueryClientProvider>,
  );
}

function newCardsInput() {
  return screen.getByLabelText('Daily new cards');
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe('Settings — load states', () => {
  it('shows a loading state while settings load', () => {
    get.mockReturnValue(new Promise<ApiResult>(() => {}));
    renderSettings();
    expect(screen.getByText(/loading your settings/i)).toBeInTheDocument();
  });

  it('shows a retryable error state when the load fails', async () => {
    const user = userEvent.setup();
    get
      .mockReturnValueOnce(fail(500))
      .mockReturnValue(ok({ values: { daily_new_limit: '20' } }));
    renderSettings();

    expect(
      await screen.findByText('Could not load your settings'),
    ).toBeInTheDocument();

    // Retry refetches and reveals the form.
    await user.click(screen.getByRole('button', { name: /retry/i }));
    expect(await screen.findByLabelText('Daily new cards')).toHaveValue(20);
    expect(get).toHaveBeenCalledTimes(2);
  });
});

describe('Settings — form seeding', () => {
  it('seeds each field from the saved value, falling back to defaults when unset', async () => {
    get.mockReturnValue(
      ok({ values: { daily_new_limit: '20', discover_count: '8' } }),
    );
    renderSettings();

    expect(await screen.findByLabelText('Daily new cards')).toHaveValue(20);
    // daily_total_limit is unset → its default (50).
    expect(screen.getByLabelText('Daily total cards')).toHaveValue(50);
    expect(screen.getByLabelText('Discover word count')).toHaveValue(8);
  });
});

describe('Settings — validation (client bounds)', () => {
  beforeEach(() => {
    get.mockReturnValue(ok({ values: {} }));
  });

  it('blocks save and shows an inline error for an out-of-bounds value', async () => {
    renderSettings();
    await screen.findByLabelText('Daily new cards');

    fireEvent.change(newCardsInput(), { target: { value: '0' } });
    expect(screen.getByText('Must be between 1 and 100.')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /save settings/i }),
    ).toBeDisabled();

    // A blank value is invalid too.
    fireEvent.change(newCardsInput(), { target: { value: '' } });
    expect(screen.getByText('Enter a value.')).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /save settings/i }),
    ).toBeDisabled();

    // Back in range re-enables save and clears the error.
    fireEvent.change(newCardsInput(), { target: { value: '12' } });
    expect(
      screen.queryByText('Must be between 1 and 100.'),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /save settings/i }),
    ).toBeEnabled();
  });

  it('does not PUT when the form is submitted with an invalid value', async () => {
    renderSettings();
    await screen.findByLabelText('Daily new cards');
    fireEvent.change(newCardsInput(), { target: { value: '999' } });
    fireEvent.submit(newCardsInput().closest('form')!);
    expect(put).not.toHaveBeenCalled();
  });
});

describe('Settings — save', () => {
  it('PUTs all fields (normalized) and toasts on success', async () => {
    const user = userEvent.setup();
    get.mockReturnValue(
      ok({
        values: {
          daily_new_limit: '20',
          daily_total_limit: '50',
          discover_count: '8',
        },
      }),
    );
    put.mockReturnValue(
      ok({
        values: {
          daily_new_limit: '15',
          daily_total_limit: '50',
          discover_count: '8',
        },
      }),
    );
    renderSettings();
    await screen.findByLabelText('Daily new cards');

    fireEvent.change(newCardsInput(), { target: { value: '15' } });
    await user.click(screen.getByRole('button', { name: /save settings/i }));

    expect(put).toHaveBeenCalledWith('/settings', {
      body: {
        values: {
          daily_new_limit: '15',
          daily_total_limit: '50',
          discover_count: '8',
        },
      },
    });
    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Settings saved' }),
    );
  });

  it('shows a saving state while the save is in flight', async () => {
    const user = userEvent.setup();
    get.mockReturnValue(ok({ values: {} }));
    put.mockReturnValue(new Promise<ApiResult>(() => {})); // never resolves
    renderSettings();
    await screen.findByLabelText('Daily new cards');

    await user.click(screen.getByRole('button', { name: /save settings/i }));

    expect(
      await screen.findByRole('button', { name: /saving/i }),
    ).toBeDisabled();

    // A second submit while the save is in flight must not fire a second PUT.
    fireEvent.submit(newCardsInput().closest('form')!);
    expect(put).toHaveBeenCalledTimes(1);
  });

  it('toasts a destructive error when the save fails', async () => {
    const user = userEvent.setup();
    get.mockReturnValue(ok({ values: {} }));
    put.mockReturnValue(fail(500));
    renderSettings();
    await screen.findByLabelText('Daily new cards');

    await user.click(screen.getByRole('button', { name: /save settings/i }));

    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({ variant: 'destructive' }),
    );
  });
});
