import "@testing-library/jest-dom/vitest";

// jsdom has no layout observer; actual panel sizing and dragging are covered in Edge.
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
