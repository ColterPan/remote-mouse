/**
 * touchpad.js — Connects the on-screen touchpad and scroll strip to the PC.
 *
 * Flow:  finger events → GestureTracker (gestures.js) decides what they mean
 *        → movement/scroll is sent to the PC
 *
 * How it stays smooth and responsive:
 *  • `pointerrawupdate` events (when the browser supports them) arrive as soon
 *    as the touch screen reports, instead of once per screen refresh like
 *    `pointermove`. Otherwise we unpack `getCoalescedEvents()` so no touch
 *    samples are lost.
 *  • Movement is sent IMMEDIATELY, merged so that at most one message leaves
 *    every SEND_INTERVAL_MS (~125 per second). Previously we waited for the
 *    next animation frame, which added up to a frame or two of lag.
 *  • Clicks and button presses flush pending movement first, so order is kept.
 *  • A two-finger flick (or a flick on the scroll strip) continues as momentum
 *    scrolling (momentum.js); touching the pad again stops it instantly.
 */

import { DOUBLE_TAP_MS, FLING_MIN_SPEED, GestureTracker, panToScroll, smooth } from './gestures.js';
import { Momentum } from './momentum.js';

export const SEND_INTERVAL_MS = 8;
const round = (value) => Math.round(value * 1000) / 1000;
const supportsRawUpdate = typeof window !== 'undefined' && 'onpointerrawupdate' in window;

/**
 * @param {object} opts
 * @param {HTMLElement} opts.element      the touchpad
 * @param {HTMLElement} opts.strip        the one-finger scroll strip
 * @param {(msg: object) => void} opts.send
 * @param {() => object} opts.getOptions  current sensitivity/scroll settings
 * @param {() => void} opts.onClick       e.g. vibrate
 * @param {() => void} [opts.onFirstUse]  e.g. hide the tips card
 */
export function createTouchpad({ element, strip, send, getOptions, onClick, onFirstUse = () => {} }) {
  const tracker = new GestureTracker(getOptions());
  const momentum = new Momentum();
  let pending = { mx: 0, my: 0, sx: 0, sy: 0 };
  let lastSent = -Infinity;
  let sendTimer = 0;
  let momentumFrame = 0;

  // --- Sending ---------------------------------------------------------------

  function flush() {
    clearTimeout(sendTimer);
    sendTimer = 0;
    const { mx, my, sx, sy } = pending;
    pending = { mx: 0, my: 0, sx: 0, sy: 0 };
    if (mx || my) send({ t: 'move', dx: round(mx), dy: round(my) });
    if (sx || sy) send({ t: 'scroll', dx: round(sx), dy: round(sy) });
    lastSent = performance.now();
  }

  function queue(kind, dx, dy) {
    pending =
      kind === 'move'
        ? { ...pending, mx: pending.mx + dx, my: pending.my + dy }
        : { ...pending, sx: pending.sx + dx, sy: pending.sy + dy };
    const wait = SEND_INTERVAL_MS - (performance.now() - lastSent);
    if (wait <= 0) flush();
    else if (!sendTimer) sendTimer = setTimeout(flush, wait);
  }

  // --- Momentum scrolling ----------------------------------------------------

  function stopMomentum() {
    momentum.stop();
    cancelAnimationFrame(momentumFrame);
    momentumFrame = 0;
  }

  function startMomentum(vx, vy) {
    if (!getOptions().momentum) return;
    momentum.start(vx, vy, performance.now());
    const tick = (now) => {
      const { dx, dy } = momentum.step(now);
      if (dx || dy) queue('scroll', dx, dy);
      momentumFrame = momentum.active ? requestAnimationFrame(tick) : 0;
    };
    momentumFrame = requestAnimationFrame(tick);
  }

  // --- Gesture actions -------------------------------------------------------

  function perform(actions) {
    for (const action of actions) {
      if (action.type === 'move' || action.type === 'scroll') {
        queue(action.type, action.dx, action.dy);
        continue;
      }
      if (action.type === 'fling') {
        startMomentum(action.vx, action.vy);
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

  /** Feed every touch sample (including coalesced ones) to the tracker. */
  function samples(e) {
    if (e.type === 'pointermove' && typeof e.getCoalescedEvents === 'function') {
      const list = e.getCoalescedEvents();
      if (list.length) return list;
    }
    return [e];
  }

  // --- Touchpad ------------------------------------------------------------
  element.addEventListener('pointerdown', (e) => {
    e.preventDefault(); // keep the phone keyboard open and stop text selection
    stopMomentum();
    element.setPointerCapture(e.pointerId);
    tracker.setOptions(getOptions());
    element.classList.add('active');
    onFirstUse();
    perform(tracker.down(e.pointerId, e.clientX, e.clientY, e.timeStamp));
  });

  element.addEventListener(supportsRawUpdate ? 'pointerrawupdate' : 'pointermove', (e) => {
    for (const s of samples(e)) {
      perform(tracker.move(e.pointerId, s.clientX, s.clientY, s.timeStamp));
    }
  });

  // A single tap's click is held back briefly (see gestures.js); this timer
  // releases it if no second touch arrives.
  let clickTimer = 0;
  element.addEventListener('pointerup', (e) => {
    // Apply the lift-off position as a final movement first. Android WebView
    // can drop some move events during the first gesture after the page
    // loads; positions are absolute, so this recovers any missing distance.
    perform(tracker.move(e.pointerId, e.clientX, e.clientY, e.timeStamp));
    perform(tracker.up(e.pointerId, e.clientX, e.clientY, e.timeStamp));
    if (tracker.pointers.size === 0) element.classList.remove('active');
    if (tracker.hasPendingClick) {
      clearTimeout(clickTimer);
      clickTimer = setTimeout(() => perform(tracker.expire(performance.now())), DOUBLE_TAP_MS + 5);
    }
  });
  element.addEventListener('pointercancel', () => {
    perform(tracker.cancel());
    element.classList.remove('active');
  });

  // --- Scroll strip: one finger up/down scrolls, flick for momentum --------
  let stripLast = null; // { y, t }
  let stripV = 0;
  strip.addEventListener('pointerdown', (e) => {
    e.preventDefault();
    stopMomentum();
    strip.setPointerCapture(e.pointerId);
    strip.classList.add('active');
    stripLast = { y: e.clientY, t: e.timeStamp };
    stripV = 0;
  });
  strip.addEventListener(supportsRawUpdate ? 'pointerrawupdate' : 'pointermove', (e) => {
    if (!stripLast) return;
    for (const s of samples(e)) {
      const dt = Math.max(1, s.timeStamp - stripLast.t);
      const { dy } = panToScroll(0, s.clientY - stripLast.y, getOptions());
      stripV = smooth(stripV, dy / dt, dt, 48);
      stripLast = { y: s.clientY, t: s.timeStamp };
      queue('scroll', 0, dy);
    }
  });
  const stripEnd = (e) => {
    if (stripLast && e.type === 'pointerup') {
      // Same safeguard as the touchpad: don't lose the last stretch of scrolling.
      queue('scroll', 0, panToScroll(0, e.clientY - stripLast.y, getOptions()).dy);
    }
    const recent = stripLast && e.timeStamp - stripLast.t < 60;
    stripLast = null;
    strip.classList.remove('active');
    flush();
    if (recent && Math.abs(stripV) >= FLING_MIN_SPEED) startMomentum(0, stripV);
  };
  strip.addEventListener('pointerup', stripEnd);
  strip.addEventListener('pointercancel', stripEnd);

  return {
    /** Abort any gesture in progress (e.g. the app went to the background). */
    reset() {
      stopMomentum();
      perform(tracker.cancel());
      flush();
    },
  };
}
