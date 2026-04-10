import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useUnsavedChangesWarning } from './useUnsavedChangesWarning';

describe('useUnsavedChangesWarning', () => {
  let addSpy: ReturnType<typeof vi.spyOn>;
  let removeSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    addSpy = vi.spyOn(window, 'addEventListener');
    removeSpy = vi.spyOn(window, 'removeEventListener');
  });

  afterEach(() => {
    addSpy.mockRestore();
    removeSpy.mockRestore();
  });

  it('does NOT attach the beforeunload handler when not dirty', () => {
    renderHook(() => useUnsavedChangesWarning(false));
    const calls = addSpy.mock.calls.filter((c) => c[0] === 'beforeunload');
    expect(calls).toHaveLength(0);
  });

  it('attaches the beforeunload handler when dirty', () => {
    renderHook(() => useUnsavedChangesWarning(true));
    const calls = addSpy.mock.calls.filter((c) => c[0] === 'beforeunload');
    expect(calls).toHaveLength(1);
  });

  it('removes the handler on unmount', () => {
    const { unmount } = renderHook(() => useUnsavedChangesWarning(true));
    unmount();
    const calls = removeSpy.mock.calls.filter((c) => c[0] === 'beforeunload');
    expect(calls).toHaveLength(1);
  });

  it('attaches and removes when isDirty transitions', () => {
    const { rerender, unmount } = renderHook(
      ({ dirty }: { dirty: boolean }) => useUnsavedChangesWarning(dirty),
      { initialProps: { dirty: false } }
    );

    expect(addSpy.mock.calls.filter((c) => c[0] === 'beforeunload')).toHaveLength(0);

    rerender({ dirty: true });
    expect(addSpy.mock.calls.filter((c) => c[0] === 'beforeunload')).toHaveLength(1);

    rerender({ dirty: false });
    expect(removeSpy.mock.calls.filter((c) => c[0] === 'beforeunload')).toHaveLength(1);

    unmount();
  });

  it('handler sets preventDefault and returnValue on the BeforeUnloadEvent', () => {
    renderHook(() => useUnsavedChangesWarning(true));
    const handler = addSpy.mock.calls.find((c) => c[0] === 'beforeunload')?.[1] as
      | ((e: BeforeUnloadEvent) => void)
      | undefined;
    expect(handler).toBeDefined();

    const fakeEvent = {
      preventDefault: vi.fn(),
      returnValue: undefined as string | undefined,
    } as unknown as BeforeUnloadEvent;

    handler?.(fakeEvent);

    expect(fakeEvent.preventDefault).toHaveBeenCalledTimes(1);
    expect(fakeEvent.returnValue).toBe('');
  });
});
