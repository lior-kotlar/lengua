import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { HelpTip } from '@/components/help-tip';

describe('HelpTip', () => {
  it('exposes the label as the trigger name and the text as its hover title', () => {
    render(<HelpTip text="Explains the thing." label="About the thing" />);

    const trigger = screen.getByRole('button', { name: 'About the thing' });
    expect(trigger).toHaveAttribute('title', 'Explains the thing.');
  });

  it('falls back to a generic accessible name', () => {
    render(<HelpTip text="Explains the thing." />);
    expect(
      screen.getByRole('button', { name: 'More information' }),
    ).toBeInTheDocument();
  });

  it('reveals the explanation when the trigger is clicked or tapped', async () => {
    const user = userEvent.setup();
    render(<HelpTip text="Explains the thing." label="About the thing" />);

    // Closed by default — no popover content in the DOM.
    expect(screen.queryByText('Explains the thing.')).not.toBeInTheDocument();

    await user.click(screen.getByRole('button', { name: 'About the thing' }));
    expect(screen.getByText('Explains the thing.')).toBeInTheDocument();
  });

  it('is a plain button that never submits a surrounding form', async () => {
    const onSubmit = vi.fn((event: React.FormEvent) => event.preventDefault());
    const user = userEvent.setup();
    render(
      <form onSubmit={onSubmit}>
        <HelpTip text="Explains the thing." label="About the thing" />
      </form>,
    );

    await user.click(screen.getByRole('button', { name: 'About the thing' }));
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
