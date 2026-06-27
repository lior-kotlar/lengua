import { describe, expect, it } from 'vitest';

import {
  isValid,
  MIN_PASSWORD_LENGTH,
  validateCredentials,
  validateEmail,
  validatePassword,
} from '@/lib/auth-validation';

describe('validateEmail', () => {
  it('accepts a well-formed address', () => {
    expect(validateEmail('user@example.com')).toBeNull();
    expect(validateEmail('  user@example.com  ')).toBeNull();
  });

  it('rejects blank and malformed addresses', () => {
    expect(validateEmail('')).toMatch(/enter your email/i);
    expect(validateEmail('   ')).toMatch(/enter your email/i);
    expect(validateEmail('not-an-email')).toMatch(/valid email/i);
    expect(validateEmail('a@b')).toMatch(/valid email/i);
    expect(validateEmail('a b@c.com')).toMatch(/valid email/i);
  });
});

describe('validatePassword', () => {
  it('accepts a password meeting the policy', () => {
    expect(validatePassword('Abcdef12')).toBeNull();
  });

  it('enforces length, lowercase, uppercase and a digit', () => {
    expect(validatePassword('Ab1')).toMatch(
      new RegExp(`${MIN_PASSWORD_LENGTH} characters`),
    );
    expect(validatePassword('ABCDEF12')).toMatch(/lowercase/i);
    expect(validatePassword('abcdef12')).toMatch(/uppercase/i);
    expect(validatePassword('Abcdefgh')).toMatch(/number/i);
  });
});

describe('validateCredentials', () => {
  it('only checks the fields that are present', () => {
    expect(validateCredentials({})).toEqual({});
    expect(validateCredentials({ email: 'user@example.com' })).toEqual({});
    expect(isValid(validateCredentials({ password: 'Abcdef12' }))).toBe(true);
  });

  it('collects per-field errors', () => {
    const errors = validateCredentials({
      email: 'bad',
      password: 'short',
      confirmPassword: 'different',
    });
    expect(errors.email).toBeDefined();
    expect(errors.password).toBeDefined();
    expect(errors.confirmPassword).toMatch(/do not match/i);
    expect(isValid(errors)).toBe(false);
  });

  it('passes when confirmPassword matches password', () => {
    const errors = validateCredentials({
      email: 'user@example.com',
      password: 'Abcdef12',
      confirmPassword: 'Abcdef12',
    });
    expect(errors).toEqual({});
    expect(isValid(errors)).toBe(true);
  });
});
