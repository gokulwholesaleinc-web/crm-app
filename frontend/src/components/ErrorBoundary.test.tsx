import { describe, expect, it } from 'vitest';

import { isStaleChunkLoadError } from './ErrorBoundary';

describe('isStaleChunkLoadError', () => {
  it('detects Vite dynamic import failures from stale deploy chunks', () => {
    expect(
      isStaleChunkLoadError(
        new TypeError(
          'Failed to fetch dynamically imported module: https://example.com/assets/ProposalsPage-old.js',
        ),
      ),
    ).toBe(true);
  });

  it('leaves normal runtime errors alone', () => {
    expect(isStaleChunkLoadError(new Error('Cannot read properties of undefined'))).toBe(false);
  });
});
