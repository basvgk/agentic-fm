"""calc_literal.py — the FileMaker calculation text-literal and comment grammar for the converters.

Every converter scanner that must step over (or decode) a text literal inside
calculation text uses these helpers: the human-readable step-line splitters (the
``[ … ]`` bracket finders and the ``;`` parameter splitter), the catalog emitter's
value splitters (``parametersList`` commas, ``attrGroup``/``repeatGroup`` bodies,
``fieldList`` entries) and the group-value quoting on both directions. The
TypeScript counterpart is ``webviewer/src/converter/calc-literal.ts``; keep the two
in step.

Grammar, measured against FileMaker Pro 26.0.2 and 26.0.3:

* ``"``, ``“`` (U+201C), ``”`` (U+201D), ``„`` (U+201E), ``‟`` (U+201F) and ``＂``
  (U+FF02) are ONE interchangeable delimiter (``CALC_QUOTES``): a literal opens on
  any unescaped one and closes on any unescaped one (``"ab”``, ``”ab“``, ``„ab„``
  and ``＂ab"`` are all the literal ``ab``; all 36 open/close pairs behave alike).
  No other character delimits (``‚ ‘ ’ « » 「 」 〝 〞 〟 ＇`` are errors). FileMaker
  stores a pasted literal with straight quotes (``„y, z„`` comes back as
  ``"y, z"``).
* Inside a literal a backslash escapes the next delimiter, backslash or ``¶``
  (``"a\\"b"`` is ``a"b``, ``"a\\„b"`` is ``a„b``, ``"a\\\\b"`` is ``a\\b``).
  Before any other character the backslash is ordinary content (``"a\\nb"`` is
  the four characters ``a\\nb``). ``＼`` (U+FF3C) and ``﹨`` (U+FE68) are
  backslashes too (``CALC_BACKSLASHES``): ``"a＼"b"`` is ``a"b``, ``"a＼＼b"`` and
  ``"a\\＼b"`` are ``a＼b``, ``"a＼¶b"`` is ``a¶b``. FileMaker stores a doubled
  quote as the backslash form (``"a""b"`` comes back as ``"a\\"b"``).
* Inside a literal a delimiter immediately followed by another delimiter is the
  doubled escape: the second character is content (``"a""b"`` is ``a"b``,
  ``"a"＂b"`` is ``a＂b``).
* ``'``, ``‘`` and ``’`` are never calculation delimiters.

A delimiter preceded by an odd backslash run outside a literal does not open one.

Calculation comments, measured against FileMaker Pro 26.0.2:

* ``/*`` opens a block comment that runs to its MATCHING ``*/``: block comments nest
  (``1 /* a /* b */ c */ + 2`` is 3, ``1 /* a */ */ + 2`` is error 1204). An
  unmatched ``/*`` is error 1205.
* ``//`` opens a line comment that runs to the next return (FileMaker stores a
  return in a calculation as CR; human-readable text carries it as LF; a pasted LF
  is stored as CR).
* Inside a comment nothing is structure: a quote opens no literal
  (``1 /* "*/" */ + 2`` is error 1206), ``//`` inside a block comment and ``/*``
  inside a line comment are plain text.
* A comment opens only outside a literal (``"a /* b"`` is the text ``a /* b``).
* ``/`` and ``*`` each have three compatibility forms that work in every one of
  those positions (``CALC_SLASHES``, ``CALC_STARS``): ``1 ／＊ c ; d ＊／ + 2`` is 3.

The human-readable splitters use a narrower comment rule (``hr_calc_comment_span_at``),
because a step line mixes calculations with bare values such as file paths. Their
parenthesis and bracket depth reads every form FileMaker reads as one
(``CALC_OPEN_PARENS`` and its siblings, ``hr_bracket_depth_delta``, below).
Stdlib only.
"""

from __future__ import annotations

CALC_QUOTES = frozenset('"\u201c\u201d\u201e\u201f\uff02')
CALC_BACKSLASHES = frozenset("\\\uff3c\ufe68")
# Characters a backslash escapes inside a literal.
_ESCAPABLE = CALC_QUOTES | CALC_BACKSLASHES | {"¶"}


def is_backslash_escaped(s: str, at: int) -> bool:
    """True when the character at ``at`` is preceded by an odd run of backslashes
    (any mix of the ``CALC_BACKSLASHES`` forms)."""
    run = 0
    while at > 0 and s[at - 1] in CALC_BACKSLASHES:
        run += 1
        at -= 1
    return run % 2 == 1


def is_unescaped_calc_quote(s: str, at: int) -> bool:
    """True when ``s[at]`` is a literal delimiter not preceded by an odd backslash run.

    In a toggle-style scanner every such character flips in/out of a literal, because
    the six delimiters pair freely (the doubled escape toggles twice).
    """
    return at < len(s) and s[at] in CALC_QUOTES and not is_backslash_escaped(s, at)


def is_calc_escape(s: str, at: int) -> bool:
    """True when the backslash (any ``CALC_BACKSLASHES`` form) at ``at`` (inside a
    literal) escapes the next character."""
    return s[at] in CALC_BACKSLASHES and at + 1 < len(s) and s[at + 1] in _ESCAPABLE


def skip_calc_literal(s: str, at: int) -> tuple[int, bool, str]:
    """Scan the literal whose opening delimiter is ``s[at]``.

    Returns ``(end, closed, decoded)``: the offset just past the closing delimiter
    (``len(s)`` when unterminated, ``closed`` False) and the literal's value with
    escapes and doubled delimiters resolved and the enclosing delimiters dropped.
    """
    n = len(s)
    out: list[str] = []
    i = at + 1
    while i < n:
        c = s[i]
        if c in CALC_BACKSLASHES and is_calc_escape(s, i):
            out.append(s[i + 1])
            i += 2
            continue
        if c in CALC_QUOTES:
            if i + 1 < n and s[i + 1] in CALC_QUOTES:
                out.append(s[i + 1])
                i += 2
                continue
            return i + 1, True, "".join(out)
        out.append(c)
        i += 1
    return n, False, "".join(out)


def calc_literal_span_at(s: str, at: int) -> int:
    """Length of the text literal that opens at ``at`` (0 when none opens there).

    An unterminated literal runs to the end of ``s``.
    """
    if not is_unescaped_calc_quote(s, at):
        return 0
    return skip_calc_literal(s, at)[0] - at


def quote_calc_literal(v: str, open_q: str = "“", close_q: str = "”") -> str:
    """Write ``v`` as ONE text literal between ``open_q`` and ``close_q`` that
    ``skip_calc_literal`` decodes back to exactly ``v``.

    Every embedded delimiter is backslash-escaped, and a backslash is escaped only
    when it would otherwise escape what follows it (the next character is
    escapable, or it is last and would escape the closing delimiter). Everything
    else is written verbatim, so a value with no delimiter and no such backslash
    reads exactly as FileMaker displays a quoted literal text parameter (``“x”``,
    ``“a\\b”``; FileMaker itself never escapes the value it displays).
    """
    out = [open_q]
    last = len(v) - 1
    for i, c in enumerate(v):
        if c in CALC_QUOTES or (c in CALC_BACKSLASHES and (i == last or is_calc_escape(v, i))):
            out.append("\\" + c)
        else:
            out.append(c)
    out.append(close_q)
    return "".join(out)


def decode_whole_calc_literal(s: str) -> str | None:
    """The decoded value when ``s`` is exactly one closed text literal (its first
    character opens it and its closing delimiter is its last character); ``None``
    for anything else (bare text, two literals, an unterminated one, trailing text).
    """
    if not s or s[0] not in CALC_QUOTES:
        return None
    end, closed, decoded = skip_calc_literal(s, 0)
    return decoded if closed and end == len(s) else None


# --- calculation comments ----------------------------------------------------


# FileMaker reads ``⁄`` (U+2044), ``∕`` (U+2215) and ``／`` (U+FF0F) as ``/`` and ``∗``
# (U+2217), ``﹡`` (U+FE61) and ``＊`` (U+FF0A) as ``*`` in every comment position
# (measured against FileMaker Pro 26.0.2 and 26.0.3): any slash then any star opens a
# block comment (``1 ／＊ c ; d ＊／ + 2`` is 3), any star then any slash closes one,
# the forms nest together, and any two slashes open a line comment. A paste stores
# the outer delimiters as ASCII. Outside a comment they are the division and
# multiplication operators (``6 ／ 3`` is 2).
CALC_SLASHES = frozenset("/\u2044\u2215\uff0f")
CALC_STARS = frozenset("*\u2217\ufe61\uff0a")


def calc_line_comment_open_len(s: str, at: int) -> int:
    """Length (2) of a line-comment opener (two slash forms) at *at*, 0 when none."""
    first, second = s[at : at + 1], s[at + 1 : at + 2]
    return 2 if first in CALC_SLASHES and second in CALC_SLASHES else 0


def calc_block_comment_open_len(s: str, at: int) -> int:
    """Length (2) of a block-comment opener (a slash form, then a star form) at
    *at*, 0 when none."""
    first, second = s[at : at + 1], s[at + 1 : at + 2]
    return 2 if first in CALC_SLASHES and second in CALC_STARS else 0


def calc_comment_len(s: str, at: int) -> tuple[int, bool]:
    """Length of the calculation comment that opens at ``at`` and whether it closes.

    ``(0, False)`` when no ``/*`` or ``//``, in any of their forms, starts there (the
    caller has established that ``at`` is outside a literal). A block comment runs
    past its matching ``*/`` (block comments nest), or to the end of ``s`` when it
    has none (not closed). A line comment runs up to, not including, the next CR or
    LF (or to the end); it is always closed.
    """
    n = len(s)
    if calc_line_comment_open_len(s, at):
        i = at + 2
        while i < n and s[i] not in "\r\n":
            i += 1
        return i - at, True
    if not calc_block_comment_open_len(s, at):
        return 0, False
    depth = 1
    i = at + 2
    while i + 1 < n:
        if s[i] in CALC_SLASHES and s[i + 1] in CALC_STARS:
            depth += 1
            i += 2
        elif s[i] in CALC_STARS and s[i + 1] in CALC_SLASHES:
            i += 2
            depth -= 1
            if depth == 0:
                return i - at, True
        else:
            i += 1
    return n - at, False


# A comment opens in human-readable text only after one of these (or at the start).
_HR_COMMENT_MAY_FOLLOW = frozenset(
    ' \t\r\n\v\f()[]{};,&+=<>^"“”„‟＂'
    # The other forms FileMaker reads as whitespace, a parenthesis, a bracket, an
    # argument separator or ``&`` (``1　／＊ c ＊／`` after U+3000 opens).
    "\u0085\u00a0\u1680\u180e"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u200b"
    "\u2028\u2029\u202f\u205f\u2060\u3000\ufeff"
    "\ufe59\uff08\ufe5a\uff09\uff3b\uff3d"
    "\u060c\u061b\u3001\ufe50\ufe51\ufe54\uff0c\uff1b\uff64"
    "\ufe60\uff06"
)


def hr_calc_comment_may_open_after(s: str, at: int) -> bool:
    """True when a comment opener at ``at`` is not glued to a word or path character.

    Human-readable step text mixes calculations with bare non-calculation values (a
    file path ``filewin://srv/a.csv``, ``file:a//b``, a Flow URL), and a splitter
    cannot tell which a value is before it has split the line. So a comment opens
    only where a calculation token can end: at the start of the text, after
    whitespace, after a literal delimiter, or after one of ``( ) [ ] { } ; , & + = <
    > ^`` -- never glued to a preceding word or path character (``$y//note``, which
    FileMaker accepts, is then read as plain text, exactly as before comments were
    recognised).
    """
    return at == 0 or s[at - 1] in _HR_COMMENT_MAY_FOLLOW


def hr_calc_comment_span_at(s: str, at: int, stops: str = "") -> int:
    """Length of the comment a human-readable splitter steps over at ``at`` (0 if none).

    ``calc_comment_len`` under the human-readable rule: the opener must not be glued
    to a word character, and a block comment with no matching ``*/`` in ``s`` is not
    a comment (FileMaker rejects it, and reading it as one would swallow the rest of
    the step; ``hr_unterminated_calc_comment_at`` reports it).

    ``stops`` handles the one-line form. FileMaker's Script Workspace draws a
    calculation's returns as spaces, so its line for a step reads
    ``Height: 400 // Pixels ; Width: 600 // Pixels ; … ]``, and that is also how an
    author writes it: on the LAST line of ``s`` (no CR or LF follows the comment) a
    ``//`` comment ends before the first character of ``stops`` -- the separator the
    caller splits on (``;`` for step parameters, ``,`` for a list, ``|`` for repeated
    entries). A comment followed by a line break runs to that break, whatever it
    holds. XML->HR writes a line break after a comment whose text holds such a
    character (``hr_needs_line_break_after``), so its own output never depends on it.
    """
    line = calc_line_comment_open_len(s, at)
    if not line and not calc_block_comment_open_len(s, at):
        return 0
    if not hr_calc_comment_may_open_after(s, at):
        return 0
    span, closed = calc_comment_len(s, at)
    if not closed:
        return 0
    if line and at + span == len(s) and stops:
        for j in range(at + line, len(s)):
            if s[j] in stops:
                return j - at
    return span


def hr_unterminated_calc_comment_at(s: str, at: int) -> bool:
    """True when an unmatched ``/*`` (one ``hr_calc_comment_span_at`` declines only
    because it never closes) opens at ``at``."""
    if calc_line_comment_open_len(s, at) or not calc_block_comment_open_len(s, at):
        return False
    if not hr_calc_comment_may_open_after(s, at):
        return False
    return not calc_comment_len(s, at)[1]


def hr_calc_opaque_span_at(s: str, at: int, stops: str = "") -> int:
    """Length of the opaque span a human-readable splitter steps over whole at ``at``:
    a text literal (an unterminated one runs to the end) or a comment
    (``hr_calc_comment_span_at``). 0 when neither opens there. A separator, bracket or
    quote inside the span is content, not structure."""
    lit = calc_literal_span_at(s, at)
    if lit:
        return lit
    return hr_calc_comment_span_at(s, at, stops)


def hr_needs_line_break_after(token: str, sep: str) -> bool:
    """True when XML->HR must break the line after ``token`` and token the separator
    ``sep`` that follows it (`` ; ``, ``, ``, `` | ``, or the step's closing `` ]``):
    ``token`` ends inside a ``//`` line comment whose text holds ``;``, ``]`` or the
    separator's own character, which the one-line reading of
    ``hr_calc_comment_span_at`` would take as structure. Any other trailing comment
    (``Height: 400 // Pixels ; …``) stays on FileMaker's one line.
    """
    i = 0
    n = len(token)
    while i < n:
        lit = calc_literal_span_at(token, i)
        if lit:
            i += lit
            continue
        c = hr_calc_comment_span_at(token, i)
        if c:
            if calc_line_comment_open_len(token, i) and i + c == n:
                text = token[i + 2 :]
                own = sep.strip(" ")[:1] or "]"
                return any(ch in text for ch in ";]") or own in text
            i += c
            continue
        i += 1
    return False


def hr_sep(token: str, sep: str) -> str:
    """The separator XML->HR writes after the HR token ``token``: ``sep`` as is, or a line break
    followed by ``sep`` without its leading space when ``token`` ends in a ``//``
    comment the one-line reading would cut (``hr_needs_line_break_after``)."""
    if not hr_needs_line_break_after(token, sep):
        return sep
    return "\n" + sep.lstrip(" ")


# FileMaker reads ``﹙`` and ``（`` as ``(``, ``﹚`` and ``）`` as ``)``, ``［`` as ``[``
# and ``］`` as ``]`` in a calculation, pairing them freely with the ASCII forms
# (``Left （ "abc" ; 2 ）`` is ``ab``, ``Let ( ［ a = 1 ; b = 2 ] ; a + b )`` is 3;
# measured against FileMaker Pro 26.0.2 and 26.0.3). A paste stores them as ASCII.
# Inside a literal they are ordinary text.
CALC_OPEN_PARENS = frozenset("(\ufe59\uff08")
CALC_CLOSE_PARENS = frozenset(")\ufe5a\uff09")
CALC_OPEN_BRACKETS = frozenset("[\uff3b")
CALC_CLOSE_BRACKETS = frozenset("]\uff3d")


def hr_bracket_depth_delta(s: str, at: int, depth: int) -> int:
    """Depth change (+1, -1 or 0) for the bracket at *at* in a step-line scan that
    tracks a step's own ``[ ]`` (or a field subscript's) with the calculation inside,
    *depth* brackets being open before *at*. The outer brackets are human-readable
    syntax and ASCII only; inside them the calculation's brackets count in every
    form, so ``［`` opens only once a bracket is open and ``］`` closes only a
    bracket nested inside the outer one: a stray ``］`` never closes the step."""
    ch = s[at]
    if ch == "[":
        return 1
    if ch == "]":
        return -1
    if depth > 0 and ch in CALC_OPEN_BRACKETS:
        return 1
    if depth > 1 and ch in CALC_CLOSE_BRACKETS:
        return -1
    return 0


# --- quoted literal text versus calculation ----------------------------------

# Whitespace FileMaker accepts between calculation tokens (TAB, LF, VT, FF, CR,
# SPACE, U+00A0, U+1680, U+180E, U+2000-U+200B, U+205F, U+3000).
_CALC_SPACES = frozenset(
    "\t\n\x0b\x0c\r   ᠎ 　" + "".join(chr(c) for c in range(0x2000, 0x200C))
)
# Argument separators FileMaker reads as ``;`` and the ``&`` forms.
_CALC_SEPARATORS = frozenset(";,،؛、﹐﹑﹔，；､")
_CALC_JOIN_OPERATORS = frozenset("&﹠＆+-*/^=<>≠≤≥")
_CALC_WORD_OPERATORS_AFTER = ("and", "or", "xor")
_CALC_WORD_OPERATORS_BEFORE = ("and", "or", "xor", "not")


def _calc_word_at(s: str, at: int, w: str) -> bool:
    if s[at : at + len(w)].lower() != w:
        return False
    before = s[at - 1] if at > 0 else ""
    after = s[at + len(w)] if at + len(w) < len(s) else ""
    return not (before.isascii() and before.isalpha()) and not (after.isascii() and after.isalpha())


def _calc_gap_joins_operands(gap: str, depth: int) -> tuple[bool, int]:
    """Whether ``gap`` (the text between two literals) joins them as calculation
    operands, and the parenthesis/bracket depth after it. See
    ``reads_as_quoted_literal_text``."""
    before = depth
    for c in gap:
        if c in CALC_OPEN_PARENS or c in CALC_OPEN_BRACKETS:
            depth += 1
        elif c in CALC_CLOSE_PARENS or c in CALC_CLOSE_BRACKETS:
            depth -= 1
    a = 0
    while a < len(gap) and gap[a] in _CALC_SPACES:
        a += 1
    z = len(gap)
    while z > a and gap[z - 1] in _CALC_SPACES:
        z -= 1
    if a >= z:
        return False, depth
    first, last = gap[a], gap[z - 1]
    start_ok = (
        first in _CALC_JOIN_OPERATORS
        or first in CALC_CLOSE_PARENS
        or first in CALC_CLOSE_BRACKETS
        or (before > 0 and first in _CALC_SEPARATORS)
        or any(_calc_word_at(gap, a, w) for w in _CALC_WORD_OPERATORS_AFTER)
    )
    if not start_ok:
        return False, depth
    end_ok = (
        last in _CALC_JOIN_OPERATORS
        or last in CALC_OPEN_PARENS
        or last in CALC_OPEN_BRACKETS
        or last in _CALC_SEPARATORS
        or any(z - a >= len(w) and _calc_word_at(gap, z - len(w), w) for w in _CALC_WORD_OPERATORS_BEFORE)
    )
    return end_ok, depth


def reads_as_quoted_literal_text(t: str) -> bool:
    """Whether ``t`` (one trimmed HR token) reads as quoted literal text rather
    than a calculation.

    FileMaker displays a literal text parameter between quotes and never escapes
    it: Perform AppleScript's text ``a "b";c] d`` shows as ``"a "b";c] d"``, while
    a calculation shows as written (``"say " & $x``). True for one whole literal
    and for FileMaker's display form: a token that opens with a delimiter and whose
    literals are not joined as calculation operands (plain text between two
    literals, or a literal that never closes). False for anything that does not
    open with a delimiter, ends in calculation text, or joins every literal with an
    operator. Displayed text whose quotes happen to spell a valid calculation
    (``x" & "y`` shows as ``"x" & "y"``) cannot be told apart and reads as the
    calculation.
    """
    if not t or t[0] not in CALC_QUOTES:
        return False
    depth = 0
    joined = False
    i = 0
    while True:
        past, closed, _ = skip_calc_literal(t, i)
        if not closed:
            return True
        if past >= len(t):
            return not joined
        j = past
        while j < len(t) and t[j] not in CALC_QUOTES:
            j += 1
        if j >= len(t):
            return False
        ok, depth = _calc_gap_joins_operands(t[past:j], depth)
        if not ok:
            return True
        joined = True
        i = j
