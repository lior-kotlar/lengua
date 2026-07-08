import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { PasswordInput } from '@/components/ui/password-input';

/**
 * Renders the reveal control the way the auth forms use it: a `<label htmlFor>` associated with the
 * input so `getByLabelText('Password')` keeps resolving to the field (never the toggle button).
 */
function renderField(extra?: React.ComponentProps<typeof PasswordInput>) {
  render(
    <>
      <label htmlFor="pw">Password</label>
      <PasswordInput id="pw" autoComplete="current-password" {...extra} />
    </>,
  );
  return {
    input: screen.getByLabelText('Password') as HTMLInputElement,
    toggle: () => screen.getByRole('button'),
  };
}

describe('PasswordInput', () => {
  it('starts masked and preserves the label association + autoComplete', () => {
    const { input, toggle } = renderField();
    expect(input).toHaveAttribute('type', 'password');
    expect(input).toHaveAttribute('autoComplete', 'current-password');
    // The toggle is a real button that must never submit a form, with an action-describing label.
    expect(toggle()).toHaveAttribute('type', 'button');
    expect(toggle()).toHaveAccessibleName('Show password');
  });

  it('reveals while the pointer is held and re-masks on release', () => {
    const { input, toggle } = renderField();

    fireEvent.pointerDown(toggle());
    expect(input).toHaveAttribute('type', 'text');
    expect(toggle()).toHaveAccessibleName('Hide password');

    fireEvent.pointerUp(toggle());
    expect(input).toHaveAttribute('type', 'password');
    expect(toggle()).toHaveAccessibleName('Show password');
  });

  it('re-masks when the pointer leaves or the gesture is cancelled mid-hold', () => {
    const { input, toggle } = renderField();

    fireEvent.pointerDown(toggle());
    expect(input).toHaveAttribute('type', 'text');
    fireEvent.pointerLeave(toggle());
    expect(input).toHaveAttribute('type', 'password');

    fireEvent.pointerDown(toggle());
    expect(input).toHaveAttribute('type', 'text');
    fireEvent.pointerCancel(toggle());
    expect(input).toHaveAttribute('type', 'password');
  });

  it('prevents the default pointer-down action so focus is not stolen from the field', () => {
    const { toggle } = renderField();
    const event = new Event('pointerdown', { bubbles: true, cancelable: true });
    fireEvent(toggle(), event);
    expect(event.defaultPrevented).toBe(true);
  });

  it('toggles (sticky) via Enter and Space for keyboard users', () => {
    const { input, toggle } = renderField();

    fireEvent.keyDown(toggle(), { key: 'Enter' });
    expect(input).toHaveAttribute('type', 'text');
    // Sticky: a second Enter hides again (unlike the momentary pointer hold).
    fireEvent.keyDown(toggle(), { key: 'Enter' });
    expect(input).toHaveAttribute('type', 'password');

    fireEvent.keyDown(toggle(), { key: ' ' });
    expect(input).toHaveAttribute('type', 'text');
  });

  it('flips once per physical press — key auto-repeat is ignored', () => {
    const { input, toggle } = renderField();
    fireEvent.keyDown(toggle(), { key: 'Enter' });
    expect(input).toHaveAttribute('type', 'text');
    // A held key fires a stream of keydown events with repeat: true — they must not re-flip, or
    // the reveal strobes and lands on a parity-dependent state.
    fireEvent.keyDown(toggle(), { key: 'Enter', repeat: true });
    expect(input).toHaveAttribute('type', 'text');
    fireEvent.keyDown(toggle(), { key: ' ', repeat: true });
    expect(input).toHaveAttribute('type', 'text');
  });

  it('prevents default on Space so the page does not scroll', () => {
    const { toggle } = renderField();
    const event = new KeyboardEvent('keydown', {
      key: ' ',
      bubbles: true,
      cancelable: true,
    });
    fireEvent(toggle(), event);
    expect(event.defaultPrevented).toBe(true);
  });

  it('prevents default on auto-repeated Space too (no page scroll mid-hold)', () => {
    const { toggle } = renderField();
    const event = new KeyboardEvent('keydown', {
      key: ' ',
      repeat: true,
      bubbles: true,
      cancelable: true,
    });
    fireEvent(toggle(), event);
    expect(event.defaultPrevented).toBe(true);
  });

  it('ignores unrelated keys', () => {
    const { input, toggle } = renderField();
    fireEvent.keyDown(toggle(), { key: 'a' });
    expect(input).toHaveAttribute('type', 'password');
  });

  it('re-masks on blur so a revealed password is not left exposed', () => {
    const { input, toggle } = renderField();
    fireEvent.keyDown(toggle(), { key: 'Enter' });
    expect(input).toHaveAttribute('type', 'text');
    fireEvent.blur(toggle());
    expect(input).toHaveAttribute('type', 'password');
  });

  it('keeps a keyboard-toggled reveal through a plain hover-out (no hold in progress)', () => {
    const { input, toggle } = renderField();
    fireEvent.keyDown(toggle(), { key: 'Enter' });
    expect(input).toHaveAttribute('type', 'text');
    // pointerleave fires on a plain mouse sweep across the button with nothing pressed, and a
    // stray pointerup behaves the same — neither is a deliberate action, so the sticky keyboard
    // reveal must survive both. Only toggle/hold-release/blur re-mask.
    fireEvent.pointerLeave(toggle());
    fireEvent.pointerUp(toggle());
    expect(input).toHaveAttribute('type', 'text');
    fireEvent.blur(toggle());
    expect(input).toHaveAttribute('type', 'password');
  });

  it('does not submit the surrounding form when clicked or toggled', async () => {
    const onSubmit = vi.fn((event: React.FormEvent) => event.preventDefault());
    render(
      <form onSubmit={onSubmit}>
        <label htmlFor="pw">Password</label>
        <PasswordInput id="pw" />
      </form>,
    );
    const user = userEvent.setup();
    await user.click(screen.getByRole('button'));
    fireEvent.keyDown(screen.getByRole('button'), { key: 'Enter' });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it('still accepts typed input while masked', async () => {
    const { input } = renderField();
    const user = userEvent.setup();
    await user.type(input, 'hunter2');
    expect(input).toHaveValue('hunter2');
  });
});
