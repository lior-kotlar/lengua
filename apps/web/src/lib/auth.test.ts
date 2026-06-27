import { AuthApiError } from '@supabase/supabase-js';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { auth } = vi.hoisted(() => ({
  auth: {
    signUp: vi.fn(),
    signInWithPassword: vi.fn(),
    signInWithOAuth: vi.fn(),
    resetPasswordForEmail: vi.fn(),
    updateUser: vi.fn(),
    resend: vi.fn(),
    signOut: vi.fn(),
    getSession: vi.fn(),
  },
}));

vi.mock('@/lib/supabase', () => ({ getSupabaseClient: () => ({ auth }) }));

import {
  getCurrentSession,
  mapAuthError,
  readAuthRedirectError,
  requestPasswordReset,
  resendVerificationEmail,
  signInWithEmail,
  signInWithProvider,
  signOut,
  signOutLocal,
  signUpWithEmail,
  updatePassword,
} from '@/lib/auth';

const ok = { data: { session: null, user: null }, error: null };

beforeEach(() => {
  vi.clearAllMocks();
  auth.signUp.mockResolvedValue(ok);
  auth.signInWithPassword.mockResolvedValue(ok);
  auth.signInWithOAuth.mockResolvedValue({ data: {}, error: null });
  auth.resetPasswordForEmail.mockResolvedValue({ data: {}, error: null });
  auth.updateUser.mockResolvedValue({ data: { user: null }, error: null });
  auth.resend.mockResolvedValue({ data: {}, error: null });
  auth.signOut.mockResolvedValue({ error: null });
  auth.getSession.mockResolvedValue({ data: { session: null }, error: null });
});

const origin = window.location.origin;

describe('signUpWithEmail', () => {
  it('flags needsVerification when no session is returned', async () => {
    const result = await signUpWithEmail('user@example.com', 'Abcdef12');
    expect(result.error).toBeNull();
    expect(result.needsVerification).toBe(true);
    expect(auth.signUp).toHaveBeenCalledWith({
      email: 'user@example.com',
      password: 'Abcdef12',
      options: { emailRedirectTo: `${origin}/auth/callback` },
    });
  });

  it('does not flag needsVerification when a session is returned', async () => {
    auth.signUp.mockResolvedValue({
      data: { session: { access_token: 't' }, user: { id: 'u' } },
      error: null,
    });
    const result = await signUpWithEmail('user@example.com', 'Abcdef12');
    expect(result.needsVerification).toBe(false);
  });

  it('maps an error and reports no verification', async () => {
    auth.signUp.mockResolvedValue({
      data: { session: null, user: null },
      error: new AuthApiError('exists', 422, 'user_already_exists'),
    });
    const result = await signUpWithEmail('user@example.com', 'Abcdef12');
    expect(result.error).toMatch(/already exists/i);
    expect(result.needsVerification).toBe(false);
  });
});

describe('signInWithEmail', () => {
  it('returns no error on success', async () => {
    expect(await signInWithEmail('user@example.com', 'Abcdef12')).toEqual({
      error: null,
    });
  });

  it('maps invalid credentials', async () => {
    auth.signInWithPassword.mockResolvedValue({
      data: ok.data,
      error: new AuthApiError('bad', 400, 'invalid_credentials'),
    });
    const result = await signInWithEmail('user@example.com', 'x');
    expect(result.error).toMatch(/incorrect email or password/i);
    expect(result.code).toBe('invalid_credentials');
  });
});

describe('signInWithProvider', () => {
  it('calls signInWithOAuth with provider + web-origin redirect', async () => {
    expect(await signInWithProvider('google')).toEqual({ error: null });
    expect(auth.signInWithOAuth).toHaveBeenCalledWith({
      provider: 'google',
      options: { redirectTo: `${origin}/auth/callback` },
    });
  });

  it('maps an error', async () => {
    auth.signInWithOAuth.mockResolvedValue({
      data: {},
      error: new AuthApiError('nope', 400, 'validation_failed'),
    });
    expect((await signInWithProvider('apple')).error).toBeTruthy();
  });
});

describe('requestPasswordReset', () => {
  it('sends with the reset redirect URL', async () => {
    expect(await requestPasswordReset('user@example.com')).toEqual({
      error: null,
    });
    expect(auth.resetPasswordForEmail).toHaveBeenCalledWith(
      'user@example.com',
      {
        redirectTo: `${origin}/reset-password`,
      },
    );
  });

  it('maps an error', async () => {
    auth.resetPasswordForEmail.mockResolvedValue({
      data: {},
      error: new AuthApiError('slow down', 429, 'over_email_send_rate_limit'),
    });
    expect((await requestPasswordReset('user@example.com')).error).toMatch(
      /too many attempts/i,
    );
  });
});

describe('updatePassword', () => {
  it('updates the user password', async () => {
    expect(await updatePassword('Abcdef12')).toEqual({ error: null });
    expect(auth.updateUser).toHaveBeenCalledWith({ password: 'Abcdef12' });
  });

  it('maps a same-password error', async () => {
    auth.updateUser.mockResolvedValue({
      data: { user: null },
      error: new AuthApiError('same', 422, 'same_password'),
    });
    expect((await updatePassword('Abcdef12')).error).toMatch(/different/i);
  });
});

describe('resendVerificationEmail', () => {
  it('resends a signup verification', async () => {
    expect(await resendVerificationEmail('user@example.com')).toEqual({
      error: null,
    });
    expect(auth.resend).toHaveBeenCalledWith({
      type: 'signup',
      email: 'user@example.com',
      options: { emailRedirectTo: `${origin}/auth/callback` },
    });
  });

  it('maps an error', async () => {
    auth.resend.mockResolvedValue({
      data: {},
      error: new AuthApiError('expired', 401, 'otp_expired'),
    });
    expect((await resendVerificationEmail('x@y.com')).error).toMatch(
      /expired/i,
    );
  });
});

describe('signOut + getCurrentSession', () => {
  it('signs out', async () => {
    expect(await signOut()).toEqual({ error: null });
    expect(auth.signOut).toHaveBeenCalled();
  });

  it('maps a sign-out error', async () => {
    auth.signOut.mockResolvedValue({
      error: new AuthApiError('boom', 500, 'unexpected_failure'),
    });
    expect((await signOut()).error).toBeTruthy();
  });

  it('signs out LOCALLY (no network logout) for the post-delete teardown', async () => {
    expect(await signOutLocal()).toEqual({ error: null });
    expect(auth.signOut).toHaveBeenCalledWith({ scope: 'local' });
  });

  it('maps a local sign-out error', async () => {
    auth.signOut.mockResolvedValue({
      error: new AuthApiError('boom', 500, 'unexpected_failure'),
    });
    expect((await signOutLocal()).error).toBeTruthy();
  });

  it('reads the current session', async () => {
    auth.getSession.mockResolvedValue({
      data: { session: { access_token: 't' } },
      error: null,
    });
    expect(await getCurrentSession()).toEqual({ access_token: 't' });
  });
});

describe('mapAuthError', () => {
  it('maps known codes to friendly messages', () => {
    const cases: Array<[string, RegExp]> = [
      ['invalid_credentials', /incorrect/i],
      ['email_not_confirmed', /verify your email/i],
      ['email_exists', /already exists/i],
      ['signup_disabled', /disabled/i],
      ['over_request_rate_limit', /too many/i],
    ];
    for (const [code, re] of cases) {
      expect(mapAuthError(new AuthApiError('m', 400, code)).error).toMatch(re);
    }
  });

  it('falls back to the raw message for unknown codes, then a generic one', () => {
    expect(
      mapAuthError(new AuthApiError('Custom msg', 400, 'something_new')).error,
    ).toBe('Custom msg');
    // Empty message → generic fallback.
    expect(
      mapAuthError(new AuthApiError('', 400, 'something_new')).error,
    ).toMatch(/something went wrong/i);
  });

  it('uses the policy fallback when weak_password has no message', () => {
    expect(
      mapAuthError(new AuthApiError('', 400, 'weak_password')).error,
    ).toMatch(/too weak/i);
  });

  it('returns a generic message for non-auth errors', () => {
    expect(mapAuthError(new Error('plain')).error).toMatch(
      /something went wrong/i,
    );
    expect(mapAuthError('weird').code).toBeUndefined();
  });
});

describe('readAuthRedirectError', () => {
  it('returns null when there is no error', () => {
    expect(readAuthRedirectError('http://localhost/auth/callback')).toBeNull();
  });

  it('parses an error from the query string', () => {
    const result = readAuthRedirectError(
      'http://localhost/auth/callback?error=access_denied&error_code=otp_expired&error_description=Link%20expired',
    );
    expect(result).toEqual({
      code: 'otp_expired',
      description: 'Link expired',
    });
  });

  it('parses an error from the URL hash and falls back to the generic code', () => {
    const result = readAuthRedirectError(
      'http://localhost/reset-password#error=access_denied',
    );
    expect(result).toEqual({ code: 'access_denied', description: null });
  });
});
