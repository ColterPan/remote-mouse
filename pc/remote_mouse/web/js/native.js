/**
 * native.js — Lets the SAME remote page run inside the Android app.
 *
 * In a normal browser, connection.js uses a WebSocket straight to the PC.
 * Inside the Android app, the native side owns the connection instead (with
 * certificate pinning, network discovery and a low-latency Wi-Fi lock), and
 * the page talks to it through a message channel the app injects as
 * `window.RemoteMouseNative`.
 *
 * NativeSocket imitates the small part of the WebSocket API that
 * connection.js uses (readyState, send, close, open/message/close events), so
 * connection.js works unchanged in both worlds.
 *
 * Every connection attempt gets an id (`cid`); events from an older attempt
 * are ignored, so a slow failure can never close a newer connection.
 */

const CONNECTING = 0;
const OPEN = 1;
const CLOSED = 3;
const AUTH_PREFIX = '{"t":"auth"';
const UNAUTHORIZED = 4401;
const UNKNOWN_PC = 4404;

/** The app's message channel, or null when running in a normal browser. */
export function nativeBridge() {
  const bridge = globalThis.RemoteMouseNative;
  return bridge && typeof bridge.postMessage === 'function' ? bridge : null;
}

export class NativeHost {
  /** @param {{ postMessage(text: string): void, onmessage?: Function }} bridge */
  constructor(bridge) {
    this.bridge = bridge;
    this.handlers = new Map();
    this.socket = null;
    this.nextCid = 1;
    bridge.onmessage = (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }
      this._dispatch(message);
    };
  }

  /** Ask the native side to do something, e.g. request('scan'). */
  request(op, payload = {}) {
    this.bridge.postMessage(JSON.stringify({ op, ...payload }));
  }

  /** Listen for native events: 'pcs', 'status', 'paired', 'scanError'. */
  on(event, handler) {
    this.handlers.set(event, [...(this.handlers.get(event) || []), handler]);
  }

  /** Start a connection to a saved PC; returns a WebSocket look-alike. */
  openSocket(pcId) {
    const socket = new NativeSocket(this, this.nextCid++);
    this.socket = socket;
    this.request('connect', { id: pcId, cid: socket.cid });
    return socket;
  }

  _dispatch(message) {
    const forSocket = message.ev === 'open' || message.ev === 'message' || message.ev === 'close';
    if (forSocket || message.ev === 'status') {
      if (!this.socket || this.socket.cid !== message.cid) return; // stale attempt
      if (forSocket) {
        this.socket._receive(message);
        return;
      }
    }
    for (const handler of this.handlers.get(message.ev) || []) handler(message);
  }
}

export class NativeSocket extends EventTarget {
  constructor(host, cid) {
    super();
    this.host = host;
    this.cid = cid;
    this.readyState = CONNECTING;
  }

  send(text) {
    if (this.readyState !== OPEN) return;
    if (text.startsWith(AUTH_PREFIX)) return; // the app already logged in for us
    this.host.request('send', { msg: text });
  }

  close() {
    if (this.readyState === CLOSED) return;
    this.readyState = CLOSED;
    if (this.host.socket === this) {
      this.host.socket = null;
      this.host.request('disconnect');
    }
  }

  _receive(message) {
    if (message.ev === 'open') {
      this.readyState = OPEN;
      this.dispatchEvent(new Event('open'));
      this._emitMessage(message.data); // the PC's "hello"
    } else if (message.ev === 'message') {
      this._emitMessage(message.data);
    } else if (message.ev === 'close') {
      this.readyState = CLOSED;
      if (this.host.socket === this) this.host.socket = null;
      const event = new Event('close');
      // 4404 = "this PC isn't saved on the phone": same outcome as a rejected
      // token — the user needs to pair (scan) again.
      event.code = message.code === UNKNOWN_PC ? UNAUTHORIZED : message.code;
      this.dispatchEvent(event);
    }
  }

  _emitMessage(data) {
    const event = new Event('message');
    event.data = data;
    this.dispatchEvent(event);
  }
}
