import "@testing-library/jest-dom";

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
