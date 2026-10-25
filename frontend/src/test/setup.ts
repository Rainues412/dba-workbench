import "@testing-library/jest-dom/vitest";

// Native scrolling is asserted here by calls and by viewport geometry in Edge.
if (!Element.prototype.scrollIntoView) Element.prototype.scrollIntoView = () => undefined;

// jsdom has no layout observer; actual panel sizing and dragging are covered in Edge.
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}
