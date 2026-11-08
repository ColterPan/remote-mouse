/**
 * textdiff.js — Works out what the user typed by comparing two strings.
 *
 * Why? Phone keyboards (Gboard, Samsung, SwiftKey) don't reliably report
 * individual key presses to web pages — Android usually says "key 229,
 * unidentified". What we CAN see reliably is the text field's value before
 * and after each change. So:
 *
 *   before: "hel"      after: "help"   → type "p"
 *   before: "teh"      after: "the"    → 2 backspaces, then type "he"
 *                                        (autocorrect rewrote the word)
 *
 * Comparison is done per Unicode code point, so an emoji counts as one
 * character (one backspace), not two UTF-16 halves.
 *
 * @param {string} previous
 * @param {string} next
 * @returns {{ deleteCount: number, insert: string }}
 */
export function diffText(previous, next) {
  const before = Array.from(previous);
  const after = Array.from(next);
  let common = 0;
  const limit = Math.min(before.length, after.length);
  while (common < limit && before[common] === after[common]) common += 1;
  return {
    deleteCount: before.length - common,
    insert: after.slice(common).join(''),
  };
}
