/**
 * calc-literal.ts — the FileMaker calculation text-literal and comment grammar for the converters.
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
 *
 * Calculation comments, measured against FileMaker Pro 26.0.2:
 *  - A slash-star opens a block comment that runs to its MATCHING star-slash:
 *    block comments nest (`1 /* a /* b ⁎/ c ⁎/ + 2`, with ⁎/ standing for the
 *    closer, is 3). An unmatched opener is error 1205.
 *  - `//` opens a line comment that runs to the next return (FileMaker stores a
 *    return in a calculation as CR; HR text carries it as LF; a pasted LF is
 *    stored as CR).
 *  - Inside a comment nothing is structure: a quote opens no literal, `//` inside
 *    a block comment and `/*` inside a line comment are plain text.
 *  - A comment opens only outside a literal.
 * The HR splitters use a narrower comment rule (`hrCalcCommentSpanAt`), because a
 * step line mixes calculations with bare values such as file paths. Their
 * parenthesis and bracket depth reads every form FileMaker reads as one
 * (`isCalcOpenParen` and its siblings, `hrBracketDepthDelta`, below).
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

/**
 * Write `v` as ONE text literal between `open` and `close` that `skipCalcLiteral`
 * decodes back to exactly `v`. Every embedded delimiter is backslash-escaped, and
 * a backslash is escaped only when it would otherwise escape what follows it (the
 * next character is escapable, or it is last and would escape the closing
 * delimiter). Everything else is written verbatim, so a value with no delimiter
 * and no such backslash reads exactly as FileMaker displays a quoted literal text
 * parameter (`“x”`, `“a\b”`; FileMaker itself never escapes the value it displays).
 */
export function quoteCalcLiteral(v: string, open = '“', close = '”'): string {
  let out = open;
  for (let i = 0; i < v.length; i++) {
    const c = v[i];
    if (isCalcQuote(c)) out += '\\' + c;
    else if (c === '\\' && (i === v.length - 1 || isCalcEscape(v, i))) out += '\\\\';
    else out += c;
  }
  return out + close;
}

/**
 * The decoded value when `s` is exactly one closed text literal (its first
 * character opens it and its closing delimiter is its last character); `null` for
 * anything else (bare text, two literals, an unterminated one, trailing text).
 */
export function decodeWholeCalcLiteral(s: string): string | null {
  if (!isCalcQuote(s[0])) return null;
  const { end, closed, decoded } = skipCalcLiteral(s, 0);
  return closed && end === s.length ? decoded : null;
}

// ---------------------------------------------------------------------------
// Calculation comments
// ---------------------------------------------------------------------------

/**
 * Length of the calculation comment that opens at `at`, and whether it closes
 * (`{ len: 0 }` when no `/*` or `//` starts there; the caller has established
 * that `at` is outside a literal). A block comment runs past its matching close
 * (block comments nest), or to the end of `s` when it has none. A line comment
 * runs up to, not including, the next CR or LF; it is always closed.
 */
export function calcCommentLen(s: string, at: number): { len: number; closed: boolean } {
  if (at + 1 >= s.length || s[at] !== '/') return { len: 0, closed: false };
  if (s[at + 1] === '/') {
    let i = at + 2;
    while (i < s.length && s[i] !== '\n' && s[i] !== '\r') i++;
    return { len: i - at, closed: true };
  }
  if (s[at + 1] !== '*') return { len: 0, closed: false };
  let depth = 1;
  let i = at + 2;
  while (i + 1 < s.length) {
    if (s[i] === '/' && s[i + 1] === '*') { depth++; i += 2; }
    else if (s[i] === '*' && s[i + 1] === '/') {
      i += 2;
      if (--depth === 0) return { len: i - at, closed: true };
    } else i++;
  }
  return { len: s.length - at, closed: false };
}

/** A comment opens in HR text only after one of these (or at the start). */
const HR_COMMENT_MAY_FOLLOW = ' \t\r\n()[]{};,&+=<>^"“”';

/**
 * True when a comment opener at `at` is not glued to a word or path character.
 * HR step text mixes calculations with bare non-calculation values (a file path
 * `filewin://srv/a.csv`, `file:a//b`, a Flow URL), and a splitter cannot tell
 * which a value is before it has split the line, so a comment opens only where a
 * calculation token can end (`$y//note`, which FileMaker accepts, is then read as
 * plain text, exactly as before comments were recognised).
 */
export function hrCalcCommentMayOpenAfter(s: string, at: number): boolean {
  return at === 0 || HR_COMMENT_MAY_FOLLOW.includes(s[at - 1]);
}

/**
 * Length of the comment an HR splitter steps over at `at` (0 when none):
 * `calcCommentLen` under the HR rule. An unmatched block comment is not a
 * comment (FileMaker rejects it, and reading it as one would swallow the rest of
 * the step; `hrUnterminatedCalcCommentAt` reports it).
 *
 * `stops` handles the one-line form. FileMaker's Script Workspace draws a
 * calculation's returns as spaces, so its line for a step reads
 * `Height: 400 // Pixels ; Width: 600 // Pixels ; … ]`, and that is also how an
 * author writes it: on the LAST line of `s` (no CR or LF follows the comment) a
 * `//` comment ends before the first character of `stops`, the separator the
 * caller splits on (`;` for step parameters, `,` for a list, `|` for repeated
 * entries). A comment followed by a line break runs to that break, whatever it
 * holds. XML→HR writes a line break after a comment whose text holds such a
 * character (`hrNeedsLineBreakAfter`), so its own output never depends on it.
 */
export function hrCalcCommentSpanAt(s: string, at: number, stops = ''): number {
  if (at + 1 >= s.length || s[at] !== '/' || (s[at + 1] !== '/' && s[at + 1] !== '*')) return 0;
  if (!hrCalcCommentMayOpenAfter(s, at)) return 0;
  const { len, closed } = calcCommentLen(s, at);
  if (!closed) return 0;
  if (s[at + 1] === '/' && at + len === s.length && stops) {
    for (let j = at + 2; j < s.length; j++) if (stops.includes(s[j])) return j - at;
  }
  return len;
}

/** True when an unmatched block-comment opener (one `hrCalcCommentSpanAt` declines only because it never closes) opens at `at`. */
export function hrUnterminatedCalcCommentAt(s: string, at: number): boolean {
  if (at + 1 >= s.length || s[at] !== '/' || s[at + 1] !== '*') return false;
  if (!hrCalcCommentMayOpenAfter(s, at)) return false;
  return !calcCommentLen(s, at).closed;
}

/**
 * Length of the opaque span an HR splitter steps over whole at `at`: a text
 * literal (an unterminated one runs to the end) or a comment. 0 when neither
 * opens there. A separator, bracket or quote inside the span is content.
 */
export function hrCalcOpaqueSpanAt(s: string, at: number, stops = ''): number {
  return calcLiteralSpanAt(s, at) || hrCalcCommentSpanAt(s, at, stops);
}

/**
 * True when XML→HR must break the line after the HR token `token` (one value as
 * rendered, e.g. `Height: 400 // Pixels`) and before the separator `sep` that
 * follows it (` ; `, `, `, ` | `, or the step's closing ` ]`): `token` ends inside
 * a `//` line comment whose text holds `;`, `]` or the separator's own character,
 * which the one-line reading of `hrCalcCommentSpanAt` would take as structure.
 * Any other trailing comment (`Height: 400 // Pixels ; …`) stays on one line.
 */
export function hrNeedsLineBreakAfter(token: string, sep: string): boolean {
  let i = 0;
  while (i < token.length) {
    const lit = calcLiteralSpanAt(token, i);
    if (lit) { i += lit; continue; }
    const c = hrCalcCommentSpanAt(token, i);
    if (c) {
      if (token[i + 1] === '/' && i + c === token.length) {
        const text = token.slice(i + 2);
        const own = sep.trim()[0] ?? ']';
        return text.includes(';') || text.includes(']') || text.includes(own);
      }
      i += c;
      continue;
    }
    i++;
  }
  return false;
}

/**
 * The separator XML→HR writes after the HR token `token`: `sep` as is, or a line
 * break followed by `sep` without its leading space when `token` ends in a `//`
 * comment the one-line reading would cut (`hrNeedsLineBreakAfter`).
 */
export function hrSep(token: string, sep: string): string {
  if (!hrNeedsLineBreakAfter(token, sep)) return sep;
  return '\n' + sep.replace(/^ +/, '');
}

// FileMaker reads `﹙` and `（` as `(`, `﹚` and `）` as `)`, `［` as `[` and `］` as
// `]` in a calculation, pairing them freely with the ASCII forms
// (`Left （ "abc" ; 2 ）` is `ab`, `Let ( ［ a = 1 ; b = 2 ] ; a + b )` is 3;
// measured against FileMaker Pro 26.0.2 and 26.0.3). A paste stores them as
// ASCII. Inside a literal they are ordinary text.
const CALC_OPEN_PARENS = '(\uFE59\uFF08';
const CALC_CLOSE_PARENS = ')\uFE5A\uFF09';
const CALC_OPEN_BRACKETS = '[\uFF3B';
const CALC_CLOSE_BRACKETS = ']\uFF3D';

const isOneOf = (forms: string, c: string | undefined): boolean =>
  c !== undefined && c.length === 1 && forms.includes(c);

/** True when `c` is a calculation `(` in any form FileMaker reads as one. */
export function isCalcOpenParen(c: string | undefined): boolean { return isOneOf(CALC_OPEN_PARENS, c); }
/** True when `c` is a calculation `)` in any form FileMaker reads as one. */
export function isCalcCloseParen(c: string | undefined): boolean { return isOneOf(CALC_CLOSE_PARENS, c); }
/** True when `c` is a calculation `[` in any form FileMaker reads as one. */
export function isCalcOpenBracket(c: string | undefined): boolean { return isOneOf(CALC_OPEN_BRACKETS, c); }
/** True when `c` is a calculation `]` in any form FileMaker reads as one. */
export function isCalcCloseBracket(c: string | undefined): boolean { return isOneOf(CALC_CLOSE_BRACKETS, c); }

/**
 * Depth change (+1, -1 or 0) for the bracket at `at` in an HR scan that tracks a
 * step's own `[ ]` (or a field subscript's) with the calculation inside, `depth`
 * brackets being open before `at`. The outer brackets are HR syntax and ASCII
 * only; inside them the calculation's brackets count in every form, so `［` opens
 * only once a bracket is open and `］` closes only a bracket nested inside the
 * outer one: a stray `］` never closes the step.
 */
export function hrBracketDepthDelta(s: string, at: number, depth: number): number {
  const c = s[at];
  if (c === '[') return 1;
  if (c === ']') return -1;
  if (depth > 0 && isCalcOpenBracket(c)) return 1;
  if (depth > 1 && isCalcCloseBracket(c)) return -1;
  return 0;
}
