// jest-dom adds custom jest matchers for asserting on DOM nodes.
// allows you to do things like:
// expect(element).toHaveTextContent(/react/i)
// learn more: https://github.com/testing-library/jest-dom
import '@testing-library/jest-dom';

// React 19 requires this flag to recognize the test environment as act()-compatible;
// without it, async state updates outside a directly-awaited act() callback log a
// spurious "environment not configured to support act()" warning even though the
// update is still applied correctly.
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
