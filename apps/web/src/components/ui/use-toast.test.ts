import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { reducer, toast, useToast } from '@/components/ui/use-toast';

// The toast shape isn't exported from use-toast.ts; extract it from the reducer signature so the
// test builds well-typed toasts without importing the internal ToasterToast type.
type ReducerState = Parameters<typeof reducer>[0];
type ReducerToast = ReducerState['toasts'][number];

// TOAST_LIMIT is module-local in use-toast.ts — mirror the value here.
const TOAST_LIMIT = 3;

function makeToast(id: string): ReducerToast {
  return { id, open: true, title: `toast-${id}` };
}

const empty: ReducerState = { toasts: [] };

describe('use-toast reducer', () => {
  // DISMISS_TOAST schedules a real setTimeout (addToRemoveQueue); fake timers keep the reducer test
  // from leaking timers or asynchronously mutating the module-global store.
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    // RUN (not just clear) the pending removal timers so addToRemoveQueue's module-global
    // toastTimeouts map is emptied — otherwise a stale entry dedup-blocks a later test that
    // reuses the same toast id.
    vi.runAllTimers();
    vi.useRealTimers();
  });

  it('ADD_TOAST prepends the newest toast', () => {
    const state = reducer(
      reducer(empty, { type: 'ADD_TOAST', toast: makeToast('1') }),
      { type: 'ADD_TOAST', toast: makeToast('2') },
    );
    expect(state.toasts.map((t) => t.id)).toEqual(['2', '1']);
  });

  it('ADD_TOAST caps the queue at TOAST_LIMIT, keeping the newest', () => {
    let state: ReducerState = empty;
    for (const id of ['1', '2', '3', '4', '5']) {
      state = reducer(state, { type: 'ADD_TOAST', toast: makeToast(id) });
    }
    expect(state.toasts).toHaveLength(TOAST_LIMIT);
    expect(state.toasts.map((t) => t.id)).toEqual(['5', '4', '3']);
  });

  it('UPDATE_TOAST merges fields into the matching id only', () => {
    const start: ReducerState = { toasts: [makeToast('1'), makeToast('2')] };
    const state = reducer(start, {
      type: 'UPDATE_TOAST',
      toast: { id: '1', title: 'updated' },
    });
    expect(state.toasts.find((t) => t.id === '1')?.title).toBe('updated');
    expect(state.toasts.find((t) => t.id === '2')?.title).toBe('toast-2');
  });

  it('DISMISS_TOAST with an id closes only that toast (open=false)', () => {
    const start: ReducerState = { toasts: [makeToast('1'), makeToast('2')] };
    const state = reducer(start, { type: 'DISMISS_TOAST', toastId: '1' });
    expect(state.toasts.find((t) => t.id === '1')?.open).toBe(false);
    expect(state.toasts.find((t) => t.id === '2')?.open).toBe(true);
  });

  it('DISMISS_TOAST without an id closes every toast', () => {
    const start: ReducerState = { toasts: [makeToast('1'), makeToast('2')] };
    const state = reducer(start, { type: 'DISMISS_TOAST' });
    expect(state.toasts.every((t) => t.open === false)).toBe(true);
  });

  it('REMOVE_TOAST with an id drops only that toast', () => {
    const start: ReducerState = { toasts: [makeToast('1'), makeToast('2')] };
    const state = reducer(start, { type: 'REMOVE_TOAST', toastId: '1' });
    expect(state.toasts.map((t) => t.id)).toEqual(['2']);
  });

  it('REMOVE_TOAST without an id clears the whole queue', () => {
    const start: ReducerState = { toasts: [makeToast('1'), makeToast('2')] };
    expect(reducer(start, { type: 'REMOVE_TOAST' }).toasts).toEqual([]);
  });
});

describe('useToast store', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => {
    // Drain the removal queue so the module-global store doesn't leak toasts between tests.
    act(() => {
      vi.runAllTimers();
    });
    vi.useRealTimers();
  });

  it('toast() enqueues a toast the hook exposes; dismiss + timer removes it', () => {
    const { result } = renderHook(() => useToast());

    let handle!: ReturnType<typeof toast>;
    act(() => {
      handle = toast({ title: 'Saved' });
    });
    expect(result.current.toasts.some((t) => t.id === handle.id)).toBe(true);
    expect(result.current.toasts.find((t) => t.id === handle.id)?.title).toBe(
      'Saved',
    );

    act(() => {
      result.current.dismiss(handle.id);
    });
    expect(result.current.toasts.find((t) => t.id === handle.id)?.open).toBe(
      false,
    );

    // addToRemoveQueue's setTimeout fires → REMOVE_TOAST drops it from the store.
    act(() => {
      vi.runAllTimers();
    });
    expect(result.current.toasts.some((t) => t.id === handle.id)).toBe(false);
  });

  it('the toast handle update() changes its fields in the store', () => {
    const { result } = renderHook(() => useToast());

    let handle!: ReturnType<typeof toast>;
    act(() => {
      handle = toast({ title: 'Loading' });
    });
    act(() => {
      handle.update({ id: handle.id, title: 'Done', open: true });
    });
    expect(result.current.toasts.find((t) => t.id === handle.id)?.title).toBe(
      'Done',
    );
  });
});
