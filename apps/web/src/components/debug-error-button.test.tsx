import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { DebugErrorButton } from '@/components/debug-error-button';

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('DebugErrorButton', () => {
  it('renders nothing when debug tools are disabled (the default/prod path)', () => {
    const { container } = render(<DebugErrorButton />);
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByTestId('debug-throw-error')).toBeNull();
  });

  it('renders a hidden button when debug tools are enabled', () => {
    vi.stubEnv('VITE_ENABLE_DEBUG_TOOLS', '1');
    // No onTrigger → exercises the default triggerDebugError binding (not clicked here).
    render(<DebugErrorButton />);
    const button = screen.getByTestId('debug-throw-error');
    expect(button).toHaveAccessibleName('Trigger a debug error');
    expect(button).toHaveClass('sr-only');
  });

  it('invokes the trigger exactly once on click', async () => {
    vi.stubEnv('VITE_ENABLE_DEBUG_TOOLS', '1');
    const onTrigger = vi.fn();
    render(<DebugErrorButton onTrigger={onTrigger} />);
    await userEvent.click(screen.getByTestId('debug-throw-error'));
    expect(onTrigger).toHaveBeenCalledTimes(1);
  });
});
