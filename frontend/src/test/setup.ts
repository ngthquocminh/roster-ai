import "@testing-library/jest-dom";
import { toHaveNoViolations } from "jest-axe";
import { expect, vi } from "vitest";

expect.extend(toHaveNoViolations);

// jsdom implements neither of these DOM APIs, and Radix `Select` (plan 01-07,
// the fixture picker) calls both internally when its trigger opens/closes.
// Without these no-op polyfills, every test that opens the Select throws a
// "not implemented" jsdom error unrelated to the behavior under test.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = () => {};
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

// jsdom has no viewport media-query implementation. Components use this one
// browser API to choose the phone viewing default; tests override `matches`
// when exercising the phone branch and otherwise get a desktop-sized default.
if (!window.matchMedia) {
  window.matchMedia = vi.fn((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }));
}
