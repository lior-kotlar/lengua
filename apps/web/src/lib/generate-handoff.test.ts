import { afterEach, describe, expect, it } from 'vitest';

import { handOffWords, takeHandedOffWords } from '@/lib/generate-handoff';

// Module-level store: drain it after each test so state never leaks between cases.
afterEach(() => {
  takeHandedOffWords();
});

describe('generate-handoff', () => {
  it('returns null when nothing has been handed off', () => {
    expect(takeHandedOffWords()).toBeNull();
  });

  it('hands off words and consumes them exactly once', () => {
    handOffWords(['casa', 'perro']);
    expect(takeHandedOffWords()).toEqual(['casa', 'perro']);
    // One-shot: a second take returns null.
    expect(takeHandedOffWords()).toBeNull();
  });

  it('treats an empty list as nothing to hand off', () => {
    handOffWords([]);
    expect(takeHandedOffWords()).toBeNull();
  });

  it('copies the words so later mutation of the source array does not leak in', () => {
    const words = ['uno', 'dos'];
    handOffWords(words);
    words.push('tres');
    expect(takeHandedOffWords()).toEqual(['uno', 'dos']);
  });

  it('overwrites a pending handoff with the latest words', () => {
    handOffWords(['old']);
    handOffWords(['new']);
    expect(takeHandedOffWords()).toEqual(['new']);
  });
});
