import { describe, expect, it } from 'vitest';

import { ApiError } from '@/lib/api-client';
import {
  classifyLlmError,
  describeLlmError,
  isDailyLimitError,
} from '@/lib/llm-error';

function apiError(init: {
  status: number;
  code?: string;
  message?: string;
  retryAfter?: number;
}): ApiError {
  return new ApiError({ message: 'boom', ...init });
}

describe('isDailyLimitError', () => {
  it('is true for the per-user daily cap (daily_cap_reached, 429)', () => {
    expect(
      isDailyLimitError(apiError({ status: 429, code: 'daily_cap_reached' })),
    ).toBe(true);
  });

  it('is true for the global kill-switch (daily_limit_reached, 429)', () => {
    expect(
      isDailyLimitError(apiError({ status: 429, code: 'daily_limit_reached' })),
    ).toBe(true);
  });

  it('is false for a non-daily 429 (rate_limited)', () => {
    expect(
      isDailyLimitError(apiError({ status: 429, code: 'rate_limited' })),
    ).toBe(false);
  });

  it('is false for the right code with the wrong status', () => {
    expect(
      isDailyLimitError(apiError({ status: 403, code: 'daily_cap_reached' })),
    ).toBe(false);
  });

  it('is false for a non-ApiError value', () => {
    expect(isDailyLimitError(new Error('nope'))).toBe(false);
    expect(isDailyLimitError(null)).toBe(false);
  });
});

describe('classifyLlmError', () => {
  it('classifies the daily-limit shapes', () => {
    expect(
      classifyLlmError(apiError({ status: 429, code: 'daily_cap_reached' })),
    ).toBe('daily_limit');
    expect(
      classifyLlmError(apiError({ status: 429, code: 'daily_limit_reached' })),
    ).toBe('daily_limit');
  });

  it('classifies rate_limited / server_busy / email_unverified', () => {
    expect(
      classifyLlmError(apiError({ status: 429, code: 'rate_limited' })),
    ).toBe('rate_limited');
    expect(
      classifyLlmError(apiError({ status: 503, code: 'server_busy' })),
    ).toBe('server_busy');
    expect(
      classifyLlmError(apiError({ status: 403, code: 'email_unverified' })),
    ).toBe('email_unverified');
  });

  it('falls back to generic for an unknown ApiError code and for non-ApiErrors', () => {
    expect(classifyLlmError(apiError({ status: 500 }))).toBe('generic');
    expect(classifyLlmError(new Error('weird'))).toBe('generic');
  });
});

describe('describeLlmError', () => {
  it('describes the daily-limit state', () => {
    const { title, description } = describeLlmError(
      apiError({ status: 429, code: 'daily_cap_reached' }),
    );
    expect(title).toBe('Daily limit reached');
    expect(description).toMatch(/try again tomorrow/i);
  });

  it('includes the Retry-After delay for rate_limited (pluralized)', () => {
    expect(
      describeLlmError(
        apiError({ status: 429, code: 'rate_limited', retryAfter: 5 }),
      ).description,
    ).toContain('5 seconds');
  });

  it('uses the singular for a 1-second Retry-After', () => {
    expect(
      describeLlmError(
        apiError({ status: 503, code: 'server_busy', retryAfter: 1 }),
      ).description,
    ).toContain('1 second.');
  });

  it('falls back to "in a moment" when there is no Retry-After', () => {
    expect(
      describeLlmError(apiError({ status: 429, code: 'rate_limited' }))
        .description,
    ).toMatch(/in a moment/i);
  });

  it('falls back to "in a moment" for a zero-second Retry-After', () => {
    expect(
      describeLlmError(
        apiError({ status: 503, code: 'server_busy', retryAfter: 0 }),
      ).description,
    ).toMatch(/in a moment/i);
  });

  it('describes the email-unverified state', () => {
    expect(
      describeLlmError(apiError({ status: 403, code: 'email_unverified' }))
        .title,
    ).toBe('Verify your email');
  });

  it('uses the ApiError message for a generic API error', () => {
    expect(
      describeLlmError(apiError({ status: 500, message: 'Boom happened' }))
        .description,
    ).toBe('Boom happened');
  });

  it('uses a friendly default for a non-ApiError value', () => {
    const { title, description } = describeLlmError('totally not an error');
    expect(title).toBe('Something went wrong');
    expect(description).toBe('Please try again.');
  });
});
