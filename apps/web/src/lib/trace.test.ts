import { describe, expect, it, vi } from 'vitest';

import {
  generateTraceparent,
  TRACEPARENT_FLAGS_SAMPLED,
  TRACEPARENT_REGEX,
  TRACEPARENT_VERSION,
} from '@/lib/trace';

describe('generateTraceparent', () => {
  it('produces a well-formed W3C version-00 sampled traceparent', () => {
    const tp = generateTraceparent();

    expect(tp).toMatch(TRACEPARENT_REGEX);
    const [version, traceId, parentId, flags] = tp.split('-');
    expect(version).toBe(TRACEPARENT_VERSION); // 00
    expect(traceId).toHaveLength(32); // 16 bytes
    expect(parentId).toHaveLength(16); // 8 bytes
    expect(flags).toBe(TRACEPARENT_FLAGS_SAMPLED); // 01 — sampled
  });

  it('mints a fresh, random trace-id + span-id on each call', () => {
    const first = generateTraceparent();
    const second = generateTraceparent();

    expect(first).not.toBe(second);
    // Not just the flags differ — both the trace-id and the span-id segments are freshly random.
    const [, traceA, spanA] = first.split('-');
    const [, traceB, spanB] = second.split('-');
    expect(traceA).not.toBe(traceB);
    expect(spanA).not.toBe(spanB);
  });

  it('hex-encodes the injected random bytes in order (16-byte trace-id then 8-byte span-id)', () => {
    const draws = [
      Uint8Array.from({ length: 16 }, (_, i) => i + 1), // 0102…10
      Uint8Array.from({ length: 8 }, (_, i) => 0xa0 + i), // a0a1…a7
    ];
    let call = 0;
    const randomBytes = vi.fn(() => draws[call++]);

    const tp = generateTraceparent(randomBytes);

    expect(tp).toBe('00-0102030405060708090a0b0c0d0e0f10-a0a1a2a3a4a5a6a7-01');
    expect(randomBytes).toHaveBeenNthCalledWith(1, 16);
    expect(randomBytes).toHaveBeenNthCalledWith(2, 8);
  });

  it('never emits an all-zero id: regenerates on a zero draw', () => {
    // First trace-id draw is all-zero (invalid per W3C) → rejected and redrawn; then valid ids.
    const draws = [
      new Uint8Array(16), // all zero → rejected
      Uint8Array.from({ length: 16 }, () => 0x11), // valid trace-id
      Uint8Array.from({ length: 8 }, () => 0x22), // valid span-id
    ];
    let call = 0;
    const randomBytes = vi.fn(() => draws[call++]);

    const tp = generateTraceparent(randomBytes);

    expect(tp).toBe(`00-${'11'.repeat(16)}-${'22'.repeat(8)}-01`);
    expect(tp).toMatch(TRACEPARENT_REGEX);
    expect(randomBytes).toHaveBeenCalledTimes(3); // one extra draw for the rejected all-zero id
  });
});
