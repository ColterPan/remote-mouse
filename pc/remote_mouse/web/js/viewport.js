/**
 * viewport.js — Keeps the remote laid out correctly while the phone keyboard
 * opens and closes.
 *
 * The problem: when the keyboard appears, the visible area shrinks. Depending
 * on the browser/Android version the page is either resized, overlaid, or
 * panned (scrolled) to reveal the focused text field. That made the touchpad
 * jump, overflow, or end up half-hidden behind the keyboard.
 *
 * The fix, in four parts:
 *  1. We always size the app to the *visible* area (`visualViewport`), via the
 *     CSS variables --app-h / --app-top, and keep the page from scrolling.
 *  2. We detect "the keyboard is open" by comparing the visible height with
 *     the tallest height seen at the current width (the phone's full screen).
 *  3. While the keyboard is open the layout switches to a compact mode
 *     (`.kb-open`), so the touchpad keeps a usable size above the keyboard.
 *  4. Landscape (`.landscape`) is decided from the full screen size. A CSS
 *     orientation query flipped the layout to landscape when the keyboard
 *     made the visible area wider than tall — squashing the touchpad.
 *
 * `nextViewport` is a pure function so it can be unit-tested in Node.
 */

/** A height loss bigger than this means a keyboard, not a browser toolbar. */
export const KEYBOARD_MIN_PX = 150;
/** Phones in landscape are at most this tall; tablets keep the portrait layout. */
export const LANDSCAPE_MAX_HEIGHT = 600;

/**
 * @param {{width:number, baseline:number}|null} prev  the previous state
 * @param {{width:number, height:number}} size          the current visible size
 * @returns {{width:number, height:number, baseline:number, keyboardOpen:boolean, landscape:boolean}}
 */
export function nextViewport(prev, { width, height }) {
  // Rotating the phone changes the width; start measuring afresh.
  const sameWidth = prev !== null && Math.abs(prev.width - width) < 2;
  const baseline = sameWidth ? Math.max(prev.baseline, height) : height;
  return {
    width,
    height,
    baseline,
    keyboardOpen: baseline - height > KEYBOARD_MIN_PX,
    // Judged on the full screen height, NOT the keyboard-shrunk one: a phone
    // held upright with the keyboard open is still in portrait.
    landscape: width > baseline && baseline <= LANDSCAPE_MAX_HEIGHT,
  };
}

/**
 * Start tracking. Calls `onKeyboard(open)` whenever the keyboard opens/closes.
 * @param {HTMLElement} root  the element that gets --app-h and .kb-open
 * @param {(open: boolean) => void} onKeyboard
 */
export function trackViewport(root, onKeyboard) {
  const vv = window.visualViewport;
  let state = null;

  function update() {
    const height = vv ? vv.height : window.innerHeight;
    const width = vv ? vv.width : window.innerWidth;
    const next = nextViewport(state, { width, height });
    root.style.setProperty('--app-h', `${Math.round(height)}px`);
    root.style.setProperty('--app-top', `${Math.round(vv ? vv.offsetTop : 0)}px`);
    root.classList.toggle('landscape', next.landscape);
    // Undo any scrolling the browser did to reveal the hidden text field.
    if (window.scrollX || window.scrollY) window.scrollTo(0, 0);
    const changed = state === null || state.keyboardOpen !== next.keyboardOpen;
    state = next;
    if (changed) onKeyboard(next.keyboardOpen);
  }

  if (vv) {
    vv.addEventListener('resize', update);
    vv.addEventListener('scroll', update);
  }
  window.addEventListener('resize', update);
  update();
  return { update, isKeyboardOpen: () => Boolean(state && state.keyboardOpen) };
}
