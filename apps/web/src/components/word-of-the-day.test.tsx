import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { useFeatureFlag } = vi.hoisted(() => ({ useFeatureFlag: vi.fn() }));
vi.mock('@/lib/feature-flags', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/feature-flags')>();
  return { ...actual, useFeatureFlag };
});

import { WordOfTheDay } from '@/components/word-of-the-day';
import { WORD_OF_THE_DAY_FLAG } from '@/lib/feature-flags';

beforeEach(() => {
  vi.clearAllMocks();
});

describe('WordOfTheDay', () => {
  it('renders nothing when the flag is off (ships dark)', () => {
    useFeatureFlag.mockReturnValue(false);

    const { container } = render(<WordOfTheDay />);

    expect(container).toBeEmptyDOMElement();
    expect(useFeatureFlag).toHaveBeenCalledWith(WORD_OF_THE_DAY_FLAG);
  });

  it('renders the experimental card when the flag is on', () => {
    useFeatureFlag.mockReturnValue(true);

    render(<WordOfTheDay />);

    expect(
      screen.getByRole('heading', { name: 'Word of the day' }),
    ).toBeInTheDocument();
  });
});
