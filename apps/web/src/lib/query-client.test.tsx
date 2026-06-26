import { QueryClientProvider, useQuery } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { createQueryClient } from '@/lib/query-client';

describe('createQueryClient', () => {
  it('configures sane query + mutation defaults', () => {
    const qc = createQueryClient();
    const defaults = qc.getDefaultOptions();

    expect(defaults.queries?.staleTime).toBe(30_000);
    expect(defaults.queries?.retry).toBe(1);
    expect(defaults.queries?.refetchOnWindowFocus).toBe(false);
    expect(defaults.mutations?.retry).toBe(0);
  });
});

function Greeting() {
  const { data, isLoading } = useQuery({
    queryKey: ['greeting'],
    queryFn: () => Promise.resolve('hola'),
  });

  if (isLoading) return <p>loading…</p>;
  return <p>{data}</p>;
}

describe('useQuery against the configured client', () => {
  it('transitions loading → success with the fetched data', async () => {
    const fetchSpy = vi.fn(() => Promise.resolve('hola'));
    function Spied() {
      const { data, isLoading } = useQuery({
        queryKey: ['spied'],
        queryFn: fetchSpy,
      });
      return <p>{isLoading ? 'loading…' : data}</p>;
    }

    render(
      <QueryClientProvider client={createQueryClient()}>
        <Spied />
      </QueryClientProvider>,
    );

    // First paint is the loading state.
    expect(screen.getByText('loading…')).toBeInTheDocument();

    // Then it resolves to success.
    expect(await screen.findByText('hola')).toBeInTheDocument();
    expect(fetchSpy).toHaveBeenCalledTimes(1);
  });

  it('renders the success data for a simple query', async () => {
    render(
      <QueryClientProvider client={createQueryClient()}>
        <Greeting />
      </QueryClientProvider>,
    );

    expect(await screen.findByText('hola')).toBeInTheDocument();
  });
});
