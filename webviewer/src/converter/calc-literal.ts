/**
 * calc-literal.ts — the FileMaker calculation text-literal grammar for the converters.
 *
 * Every converter scanner that must step over (or decode) a text literal inside
 * calculation text uses these helpers: the HR line parser's bracket finders and
 * `;` parameter splitter (parser.ts), the catalog emitter's value splitters
 * (`parametersList` commas, `attrGroup`/`repeatGroup` bodies, `fieldList` entries)
 * and the group-value quoting on both directions (catalog-grammar.ts). The Python
 * counterpart is `agent/scripts/calc_literal.py`; keep the two in step.
 *
 * Grammar, measured against FileMaker Pro 26.0.2:
 *  - `"`, `“` (U+201C) and `”` (U+201D) are ONE interchangeable delimiter: a
 *    literal opens on any unescaped one and closes on any unescaped one (`"ab”`,
 *    `”ab“` and `“ab"` are all the literal `ab`). FileMaker stores a pasted
 *    curly-delimited literal with straight quotes.
 *  - Inside a literal a backslash escapes the next `"`, `“`, `”`, `\` or `¶`
 *    (`"a\"b"` is `a"b`, `"a\\b"` is `a\b`). Before any other character the
 *    backslash is ordinary content (`"a\nb"` is the four characters `a\nb`).
 *    FileMaker stores a doubled quote as the backslash form (`"a""b"` comes back
 *    as `"a\"b"`).
 *  - Inside a literal a delimiter immediately followed by another delimiter is the
 *    doubled escape: the second character is content (`"a""b"` is `a"b`).
 *  - `'`, `‘` and `’` are never calculation delimiters.
 * A delimiter preceded by an odd backslash run outside a literal does not open one.
 */

const CALC_QUOTES = '"“”';
/** Characters a backslash escapes inside a literal. */
const ESCAPABLE = '"“”\\¶';

/** True when `c` is one of the three calculation literal delimiters. */
export function isCalcQuote(c: string | undefined): boolean {
  return c !== undefined && c.length === 1 && CALC_QUOTES.includes(c);
}

/** True when the character at `at` is preceded by an odd run of backslashes. */
export function isBackslashEscaped(s: string, at: number): boolean {
  let run = 0;
  while (at > 0 && s[at - 1] === '\\') { run++; at--; }
  return run % 2 === 1;
}

/**
 * True when `s[at]` is a literal delimiter not preceded by an odd backslash run.
 * In a toggle-style scanner every such character flips in/out of a literal,
 * because the three delimiters pair freely (the doubled escape toggles twice).
 */
export function isUnescapedCalcQuote(s: string, at: number): boolean {
  return isCalcQuote(s[at]) && !isBackslashEscaped(s, at);
}

/** True when the backslash at `at` (inside a literal) escapes the next character. */
export function isCalcEscape(s: string, at: number): boolean {
  return s[at] === '\\' && at + 1 < s.length && ESCAPABLE.includes(s[at + 1]);
}

/**
 * Scan the literal whose opening delimiter is `s[at]`. Returns the offset just
 * past its closing delimiter (`s.length` when unterminated, `closed` false) and
 * the literal's value with escapes and doubled delimiters resolved and the
 * enclosing delimiters dropped.
 */
export function skipCalcLiteral(s: string, at: number): { end: number; closed: boolean; decoded: string } {
  let decoded = '';
  let i = at + 1;
  while (i < s.length) {
    const c = s[i];
    if (c === '\\' && isCalcEscape(s, i)) { decoded += s[i + 1]; i += 2; continue; }
    if (isCalcQuote(c)) {
      if (isCalcQuote(s[i + 1])) { decoded += s[i + 1]; i += 2; continue; }
      return { end: i + 1, closed: true, decoded };
    }
    decoded += c;
    i++;
  }
  return { end: s.length, closed: false, decoded };
}

/**
 * Length of the text literal that opens at `at` (0 when none opens there). An
 * unterminated literal runs to the end of `s`.
 */
export function calcLiteralSpanAt(s: string, at: number): number {
  if (!isUnescapedCalcQuote(s, at)) return 0;
  return skipCalcLiteral(s, at).end - at;
}
