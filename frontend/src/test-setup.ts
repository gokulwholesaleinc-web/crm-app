import '@testing-library/jest-dom';

// Headless UI's Dialog uses ResizeObserver, which jsdom doesn't provide.
if (typeof globalThis.ResizeObserver === 'undefined') {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}
