import { act, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Toaster } from '@/components/ui/toaster';
import { toast } from '@/components/ui/use-toast';

describe('shadcn/ui primitives', () => {
  it('renders a Button as a real <button> with its variant classes', () => {
    render(<Button>Click me</Button>);
    const button = screen.getByRole('button', { name: 'Click me' });
    expect(button.tagName).toBe('BUTTON');
    expect(button).toHaveClass('inline-flex');
    expect(button).toHaveClass('bg-primary');
  });

  it('renders a Card with header + content', () => {
    render(
      <Card>
        <CardHeader>
          <CardTitle>Title</CardTitle>
        </CardHeader>
        <CardContent>Card body</CardContent>
      </Card>,
    );
    expect(screen.getByText('Title')).toBeInTheDocument();
    expect(screen.getByText('Card body')).toBeInTheDocument();
  });

  it('renders an Input', () => {
    render(<Input placeholder="Email" />);
    expect(screen.getByPlaceholderText('Email')).toBeInTheDocument();
  });

  it('renders Dialog content when open', () => {
    render(
      <Dialog open>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Confirm</DialogTitle>
            <DialogDescription>Are you sure?</DialogDescription>
          </DialogHeader>
        </DialogContent>
      </Dialog>,
    );
    expect(screen.getByText('Confirm')).toBeInTheDocument();
    expect(screen.getByText('Are you sure?')).toBeInTheDocument();
  });

  it('renders a queued Toast through the Toaster', async () => {
    render(<Toaster />);
    act(() => {
      toast({ title: 'Saved', description: 'Your changes were saved.' });
    });
    expect(await screen.findByText('Saved')).toBeInTheDocument();
  });
});
