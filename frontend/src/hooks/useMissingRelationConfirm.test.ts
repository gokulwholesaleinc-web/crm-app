import { describe, it, expect, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useMissingRelationConfirm } from './useMissingRelationConfirm';

interface TestPayload {
  id: number;
}

describe('useMissingRelationConfirm', () => {
  it('stages a payload via request and surfaces isOpen=true', () => {
    const submit = vi.fn();
    const { result } = renderHook(() => useMissingRelationConfirm<TestPayload>(submit));
    expect(result.current.isOpen).toBe(false);
    act(() => result.current.request({ id: 1 }));
    expect(result.current.isOpen).toBe(true);
    expect(submit).not.toHaveBeenCalled();
  });

  it('forwards staged payload to submit on confirm and closes', () => {
    const submit = vi.fn();
    const { result } = renderHook(() => useMissingRelationConfirm<TestPayload>(submit));
    act(() => result.current.request({ id: 1 }));
    act(() => result.current.onConfirm());
    expect(submit).toHaveBeenCalledWith({ id: 1 });
    expect(result.current.isOpen).toBe(false);
  });

  it('discards payload on cancel without invoking submit', () => {
    const submit = vi.fn();
    const { result } = renderHook(() => useMissingRelationConfirm<TestPayload>(submit));
    act(() => result.current.request({ id: 1 }));
    act(() => result.current.onCancel());
    expect(submit).not.toHaveBeenCalled();
    expect(result.current.isOpen).toBe(false);
  });

  it('is idempotent under rapid double-click on confirm', () => {
    const submit = vi.fn();
    const { result } = renderHook(() => useMissingRelationConfirm<TestPayload>(submit));
    act(() => result.current.request({ id: 1 }));
    act(() => {
      // Two synchronous calls before React flushes setPending(null)
      result.current.onConfirm();
      result.current.onConfirm();
    });
    expect(submit).toHaveBeenCalledTimes(1);
  });

  it('does not invoke submit when confirm fires with no staged payload', () => {
    const submit = vi.fn();
    const { result } = renderHook(() => useMissingRelationConfirm<TestPayload>(submit));
    act(() => result.current.onConfirm());
    expect(submit).not.toHaveBeenCalled();
  });

  it('re-stages cleanly after a prior confirm cycle', () => {
    const submit = vi.fn();
    const { result } = renderHook(() => useMissingRelationConfirm<TestPayload>(submit));
    act(() => result.current.request({ id: 1 }));
    act(() => result.current.onConfirm());
    act(() => result.current.request({ id: 2 }));
    act(() => result.current.onConfirm());
    expect(submit).toHaveBeenNthCalledWith(1, { id: 1 });
    expect(submit).toHaveBeenNthCalledWith(2, { id: 2 });
  });
});
