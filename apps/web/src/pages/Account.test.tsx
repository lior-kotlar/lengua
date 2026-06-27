import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';

// Mock the transport (GET /account/export, DELETE /account) — keep the real unwrap/ApiError.
const { get, del } = vi.hoisted(() => ({ get: vi.fn(), del: vi.fn() }));
vi.mock('@/lib/api-client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api-client')>();
  return { ...actual, getApiClient: () => ({ GET: get, DELETE: del }) };
});
// Keep the real export/delete hooks; stub only the file-download side effect so we can assert it.
const { downloadJson } = vi.hoisted(() => ({ downloadJson: vi.fn() }));
vi.mock('@/lib/account', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/account')>();
  return { ...actual, downloadJson };
});
const { useAuth } = vi.hoisted(() => ({ useAuth: vi.fn() }));
vi.mock('@/components/auth-context', () => ({ useAuth }));
const { signOut } = vi.hoisted(() => ({ signOut: vi.fn() }));
vi.mock('@/lib/auth', () => ({ signOut }));
const { toast } = vi.hoisted(() => ({ toast: vi.fn() }));
vi.mock('@/components/ui/use-toast', () => ({ toast }));

import Account from '@/pages/Account';

function ok(data: unknown, status = 200) {
  return Promise.resolve({
    data,
    error: undefined,
    response: new Response(null, { status }),
  });
}

function fail(status: number) {
  return Promise.resolve({
    data: undefined,
    error: { detail: 'boom' },
    response: new Response(null, { status }),
  });
}

const EXPORT_BUNDLE = {
  profile: { id: 'u1', plan: 'free', created_at: '2026-01-01T00:00:00Z' },
  languages: [],
  cards: [],
  reviews: [],
  proficiency: [],
  settings: {},
};

function renderAccount() {
  const queryClient = new QueryClient({
    defaultOptions: { mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={['/account']}>
        <Account />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  useAuth.mockReturnValue({
    user: { email: 'demo@lengua.test' },
    session: {},
    loading: false,
  });
  signOut.mockResolvedValue({ error: null });
});

describe('Account — profile', () => {
  it('shows the signed-in email', () => {
    renderAccount();
    expect(screen.getByTestId('account-email')).toHaveTextContent(
      'demo@lengua.test',
    );
  });

  it('falls back to a not-signed-in label when there is no user', () => {
    useAuth.mockReturnValue({ user: null, session: null, loading: false });
    renderAccount();
    expect(screen.getByTestId('account-email')).toHaveTextContent(
      'Not signed in',
    );
  });

  it('signs out from the profile card', async () => {
    const user = userEvent.setup();
    renderAccount();
    await user.click(screen.getByRole('button', { name: /sign out/i }));
    await waitFor(() => expect(signOut).toHaveBeenCalledTimes(1));
  });
});

describe('Account — data export (4.8.2)', () => {
  it('GETs /account/export and downloads the bundle as JSON', async () => {
    const user = userEvent.setup();
    get.mockReturnValue(ok(EXPORT_BUNDLE));
    renderAccount();

    await user.click(screen.getByRole('button', { name: /export my data/i }));

    await waitFor(() =>
      expect(downloadJson).toHaveBeenCalledWith(
        'lengua-export.json',
        EXPORT_BUNDLE,
      ),
    );
    expect(get).toHaveBeenCalledWith('/account/export');
    expect(toast).toHaveBeenCalledWith(
      expect.objectContaining({ title: 'Export ready' }),
    );
  });

  it('shows a preparing state while the export is in flight', async () => {
    const user = userEvent.setup();
    get.mockReturnValue(new Promise(() => {})); // never resolves
    renderAccount();

    await user.click(screen.getByRole('button', { name: /export my data/i }));

    expect(
      await screen.findByRole('button', { name: /preparing/i }),
    ).toBeDisabled();
  });

  it('toasts a destructive error and does not download when export fails', async () => {
    const user = userEvent.setup();
    get.mockReturnValue(fail(500));
    renderAccount();

    await user.click(screen.getByRole('button', { name: /export my data/i }));

    await waitFor(() =>
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({ variant: 'destructive' }),
      ),
    );
    expect(downloadJson).not.toHaveBeenCalled();
  });
});

describe('Account — delete (4.8.3)', () => {
  it('renders the delete-account trigger (opens the confirm dialog, never deletes on render)', () => {
    renderAccount();
    expect(
      screen.getByRole('button', { name: 'Delete account' }),
    ).toBeInTheDocument();
    expect(del).not.toHaveBeenCalled();
  });
});
