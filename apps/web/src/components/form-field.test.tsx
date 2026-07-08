import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { FormField } from '@/components/form-field';

describe('FormField', () => {
  it('renders a labeled input of the given type (email stays email)', () => {
    render(<FormField id="email" label="Email" type="email" />);
    const input = screen.getByLabelText('Email');
    expect(input).toHaveAttribute('type', 'email');
    // No error → no error wiring on the input.
    expect(input).not.toHaveAttribute('aria-invalid');
    expect(input).not.toHaveAttribute('aria-describedby');
  });

  it('wires an error to the input via aria-invalid + aria-describedby', () => {
    render(
      <FormField
        id="email"
        label="Email"
        type="email"
        error="Email is required"
      />,
    );
    const input = screen.getByLabelText('Email');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAccessibleDescription('Email is required');
    expect(screen.getByText('Email is required')).toBeInTheDocument();
  });

  it('renders the reveal toggle for password fields, keeping label + error wiring intact', () => {
    render(
      <FormField
        id="pw"
        label="Password"
        type="password"
        error="Too short"
        autoComplete="new-password"
      />,
    );
    // The label must resolve to the field itself (never the toggle button), with every shared
    // prop — including the screen-reader error association — forwarded through PasswordInput.
    const input = screen.getByLabelText('Password');
    expect(input).toHaveAttribute('type', 'password');
    expect(input).toHaveAttribute('autoComplete', 'new-password');
    expect(input).toHaveAttribute('aria-invalid', 'true');
    expect(input).toHaveAccessibleDescription('Too short');
    expect(
      screen.getByRole('button', { name: 'Show password' }),
    ).toHaveAttribute('type', 'button');
  });

  it('treats an empty error as no error', () => {
    render(<FormField id="pw" label="Password" type="password" error="" />);
    const input = screen.getByLabelText('Password');
    expect(input).not.toHaveAttribute('aria-invalid');
    expect(input).not.toHaveAttribute('aria-describedby');
  });
});
