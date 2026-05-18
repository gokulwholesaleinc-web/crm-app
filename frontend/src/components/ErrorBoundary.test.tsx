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

  it('does not misclassify API 404s on paths containing "/assets/"', () => {
    // Regression: an earlier heuristic matched any error whose message
    // contained both "/assets/" and "404", which silently reloaded the
    // page when an API 404 happened to mention an /assets/ URL.
    expect(
      isStaleChunkLoadError(
        new Error('Request failed with status code 404: GET https://api.example.com/v1/assets/123'),
      ),
    ).toBe(false);
  });
});
