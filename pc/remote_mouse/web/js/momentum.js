/**
 * momentum.js — "Flick to keep scrolling", like scrolling on a phone.
 *
 * After a fast two-finger flick, the page keeps scrolling and gradually slows
 * down. Physics: velocity decays exponentially, v(t) = v0 · e^(−t/τ).
 * The distance travelled in a time step is the exact integral of that curve,
 * so the result is identical whether frames come at 60 Hz or 120 Hz.
 *
 * PURE LOGIC (no DOM/timers) — touchpad.js drives it with animation frames,
 * and web-tests/ checks the maths.
 */

export const MOMENTUM_TAU_MS = 325;     // how quickly it slows (bigger = glides longer)
export const MOMENTUM_STOP_SPEED = 0.0006; // notches/ms below which we stop
export const MOMENTUM_MAX_SPEED = 0.25;    // safety cap (250 notches/s)

/**
 * Advance one time step.
 * @returns {{ v: number, delta: number }} new velocity and distance to scroll
 */
export function momentumStep(v, dt, tau = MOMENTUM_TAU_MS) {
  const decay = Math.exp(-dt / tau);
  return { v: v * decay, delta: v * tau * (1 - decay) };
}

export class Momentum {
  constructor() {
    this.vx = 0;
    this.vy = 0;
    this.lastT = 0;
  }

  get active() {
    return this.vx !== 0 || this.vy !== 0;
  }

  start(vx, vy, t) {
    const cap = (v) => Math.max(-MOMENTUM_MAX_SPEED, Math.min(MOMENTUM_MAX_SPEED, v));
    this.vx = cap(vx);
    this.vy = cap(vy);
    this.lastT = t;
  }

  stop() {
    this.vx = 0;
    this.vy = 0;
  }

  /** Distance to scroll since the last call; stops itself when slow enough. */
  step(t) {
    if (!this.active) return { dx: 0, dy: 0 };
    const dt = Math.max(0, t - this.lastT);
    this.lastT = t;
    const x = momentumStep(this.vx, dt);
    const y = momentumStep(this.vy, dt);
    this.vx = x.v;
    this.vy = y.v;
    if (Math.hypot(this.vx, this.vy) < MOMENTUM_STOP_SPEED) this.stop();
    return { dx: x.delta, dy: y.delta };
  }
}
