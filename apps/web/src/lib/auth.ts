/**
 * Auth operations — the single seam over `supabase-js` for sign-up / log-in / OAuth / password
 * reset / sign-out.
 *
 * Supabase is AUTH ONLY (sessions, tokens, OAuth); all application data goes through the typed API
 * client. Screens call these helpers instead of touching `supabase.auth.*` directly so that:
 *  - redirect URLs (email-verification + OAuth landing, password-reset) are constructed in ONE place
 *    from the current web origin (works in dev :5173, preview :4173, and prod), and
 *  - raw GoTrue errors are normalized to friendly, code-tagged {@link AuthResult}s the UI can branch
 *    on (e.g. surface a "resend verification" CTA for `email_not_confirmed`).
 */
import {
  isAuthError,
  type Provider,
  type Session,
} from '@supabase/supabase-js';

import { getSupabaseClient } from '@/lib/supabase';

/** Route that consumes the email-verification + OAuth redirect (see `AuthCallback`). */
export const AUTH_CALLBACK_PATH = '/auth/callback';
/** Route that consumes the password-recovery redirect (see `ResetPassword`). */
export const RESET_PASSWORD_PATH = '/reset-password';

/** Absolute URL (current origin + path) used for Supabase redirects. */
function originUrl(path: string): string {
  return new URL(path, window.location.origin).toString();
}

/** The result of an auth operation: a friendly `error` message + the raw GoTrue `code` (or null). */
export interface AuthResult {
  /** A user-facing error message, or `null` on success. */
  error: string | null;
  /** The machine-readable GoTrue error code, when the call failed (for UI branching). */
  code?: string;
}

/** Sign-up result, extended with whether the user must still verify their email. */
export interface SignUpResult extends AuthResult {
  /** True when no session was returned (the normal "confirm your email first" path). */
  needsVerification: boolean;
}

/**
 * Normalize an unknown thrown/returned auth error into a friendly message + code.
 *
 * Maps the GoTrue error codes we care about; falls back to the raw message, then a generic line.
 */
export function mapAuthError(error: unknown): AuthResult {
  if (!isAuthError(error)) {
    return {
      error: 'Something went wrong. Please try again.',
      code: undefined,
    };
  }

  const code = error.code;
  switch (code) {
    case 'invalid_credentials':
      return { error: 'Incorrect email or password.', code };
    case 'email_not_confirmed':
      return {
        error: 'Please verify your email address before signing in.',
        code,
      };
    case 'email_exists':
    case 'user_already_exists':
      return { error: 'An account with this email already exists.', code };
    case 'weak_password':
      return {
        error:
          error.message ||
          'Password is too weak — use at least 8 characters with a mix of cases and a number.',
        code,
      };
    case 'same_password':
      return {
        error: 'Your new password must be different from the old one.',
        code,
      };
    case 'over_email_send_rate_limit':
    case 'over_request_rate_limit':
      return {
        error: 'Too many attempts. Please wait a moment and try again.',
        code,
      };
    case 'signup_disabled':
      return { error: 'Sign-ups are currently disabled.', code };
    case 'otp_expired':
      return {
        error: 'This link has expired. Please request a new one.',
        code,
      };
    default:
      return {
        error: error.message || 'Something went wrong. Please try again.',
        code,
      };
  }
}

/** Create an account with email + password; sends a verification email. */
export async function signUpWithEmail(
  email: string,
  password: string,
): Promise<SignUpResult> {
  const { data, error } = await getSupabaseClient().auth.signUp({
    email,
    password,
    options: { emailRedirectTo: originUrl(AUTH_CALLBACK_PATH) },
  });
  if (error) {
    return { ...mapAuthError(error), needsVerification: false };
  }
  // With email confirmation required, a successful sign-up returns no session.
  return { error: null, needsVerification: data.session === null };
}

/** Sign in with email + password. On success Supabase persists the session (auth state updates). */
export async function signInWithEmail(
  email: string,
  password: string,
): Promise<AuthResult> {
  const { error } = await getSupabaseClient().auth.signInWithPassword({
    email,
    password,
  });
  return error ? mapAuthError(error) : { error: null };
}

/** Start an OAuth sign-in; `supabase-js` redirects the browser to the provider. */
export async function signInWithProvider(
  provider: Provider,
): Promise<AuthResult> {
  const { error } = await getSupabaseClient().auth.signInWithOAuth({
    provider,
    options: { redirectTo: originUrl(AUTH_CALLBACK_PATH) },
  });
  return error ? mapAuthError(error) : { error: null };
}

/** Send a password-reset email that lands on the reset-with-token screen. */
export async function requestPasswordReset(email: string): Promise<AuthResult> {
  const { error } = await getSupabaseClient().auth.resetPasswordForEmail(
    email,
    {
      redirectTo: originUrl(RESET_PASSWORD_PATH),
    },
  );
  return error ? mapAuthError(error) : { error: null };
}

/** Set a new password for the user in the current (recovery) session. */
export async function updatePassword(password: string): Promise<AuthResult> {
  const { error } = await getSupabaseClient().auth.updateUser({ password });
  return error ? mapAuthError(error) : { error: null };
}

/** Resend the sign-up verification email. */
export async function resendVerificationEmail(
  email: string,
): Promise<AuthResult> {
  const { error } = await getSupabaseClient().auth.resend({
    type: 'signup',
    email,
    options: { emailRedirectTo: originUrl(AUTH_CALLBACK_PATH) },
  });
  return error ? mapAuthError(error) : { error: null };
}

/** Sign out — clears the persisted Supabase session (fires a SIGNED_OUT auth event). */
export async function signOut(): Promise<AuthResult> {
  const { error } = await getSupabaseClient().auth.signOut();
  return error ? mapAuthError(error) : { error: null };
}

/** Read the current session (used by the auth context bootstrap). */
export async function getCurrentSession(): Promise<Session | null> {
  const { data } = await getSupabaseClient().auth.getSession();
  return data.session;
}

/** An error returned to the web app via an auth redirect (verification / recovery / OAuth). */
export interface AuthRedirectError {
  /** The specific error code (e.g. `otp_expired`), or the generic `error` when none is given. */
  code: string;
  /** A human-readable description from the provider, when present. */
  description: string | null;
}

/**
 * Parse an auth error out of a redirect URL, or return `null` when there is none.
 *
 * GoTrue reports failures either in the query string (PKCE flow) or the URL hash (implicit flow),
 * e.g. `#error=access_denied&error_code=otp_expired&error_description=...`. We check both.
 */
export function readAuthRedirectError(
  href: string = window.location.href,
): AuthRedirectError | null {
  const url = new URL(href);
  const hash = url.hash.startsWith('#') ? url.hash.slice(1) : url.hash;
  const hashParams = new URLSearchParams(hash);
  const error = url.searchParams.get('error') ?? hashParams.get('error');
  if (error === null) {
    return null;
  }
  const code =
    url.searchParams.get('error_code') ?? hashParams.get('error_code') ?? error;
  const description =
    url.searchParams.get('error_description') ??
    hashParams.get('error_description');
  return { code, description };
}
