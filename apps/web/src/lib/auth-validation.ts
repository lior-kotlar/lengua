/**
 * Client-side auth form validation.
 *
 * These mirror the Supabase Auth policy configured in `supabase/config.toml`
 * (`minimum_password_length = 8`, `password_requirements = "lower_upper_letters_digits"`) so the
 * user gets immediate, friendly feedback instead of a round-trip + a raw GoTrue error. The server
 * remains the source of truth — these checks are a UX convenience, never a security boundary.
 */

/** Minimum password length — keep in lockstep with `minimum_password_length` in config.toml. */
export const MIN_PASSWORD_LENGTH = 8;

/** A permissive e-mail shape check (real validation is "did the verification mail arrive"). */
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Validate an e-mail address; returns an error message or `null` when valid. */
export function validateEmail(email: string): string | null {
  const trimmed = email.trim();
  if (trimmed === '') {
    return 'Enter your email address.';
  }
  if (!EMAIL_RE.test(trimmed)) {
    return 'Enter a valid email address.';
  }
  return null;
}

/**
 * Validate a password against the server policy (length + lower + upper + digit).
 *
 * Returns an error message or `null` when valid.
 */
export function validatePassword(password: string): string | null {
  if (password.length < MIN_PASSWORD_LENGTH) {
    return `Password must be at least ${MIN_PASSWORD_LENGTH} characters.`;
  }
  if (!/[a-z]/.test(password)) {
    return 'Password must include a lowercase letter.';
  }
  if (!/[A-Z]/.test(password)) {
    return 'Password must include an uppercase letter.';
  }
  if (!/[0-9]/.test(password)) {
    return 'Password must include a number.';
  }
  return null;
}

/** Fields validated on the sign-up / reset forms. */
export interface CredentialFields {
  email?: string;
  password?: string;
  confirmPassword?: string;
}

/** Per-field validation errors (only present keys failed). */
export type CredentialErrors = Partial<Record<keyof CredentialFields, string>>;

/**
 * Validate a set of credential fields. Only the fields present in `fields` are checked, so the same
 * helper serves login (email+password), sign-up (email+password+confirm) and reset (password+confirm).
 */
export function validateCredentials(
  fields: CredentialFields,
): CredentialErrors {
  const errors: CredentialErrors = {};

  if (fields.email !== undefined) {
    const emailError = validateEmail(fields.email);
    if (emailError !== null) {
      errors.email = emailError;
    }
  }

  if (fields.password !== undefined) {
    const passwordError = validatePassword(fields.password);
    if (passwordError !== null) {
      errors.password = passwordError;
    }
  }

  if (fields.confirmPassword !== undefined) {
    if (fields.confirmPassword !== fields.password) {
      errors.confirmPassword = 'Passwords do not match.';
    }
  }

  return errors;
}

/** True when a {@link CredentialErrors} map has no entries. */
export function isValid(errors: CredentialErrors): boolean {
  return Object.keys(errors).length === 0;
}
