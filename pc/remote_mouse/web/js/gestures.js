/**
 * gestures.js — Turns raw finger positions into mouse actions.
 *
 * This file is PURE LOGIC: no DOM, no network, no timers. touchpad.js feeds
 * it finger events (pointer id, x, y, time) and it returns a list of actions:
 *   { type: 'move', dx, dy }      { type: 'click', button: 'left' }
 *   { type: 'scroll', dx, dy }    { type: 'down' | 'up', button: 'left' }
 * Keeping it DOM-free means it can be unit tested in Node (web-tests/).
 *
 * Gestures (like a laptop touchpad):
 *   1 finger slide ........ move the pointer (faster swipes travel further)
 *   1 finger tap .......... left click
 *   tap twice ............. double-click
 *   2 finger tap .......... right click
 *   3 finger tap .......... middle click
 *   2 finger slide ........ scroll (vertical and horizontal)
 *   tap, then touch again
 *   and slide ............. drag (left button held until you lift)
 *
 * Why is a single tap's click slightly delayed?
 *   After a tap we wait DOUBLE_TAP_MS to see whether you touch again to DRAG.
 *   If we clicked immediately and then pressed the button for the drag, Windows
 *   would see "click + press at the same spot" as a double-click (and e.g.
 *   open the file you meant to move). So the click is held back briefly
 *   ("pending"), exactly like laptop touchpads do. touchpad.js calls
 *   `expire()` when the wait is over to release the click.
 */

// --- Tuning constants ------------------------------------------------------
export const TAP_MAX_MS = 250;          // a tap is shorter than this…
export const TAP_SLOP_PX = 10;          // …and moves less than this per finger
export const DOUBLE_TAP_MS = 250;       // wait after a tap for a second touch
export const DOUBLE_TAP_SLOP_PX = 48;   // second touch must be near the first
export const SCROLL_PX_PER_NOTCH = 36;  // finger travel for one wheel notch (speed 1)

// Pointer acceleration: slow movements stay precise, fast flicks go far.
// The curve is smooth (no sudden "knee"), so speeding up feels continuous.
const ACCEL_STRENGTH = 0.9;    // how strong the boost is
const ACCEL_EXPONENT = 1.3;    // >1: gentle at low speed, stronger when fast
const ACCEL_MAX_SPEED = 3.0;   // px/ms above which the boost stops growing
// Finger speed is averaged over ~24 ms. Touch screens report slightly uneven
// timestamps, and using raw per-event speed made the gain (and cursor) jitter.
const SPEED_SMOOTHING_MS = 24;

// Momentum scrolling: a two-finger flick keeps scrolling and slows down.
export const FLING_MIN_SPEED = 0.004; // notches per ms (= 4 notches/s)
const FLING_MAX_IDLE_MS = 60;         // fingers must still be moving at lift-off

const BUTTON_FOR_FINGERS = { 1: 'left', 2: 'right', 3: 'middle' };
const LEFT_CLICK = Object.freeze({ type: 'click', button: 'left' });

export const DEFAULT_OPTIONS = Object.freeze({
  sensitivity: 1.6,
  scrollSpeed: 1.0,
  naturalScroll: true,
});

const clamp = (value, lo, hi) => Math.min(hi, Math.max(lo, value));

/**
 * How much to multiply a finger movement by, given its speed.
 * @param {number} speed  finger speed in CSS px per millisecond
 * @param {number} sensitivity  user setting (1 = phone px → PC px)
 * @returns {number}
 */
export function pointerGain(speed, sensitivity) {
  const s = clamp(speed, 0, ACCEL_MAX_SPEED);
  return sensitivity * (1 + ACCEL_STRENGTH * s ** ACCEL_EXPONENT);
}

/**
 * Exponential moving average that respects uneven time steps.
 * @param {number} previous  last smoothed value
 * @param {number} sample    new raw value
 * @param {number} dt        ms since the last sample
 * @param {number} tau       smoothing time constant in ms
 */
export function smooth(previous, sample, dt, tau) {
  const alpha = 1 - Math.exp(-dt / tau);
  return previous + (sample - previous) * alpha;
}

/**
 * Convert a two-finger pan (finger movement in px) into wheel notches.
 *
 * Screen Y grows downwards but the wheel's "up" is positive, hence the
 * different signs for the two axes. With natural scrolling the content
 * follows your fingers, like on a phone.
 * @returns {{ dx: number, dy: number }}
 */
export function panToScroll(fingerDx, fingerDy, { naturalScroll, scrollSpeed }) {
  const k = scrollSpeed / SCROLL_PX_PER_NOTCH;
  const sign = naturalScroll ? 1 : -1;
  return { dx: -fingerDx * k * sign, dy: fingerDy * k * sign };
}

/**
 * A small state machine that tracks the fingers of one gesture.
 * Call down/move/up for every pointer event; each returns an array of actions.
 */
export class GestureTracker {
  constructor(options = {}) {
    this.options = { ...DEFAULT_OPTIONS, ...options };
    this.pointers = new Map(); // id → { x, y, t }
    this.gesture = null;       // info about the gesture in progress
    this.pendingTap = null;    // { t, x, y }: a left click we're holding back
  }

  setOptions(options) {
    this.options = { ...this.options, ...options };
  }

  /** True while the left button is held by a tap-and-drag. */
  get isDragging() {
    return Boolean(this.gesture && this.gesture.dragging);
  }

  /** True when a click is waiting for DOUBLE_TAP_MS to pass (see top). */
  get hasPendingClick() {
    return this.pendingTap !== null;
  }

  down(id, x, y, t) {
    const actions = [];
    if (this.pointers.size === 0) {
      const isSecondTouch = this._isSecondTouch(x, y, t);
      if (this.pendingTap && !isSecondTouch) actions.push(LEFT_CLICK); // stale: send it now
      this.pendingTap = null;
      this.gesture = {
        startT: t,
        startX: x,
        startY: y,
        maxFingers: 0,
        travel: 0,
        // Second touch right after a tap: maybe a drag, maybe a double-click.
        dragCandidate: isSecondTouch,
        owesClick: isSecondTouch, // the first tap's click hasn't been sent yet
        dragging: false,
        buffered: { dx: 0, dy: 0 }, // movement held back until we know it's a drag
        speed: 0,                   // smoothed finger speed (px/ms)
        scrollV: { x: 0, y: 0 },    // smoothed scroll velocity (notches/ms)
        lastScrollT: -Infinity,
      };
    }
    this.pointers.set(id, { x, y, t });
    const g = this.gesture;
    g.maxFingers = Math.max(g.maxFingers, this.pointers.size);
    if (this.pointers.size > 1 && !g.dragging) g.dragCandidate = false;
    return actions;
  }

  move(id, x, y, t) {
    const prev = this.pointers.get(id);
    const g = this.gesture;
    if (!prev || !g) return [];

    const dx = x - prev.x;
    const dy = y - prev.y;
    const dt = Math.max(1, t - prev.t);
    this.pointers.set(id, { x, y, t });
    g.travel += Math.hypot(dx, dy);

    if (this.pointers.size === 1 && (g.maxFingers === 1 || g.dragging)) {
      g.speed = smooth(g.speed, Math.hypot(dx, dy) / dt, dt, SPEED_SMOOTHING_MS);
      const gain = pointerGain(g.speed, this.options.sensitivity);
      const step = { dx: dx * gain, dy: dy * gain };
      if (g.dragCandidate && !g.dragging) {
        // Don't move yet: the button must go down where you tapped.
        g.buffered = { dx: g.buffered.dx + step.dx, dy: g.buffered.dy + step.dy };
        if (g.travel <= TAP_SLOP_PX) return [];
        g.dragging = true;
        g.owesClick = false; // a tap-and-drag replaces the click
        return [{ type: 'down', button: 'left' }, { type: 'move', ...g.buffered }];
      }
      return [{ type: 'move', ...step }];
    }
    if (this.pointers.size === 2 && !g.dragging) {
      // Each finger's movement counts half, i.e. we follow the midpoint.
      const scroll = panToScroll(dx / 2, dy / 2, this.options);
      // Track velocity per finger-pair update for a possible fling. Both
      // fingers report separately, so each event is roughly half the motion.
      g.scrollV = {
        x: smooth(g.scrollV.x, (scroll.dx * 2) / dt, dt, SPEED_SMOOTHING_MS * 2),
        y: smooth(g.scrollV.y, (scroll.dy * 2) / dt, dt, SPEED_SMOOTHING_MS * 2),
      };
      g.lastScrollT = t;
      return [{ type: 'scroll', ...scroll }];
    }
    // After lifting one of two fingers we deliberately do nothing, so the
    // pointer doesn't jump when a scroll ends.
    return [];
  }

  up(id, x, y, t) {
    if (!this.pointers.has(id)) return [];
    this.pointers.delete(id);
    if (this.pointers.size > 0) return [];

    const g = this.gesture;
    this.gesture = null;
    if (!g) return [];

    if (g.dragging) return [{ type: 'up', button: 'left' }];

    const isTap = t - g.startT <= TAP_MAX_MS && g.travel <= TAP_SLOP_PX * g.maxFingers;
    const button = BUTTON_FOR_FINGERS[Math.min(g.maxFingers, 3)];

    if (g.owesClick && isTap && button === 'left') {
      return [LEFT_CLICK, LEFT_CLICK]; // two quick taps → double-click
    }
    const owed = g.owesClick ? [LEFT_CLICK] : [];
    if (!isTap) return [...owed, ...this._fling(g, t)];
    if (button === 'left') {
      this.pendingTap = { t, x: g.startX, y: g.startY }; // wait: maybe a drag follows
      return owed;
    }
    return [...owed, { type: 'click', button }];
  }

  /** Release a held-back click once DOUBLE_TAP_MS has passed with no new touch. */
  expire(t) {
    if (!this.pendingTap || this.pointers.size > 0) return [];
    if (t - this.pendingTap.t < DOUBLE_TAP_MS) return [];
    this.pendingTap = null;
    return [LEFT_CLICK];
  }

  /** The browser took the touch away (e.g. a system gesture). Clean up. */
  cancel() {
    const wasDragging = this.isDragging;
    this.pointers.clear();
    this.gesture = null;
    this.pendingTap = null;
    return wasDragging ? [{ type: 'up', button: 'left' }] : [];
  }

  /** A two-finger scroll that was still moving at lift-off becomes a fling. */
  _fling(g, t) {
    if (g.maxFingers !== 2 || t - g.lastScrollT > FLING_MAX_IDLE_MS) return [];
    const { x, y } = g.scrollV;
    if (Math.hypot(x, y) < FLING_MIN_SPEED) return [];
    return [{ type: 'fling', vx: x, vy: y }];
  }

  _isSecondTouch(x, y, t) {
    const last = this.pendingTap;
    return Boolean(
      last &&
        t - last.t <= DOUBLE_TAP_MS &&
        Math.hypot(x - last.x, y - last.y) <= DOUBLE_TAP_SLOP_PX,
    );
  }
}
