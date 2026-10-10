/**
 * Line parser for human-readable FileMaker script format.
 *
 * Parses lines like:
 *   # comment text
 *   // Disabled Step [ params ]
 *   Set Variable [ $name ; expression ]
 *   If [ condition ]
 *   Go to Layout [ "LayoutName" ]
 *
 * Every scanner below steps over calculation text literals and comments whole
 * with the shared grammar in calc-literal.ts: `"`, `“` and `”` are one
 * interchangeable delimiter, a delimiter after an odd backslash run is content,
 * and outside a literal a block comment (nesting) and `// …` (to the end of the
 * line) are comments, so a `;`, `[`, `]` or quote inside `"a\" ; b"`, `“c ; d”`
 * or a comment is content, not structure. HR's comment rule is narrower than
 * FileMaker's: an opener glued to a word or path character (`filewin://srv`) is
 * plain text, and an unmatched block-comment opener is plain text (reported by
 * hrToXml as a warning). Comment openers and closers are read in every
 * slash/star form FileMaker reads (`／＊ … ＊／`, `⁄∗`, `／／`); the disabled-step
 * prefix `//` is HR syntax and stays ASCII.
 */

import {
  calcLineCommentOpenLen,
  isCalcQuote,
  skipCalcLiteral,
  calcLiteralSpanAt,
  hrBracketDepthDelta,
  hrCalcOpaqueSpanAt,
  hrUnterminatedCalcCommentAt,
  isCalcCloseBracket,
  isCalcCloseParen,
  isCalcOpenBracket,
  isCalcOpenParen,
  isUnescapedCalcQuote,
} from './calc-literal';

export interface ParsedLine {
  /** Original line text */
  raw: string;
  /** Line number (1-based) */
  lineNumber: number;
  /** Whether step is disabled (// prefix) */
  disabled: boolean;
  /** Whether this is a comment (# prefix) */
  isComment: boolean;
  /** Comment text (for # comments) */
  commentText?: string;
  /** Step name (e.g. "Set Variable", "If") */
  stepName: string;
  /** Raw content inside brackets, or empty string */
  bracketContent: string;
  /** Parsed parameters (semicolon-separated inside brackets) */
  params: string[];
  /** Indentation level (spaces/tabs) */
  indent: number;
  /** An unmatched block-comment opener outside every literal: FileMaker rejects the calc (error 1205); the splitters read it as plain text. */
  unterminatedCalcComment?: boolean;
  /**
   * The step's `]` was found only by reading a literal that never closes as
   * FileMaker's display form (an unescaped quote inside `“…”`): the statement
   * ended at the line's last `]`. hrToXml warns.
   */
  displayFormQuote?: boolean;
}

// --- Comment line breaks ---
//
// FileMaker draws a comment whose text holds a return on several Script
// Workspace lines, each continuation aligned under the text after `# `. HR
// writes it the same way: the break becomes a new line indented past the
// comment's own indentation, two spaces for a CR (the return FileMaker itself
// stores, and the form an author writes) and one tab for an LF (FileMaker keeps
// an LF a pasted `&#10;` put there). A blank line still ends the comment.

const COMMENT_CR_PAD = '  ';
const COMMENT_LF_PAD = '\t';

/** A comment's text with each line break written as an HR continuation (relative to column 0). */
export function encodeHrCommentText(text: string): string {
  return text.replace(/[\r\n]/g, (c) => (c === '\r' ? '\n' + COMMENT_CR_PAD : '\n' + COMMENT_LF_PAD));
}

/** Put the comment line's indentation in front of each of its continuation lines. */
export function indentHrContinuations(hrLine: string, prefix: string): string {
  return prefix ? hrLine.split('\n').join('\n' + prefix) : hrLine;
}

/** `line` continues a comment whose own line starts with the whitespace `lead`. */
export function isHrCommentContinuation(line: string, lead: string): boolean {
  if (!line.startsWith(lead)) return false;
  return line.startsWith(COMMENT_CR_PAD, lead.length) || line.charAt(lead.length) === COMMENT_LF_PAD;
}

/**
 * Where a comment line's `#` sits in its trimmed text: 0 for `# text`, past the
 * `//` for a disabled comment, which XML->HR writes and FileMaker's Script
 * Workspace draws as `// # text`. -1 when the line is not a comment.
 */
function commentHashOffset(trimmed: string): number {
  if (trimmed.startsWith('#')) return 0;
  const m = /^\/\/[ \t]*#/.exec(trimmed);
  return m ? m[0].length - 1 : -1;
}

/**
 * The comment text a merged comment statement carries: `#` (and a disabled
 * comment's `//`) and the first line's leading blanks dropped, each
 * continuation line's pad turned back into its CR or LF. A one-line comment is
 * trimmed at both ends, as before; one that continues keeps every blank inside
 * it. `hash` is the `#`'s offset in `raw`.
 */
function decodeHrCommentText(raw: string, indent: number, hash: number): string {
  const lead = raw.substring(0, indent);
  const stripCr = (s: string) => (s.endsWith('\r') ? s.slice(0, -1) : s);
  const [head, ...rest] = raw.split('\n');
  if (rest.length === 0) return head.substring(hash + 1).trim();
  let text = stripCr(head.substring(hash + 1)).replace(/^[ \t]+/, '');
  for (const physical of rest) {
    const line = stripCr(physical);
    if (isHrCommentContinuation(line, lead)) {
      const lf = line.charAt(lead.length) === COMMENT_LF_PAD;
      text += (lf ? '\n' : '\r') + line.substring(lead.length + (lf ? 1 : 2));
    } else {
      text += '\n' + line; // parseLine handed a raw multi-line comment
    }
  }
  return text;
}

/** Parse a single line of HR script text */
export function parseLine(raw: string, lineNumber: number): ParsedLine {
  const trimmed = raw.trimStart();
  const indent = raw.length - trimmed.length;

  // Empty line
  if (!trimmed) {
    return {
      raw, lineNumber, disabled: false, isComment: false,
      stepName: '', bracketContent: '', params: [], indent,
    };
  }

  // Comment: # ... (its continuation lines merged in by parseScript);
  // a disabled comment is // # ...
  const hash = commentHashOffset(trimmed);
  if (hash >= 0) {
    const commentText = decodeHrCommentText(raw, indent, indent + hash);
    return {
      raw, lineNumber, disabled: hash > 0, isComment: true,
      commentText, stepName: '# (comment)', bracketContent: '',
      params: [], indent,
    };
  }

  // Disabled step: // ...
  let disabled = false;
  let workText = trimmed;
  if (trimmed.startsWith('//')) {
    disabled = true;
    workText = trimmed.substring(2).trim();
  }

  // Extract step name and bracket content
  const bracketIdx = findTopLevelBracket(workText);

  let stepName: string;
  let bracketContent = '';
  let content = '';
  let params: string[] = [];
  let displayFormQuote = false;

  if (bracketIdx >= 0) {
    stepName = workText.substring(0, bracketIdx).trim();
    // Extract content between outermost [ and ]
    let closeBracket = findMatchingBracket(workText, bracketIdx);
    if (closeBracket < 0) {
      closeBracket = findDisplayFormClose(workText, bracketIdx);
      displayFormQuote = closeBracket >= 0;
    }
    // Split the untrimmed content: a line break before the closing `]` ends a
    // `//` comment (XML→HR writes one after a comment that holds a `;`), and
    // trimming it would hand that comment to the one-line reading.
    content = closeBracket >= 0
      ? workText.substring(bracketIdx + 1, closeBracket)
      : workText.substring(bracketIdx + 1);
    bracketContent = content.trim();
    params = splitParams(content);
  } else {
    stepName = workText.trim();
  }

  const parsed: ParsedLine = {
    raw, lineNumber, disabled, isComment: false,
    stepName, bracketContent, params, indent,
  };
  if (hasUnterminatedCalcComment(content)) parsed.unterminatedCalcComment = true;
  if (displayFormQuote) parsed.displayFormQuote = true;
  return parsed;
}

/** Parse all lines of HR script text */
export function parseScript(text: string): ParsedLine[] {
  const rawLines = text.split('\n');
  const merged = mergeMultilineStatements(rawLines);
  return merged.map((m) => parseLine(m.text, m.sourceLineNumber));
}

interface MergedLine {
  text: string;
  sourceLineNumber: number;
}

/**
 * How a `//` line comment ends while a scanner looks for a step's closing `]`.
 * AtLineEnd — the comment runs to the end of its line (the calculation
 * grammar); tried first, so a `]` inside the comment is comment text.
 * YieldsToFinalBracket — the fallback for a line written with the step's own `]`
 * after a trailing comment (`Set Variable [ $x ; Value: $y // note ]`,
 * FileMaker's own line): when the comment's line ends with `]`, that `]` closes
 * the step. Used only when AtLineEnd never closes the statement, so `… // a ; ]`
 * followed by a continuation line keeps its `]` as comment text.
 */
const enum LineCommentEnd { AtLineEnd, YieldsToFinalBracket }

/** Offset just past the literal or comment that opens at `i` (`i` when none does). */
function stepOverOpaque(s: string, i: number, mode: LineCommentEnd, stops = ''): number {
  const span = hrCalcOpaqueSpanAt(s, i, stops);
  if (!span) return i;
  let end = i + span;
  if (mode === LineCommentEnd.YieldsToFinalBracket && !calcLiteralSpanAt(s, i) &&
      calcLineCommentOpenLen(s, i)) {
    let k = end;
    while (k > i + 2 && (s[k - 1] === ' ' || s[k - 1] === '\t')) k--;
    if (k > i + 2 && s[k - 1] === ']') end = k - 1;
  }
  return end;
}

/**
 * An AtLineEnd statement scan that reached the end of the text with its bracket
 * still open: per line (indexed from `first`) the depth carried into it, whether
 * it was entered outside every literal and comment, and the lowest depth at any
 * later line end. A later statement starting on a cleanly entered line is
 * answered from it without rescanning, which keeps a script full of
 * `… // note ]` lines linear.
 */
class OpenScanTrace {
  valid = false;
  startDepth: number[] = [];
  cleanStart: boolean[] = [];
  endMin: number[] = [];
  constructor(readonly first: number) {}

  knownOpenFrom(k: number): boolean {
    if (!this.valid || k <= this.first || k - this.first >= this.cleanStart.length) return false;
    const r = k - this.first;
    return this.cleanStart[r] && this.endMin[r] > this.startDepth[r];
  }
}

/**
 * Index of the line on which the statement starting at line `first` ends: the
 * first line end, reached outside every literal and comment, at which its
 * bracket depth is back to <= 0. -1 when the text ends first (recorded in
 * `trace`). `text` is every line joined with `\n`; `lineStart[k]` is line k's offset.
 */
function statementEndLine(text: string, lineStart: number[], first: number,
                          mode: LineCommentEnd, trace: OpenScanTrace | null): number {
  const nLines = lineStart.length;
  const lineEndDepth: number[] = [];
  const reach = (to: number): void => {
    if (!trace) return;
    while (lineEndDepth.length <= to - first) {
      trace.startDepth.push(0);
      trace.cleanStart.push(false);
      lineEndDepth.push(Infinity);
    }
  };
  reach(first);
  let i = lineStart[first];
  while (i < text.length && (text[i] === ' ' || text[i] === '\t')) i++;
  if (text.startsWith('//', i)) i += 2; // disabled-step prefix, not a comment
  let depth = 0;
  let line = first;
  while (i < text.length) {
    const ch = text[i];
    if (ch === '\n') {
      if (depth <= 0) return line;
      if (trace) {
        reach(line + 1);
        lineEndDepth[line - first] = depth;
        trace.startDepth[line + 1 - first] = depth;
        trace.cleanStart[line + 1 - first] = true;
      }
      line++;
      i++;
      continue;
    }
    if (depth > 0) {
      const past = stepOverOpaque(text, i, mode);
      // FileMaker's display form (endsInDisplayFormClose): a literal at the
      // step's own level that runs past this line's end, on a line ending in a
      // delimiter and `]`, ends the statement on this line.
      if (past !== i && depth === 1 && isUnescapedCalcQuote(text, i)) {
        const eol = text.indexOf('\n', i);
        if (eol !== -1 && past > eol && endsInDisplayFormClose(text, i, eol) >= 0) return line;
      }
      if (past !== i) {
        for (let j = i; j < past; j++) if (text[j] === '\n') line++;
        i = past;
        continue;
      }
    } else if (isUnescapedCalcQuote(text, i)) {
      // A quote before any `[` keeps the historical per-line toggle.
      let past = i + calcLiteralSpanAt(text, i);
      const eol = text.indexOf('\n', i);
      if (eol !== -1 && past > eol) past = eol;
      i = past;
      continue;
    }
    depth += hrBracketDepthDelta(text, i, depth);
    i++;
  }
  if (depth <= 0) return nLines - 1;
  if (trace) {
    reach(nLines - 1);
    lineEndDepth[nLines - 1 - first] = depth;
    trace.endMin = new Array<number>(lineEndDepth.length + 1).fill(Infinity);
    for (let r = lineEndDepth.length - 1; r >= 0; r--) {
      trace.endMin[r] = Math.min(trace.endMin[r + 1], lineEndDepth[r]);
    }
    trace.valid = true;
  }
  return -1;
}

/**
 * Merge continuation lines into their opening statement.
 * A statement runs to the first line end, outside every literal and comment,
 * at which its brackets balance; its lines are joined with `\n`.
 *
 * Comment lines (`#`) and empty lines at bracket depth 0 pass through unchanged.
 */
function mergeMultilineStatements(lines: string[]): MergedLine[] {
  const result: MergedLine[] = [];
  if (lines.length === 0) return result;
  const lineStart: number[] = [];
  let pos = 0;
  for (const l of lines) { lineStart.push(pos); pos += l.length + 1; }
  const text = lines.join('\n');

  let trace = new OpenScanTrace(0);
  let k = 0;
  while (k < lines.length) {
    const trimmed = lines[k].trim();
    if (trimmed === '') {
      result.push({ text: lines[k], sourceLineNumber: k + 1 });
      k++;
      continue;
    }
    // A comment, enabled or disabled, takes its continuation lines with it
    // (encodeHrCommentText).
    if (commentHashOffset(trimmed) >= 0) {
      const lead = lines[k].substring(0, lines[k].length - lines[k].trimStart().length);
      let j = k + 1;
      while (j < lines.length && isHrCommentContinuation(lines[j], lead)) j++;
      result.push({ text: lines.slice(k, j).join('\n'), sourceLineNumber: k + 1 });
      k = j;
      continue;
    }
    let last = -1;
    if (!trace.knownOpenFrom(k)) {
      const fresh = new OpenScanTrace(k);
      last = statementEndLine(text, lineStart, k, LineCommentEnd.AtLineEnd, fresh);
      if (fresh.valid) trace = fresh;
    }
    if (last < 0) last = statementEndLine(text, lineStart, k, LineCommentEnd.YieldsToFinalBracket, null);
    if (last < 0) last = lines.length - 1; // unclosed: the rest, as before
    result.push({ text: lines.slice(k, last + 1).join('\n'), sourceLineNumber: k + 1 });
    k = last + 1;
  }
  return result;
}

/**
 * Find the first top-level '[' that starts the parameter list.
 * Skips brackets inside text literals.
 */
function findTopLevelBracket(text: string): number {
  let inQuote = false;
  for (let i = 0; i < text.length; i++) {
    if (isUnescapedCalcQuote(text, i)) inQuote = !inQuote;
    if (!inQuote && text[i] === '[') return i;
  }
  return -1;
}

function findMatchingBracketIn(text: string, openIdx: number, mode: LineCommentEnd): number {
  let depth = 0;
  let i = openIdx;
  while (i < text.length) {
    const past = stepOverOpaque(text, i, mode);
    if (past !== i) { i = past; continue; }
    const delta = hrBracketDepthDelta(text, i, depth);
    depth += delta;
    if (delta < 0 && depth === 0) return i;
    i++;
  }
  return -1;
}

/**
 * Find the matching closing ']' for an opening '['.
 * Handles nested brackets, text literals and comments.
 */
function findMatchingBracket(text: string, openIdx: number): number {
  const idx = findMatchingBracketIn(text, openIdx, LineCommentEnd.AtLineEnd);
  return idx >= 0 ? idx : findMatchingBracketIn(text, openIdx, LineCommentEnd.YieldsToFinalBracket);
}

/**
 * FileMaker draws a literal text parameter as `“` + value + `”` and never
 * escapes the value, so a value holding an odd number of quotes (`He said “hi`)
 * shows as `… ; “He said “hi” ]`: read with the literal grammar, its last
 * delimiter opens a literal that never closes and swallows the step's `]` (and,
 * in a script, every later line). The display form ends with that closing
 * delimiter, optional blanks and the step's `]`. Returns the `]`'s offset when
 * the text of one line, from the dangling literal's opening delimiter at
 * `litOpen` to `lineEnd`, ends that way (trailing blanks and a CR allowed), else
 * -1. The delimiter may be escaped (`“a\”` is the value `a\`) or be the
 * literal's own opener.
 */
function endsInDisplayFormClose(s: string, litOpen: number, lineEnd: number): number {
  let k = lineEnd;
  while (k > litOpen && (s[k - 1] === ' ' || s[k - 1] === '\t' || s[k - 1] === '\r')) k--;
  if (k <= litOpen || s[k - 1] !== ']') return -1;
  const close = k - 1;
  k = close;
  while (k > litOpen && (s[k - 1] === ' ' || s[k - 1] === '\t')) k--;
  return k > litOpen && isCalcQuote(s[k - 1]) ? close : -1;
}

/**
 * The display-form reading of a statement whose `[` at `openIdx` found no
 * matching `]`: the first literal opened at the step's own bracket level (not
 * inside a calculation bracket) that never closes, starts on the statement's
 * last line, and runs to a line ending in a delimiter and `]`
 * (endsInDisplayFormClose). Returns that `]`, or -1.
 */
function findDisplayFormClose(text: string, openIdx: number): number {
  let depth = 0;
  let i = openIdx;
  while (i < text.length) {
    if (depth === 1 && isUnescapedCalcQuote(text, i)) {
      const lit = skipCalcLiteral(text, i);
      if (!lit.closed) {
        return text.indexOf('\n', i) === -1 ? endsInDisplayFormClose(text, i, text.length) : -1;
      }
      i = lit.end;
      continue;
    }
    const past = stepOverOpaque(text, i, LineCommentEnd.AtLineEnd);
    if (past !== i) { i = past; continue; }
    depth += hrBracketDepthDelta(text, i, depth);
    if (depth <= 0) return -1;
    i++;
  }
  return -1;
}

/** True when an unmatched block-comment opener lies outside every literal and comment of `content`. */
function hasUnterminatedCalcComment(content: string): boolean {
  let i = 0;
  while (i < content.length) {
    const past = stepOverOpaque(content, i, LineCommentEnd.AtLineEnd, ';');
    if (past !== i) { i = past; continue; }
    if (hrUnterminatedCalcCommentAt(content, i)) return true;
    i++;
  }
  return false;
}

/**
 * Split bracket content by semicolons, respecting:
 * - Text literals and comments (calc-literal.ts)
 * - Nested parentheses (for function calls)
 * - Nested brackets
 */
function splitParams(content: string): string[] {
  const params: string[] = [];
  let current = '';
  let parenDepth = 0;
  let bracketDepth = 0;

  for (let i = 0; i < content.length; i++) {
    // On the last line a `//` comment ends before the next `;` (the one-line
    // form FileMaker's Script Workspace shows, calc-literal.ts hrCalcCommentSpanAt).
    const span = hrCalcOpaqueSpanAt(content, i, ';');
    if (span) {
      current += content.slice(i, i + span);
      i += span - 1;
      continue;
    }
    const ch = content[i];

    // Every form FileMaker reads as a parenthesis or bracket counts:
    // `Left （ "abc" ; 2 ）` is one argument.
    if (isCalcOpenParen(ch)) parenDepth++;
    if (isCalcCloseParen(ch)) parenDepth--;
    if (isCalcOpenBracket(ch)) bracketDepth++;
    if (isCalcCloseBracket(ch)) bracketDepth--;

    if (ch === ';' && parenDepth === 0 && bracketDepth === 0) {
      params.push(current.trim());
      current = '';
      continue;
    }

    current += ch;
  }

  if (current.trim()) {
    params.push(current.trim());
  }

  return params;
}

/**
 * Extract a labeled parameter value.
 * e.g. extractLabel("Parameter: $id", "Parameter") => "$id"
 * e.g. extractLabel("With dialog: Off", "With dialog") => "Off"
 */
export function extractLabel(param: string, label: string): string | null {
  const prefix = label + ':';
  const idx = param.indexOf(prefix);
  if (idx < 0) return null;
  return param.substring(idx + prefix.length).trim();
}

/** Strip surrounding quotes from a string */
export function unquote(s: string): string {
  if (s.startsWith('"') && s.endsWith('"') && s.length >= 2) {
    return s.substring(1, s.length - 1);
  }
  return s;
}
