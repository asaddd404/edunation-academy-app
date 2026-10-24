/**
 * `$...$` inline formulas inside plain question and answer text.
 *
 * Lesson bodies are TipTap documents with their own math nodes; question
 * text, answer options and matching pairs are plain strings, and teachers
 * (and the demo bank) write formulas into them as `$x^2 - 4 = 0$`. Without
 * this the dollar signs and backslashes reached the student verbatim.
 *
 * The delimiter rule is the usual one, chosen so prices and lone dollar
 * signs stay text: an opening `$` must be followed by a non-space, a closing
 * `$` preceded by one, the formula sits on one line, and `\$` is a literal.
 */

export type MathSegment = { type: "text"; value: string } | { type: "math"; value: string };

const INLINE_MATH = /(?<!\\)\$(?=\S)((?:\\\$|[^$\n])+?)(?<=\S)(?<!\\)\$/g;

export function hasInlineMath(text: string): boolean {
  INLINE_MATH.lastIndex = 0;
  return INLINE_MATH.test(text);
}

export function splitInlineMath(text: string): MathSegment[] {
  const segments: MathSegment[] = [];
  let last = 0;
  for (const match of text.matchAll(INLINE_MATH)) {
    const start = match.index ?? 0;
    if (start > last) segments.push({ type: "text", value: text.slice(last, start) });
    segments.push({ type: "math", value: match[1] });
    last = start + match[0].length;
  }
  if (last < text.length) segments.push({ type: "text", value: text.slice(last) });
  return segments;
}

const SUPERSCRIPT: Record<string, string> = { "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹", "-": "⁻", "+": "⁺", n: "ⁿ", x: "ˣ" };
const SYMBOLS: Record<string, string> = {
  pi: "π", cdot: "·", times: "×", div: "÷", pm: "±", le: "≤", leq: "≤", ge: "≥", geq: "≥", ne: "≠", neq: "≠",
  circ: "°", infty: "∞", alpha: "α", beta: "β", Delta: "Δ", sin: "sin", cos: "cos", tg: "tg", operatorname: "", log: "log", ln: "ln",
};

function latexToPlain(latex: string): string {
  let s = latex;
  for (let i = 0; i < 3; i++) {
    s = s.replace(/\\frac\{([^{}]*)\}\{([^{}]*)\}/g, "$1/$2").replace(/\\sqrt\{([^{}]*)\}/g, "√$1");
  }
  s = s.replace(/\^\{?\\circ\}?/g, "°");
  s = s.replace(/\^\{([^{}]*)\}/g, (_, p: string) => [...p].map((c) => SUPERSCRIPT[c] ?? `^${c}`).join(""));
  s = s.replace(/\^(\S)/g, (_, c: string) => SUPERSCRIPT[c] ?? `^${c}`);
  s = s.replace(/_\{([^{}]*)\}/g, "$1").replace(/_(\S)/g, "$1");
  s = s.replace(/\\([A-Za-z]+)/g, (_, name: string) => SYMBOLS[name] ?? name);
  return s.replace(/[{}]/g, "").replace(/\\\$/g, "$").replace(/\s+/g, " ").trim();
}

/** A readable plain-text rendering, for places that cannot hold markup --
 * a native <option>, a title attribute. */
export function inlineMathToPlain(text: string): string {
  return splitInlineMath(text)
    .map((segment) => (segment.type === "math" ? latexToPlain(segment.value) : segment.value))
    .join("");
}
