/**
 * touchpad.js — Connects the on-screen touchpad and scroll strip to the PC.
 *
 * Flow:  finger events (Pointer Events API)
 *          → GestureTracker (gestures.js) decides what they mean
 *          → movement/scroll is BATCHED: summed up and sent at most once per
 *            screen frame (~60×/s) instead of for every tiny event, which
 *            keeps Wi-Fi traffic low and motion smooth
 *          → clicks and button presses are sent immediately (after flushing
 *            any pending movement, so order is preserved)
 */

import { DOUBLE_TAP_MS, GestureTracker, panToScroll } from './gestures.js';

const round = (value) => Math.round(value * 100) / 100;

/**
 * @param {object} opts
 * @param {HTMLElement} opts.element      the touchpad
 * @param {HTMLElement} opts.strip        the one-finger scroll strip
 * @param {HTMLElement} opts.hint         helper text, hidden after first use
 * @param {(msg: object) => void} opts.send
 * @param {() => object} opts.getOptions  current sensitivity/scroll settings
 * @param {() => void} opts.onClick       e.g. vibrate
 */
export function createTouchpad({ element, strip, hint, send, getOptions, onClick }) {
  const tracker = new GestureTracker(getOptions());
  let pending = { mx: 0, my: 0, sx: 0, sy: 0 };
  let frame = 0;

  function flush() {
    if (frame) cancelAnimationFrame(frame);
    frame = 0;
    const { mx, my, sx, sy } = pending;
    pending = { mx: 0, my: 0, sx: 0, sy: 0 };
    if (mx || my) send({ t: 'move', dx: round(mx), dy: round(my) });
    if (sx || sy) send({ t: 'scroll', dx: round(sx), dy: round(sy) });
  }

  function queue(kind, dx, dy) {
    pending =
      kind === 'move'
        ? { ...pending, mx: pending.mx + dx, my: pending.my + dy }
        : { ...pending, sx: pending.sx + dx, sy: pending.sy + dy };
    if (!frame) frame = requestAnimationFrame(flush);
  }

  function perform(actions) {
    for (const action of actions) {
      if (action.type === 'move' || action.type === 'scroll') {
        queue(action.type, action.dx, action.dy);
        continue;
      }
      flush();
      if (action.type === 'click') {
        send({ t: 'click', b: action.button, n: 1 });
        onClick();
      } else {
        send({ t: action.type, b: action.button }); // 'down' | 'up'
        if (action.type === 'down') onClick();
      }
    }
    element.classList.toggle('dragging', tracker.isDragging);
  }

  // --- Touchpad ------------------------------------------------------------
  element.addEventListener('pointerdown', (e) => {
    e.preventDefault(); // keep the phone keyboard open and stop text selection
    element.setPointerCapture(e.pointerId);
    tracker.setOptions(getOptions());
    element.classList.add('active');
    hint.classList.add('hidden');
    perform(tracker.down(e.pointerId, e.clientX, e.clientY, e.timeStamp));
  });

  element.addEventListener('pointermove', (e) => {
    perform(tracker.move(e.pointerId, e.clientX, e.clientY, e.timeStamp));
  });

  // A single tap's click is held back briefly (see gestures.js); this timer
  // releases it if no second touch arrives.
  let clickTimer = 0;
  const end = (e) => {
    perform(tracker.up(e.pointerId, e.clientX, e.clientY, e.timeStamp));
    if (tracker.pointers.size === 0) element.classList.remove('active');
    if (tracker.hasPendingClick) {
      clearTimeout(clickTimer);
      clickTimer = setTimeout(() => perform(tracker.expire(performance.now())), DOUBLE_TAP_MS + 5);
    }
  };
  element.addEventListener('pointerup', end);
  element.addEventListener('pointercancel', () => {
    perform(tracker.cancel());
    element.classList.remove('active');
  });

  // --- Scroll strip: one finger up/down scrolls ---------------------------
  let stripY = null;
  strip.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    strip.setPointerCapture(e.pointerId);
    strip.classList.add('active');
    stripY = e.clientY;
  });
  strip.addEventListener('pointermove', (e) => {
    if (stripY === null) return;
    const dy = e.clientY - stripY;
    stripY = e.clientY;
    const scroll = panToScroll(0, dy, getOptions());
    queue('scroll', 0, scroll.dy);
  });
  const stripEnd = () => {
    stripY = null;
    strip.classList.remove('active');
    flush();
  };
  strip.addEventListener('pointerup', stripEnd);
  strip.addEventListener('pointercancel', stripEnd);

  return {
    /** Abort any gesture in progress (e.g. the app went to the background). */
    reset() {
      perform(tracker.cancel());
      flush();
    },
  };
}
