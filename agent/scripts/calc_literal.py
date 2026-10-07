"""calc_literal.py — the FileMaker calculation text-literal and comment grammar for the converters.

Every converter scanner that must step over (or decode) a text literal inside
calculation text uses these helpers: the human-readable step-line splitters (the
``[ … ]`` bracket finders and the ``;`` parameter splitter), the catalog emitter's
value splitters (``parametersList`` commas, ``attrGroup``/``repeatGroup`` bodies,
``fieldList`` entries) and the group-value quoting on both directions. The
TypeScript counterpart is ``webviewer/src/converter/calc-literal.ts``; keep the two
in step.

Grammar, measured against FileMaker Pro 26.0.2:

* ``"``, ``“`` (U+201C) and ``”`` (U+201D) are ONE interchangeable delimiter: a
  literal opens on any unescaped one and closes on any unescaped one (``"ab”``,
  ``”ab“`` and ``“ab"`` are all the literal ``ab``). FileMaker stores a pasted
  curly-delimited literal with straight quotes.
* Inside a literal a backslash escapes the next ``"``, ``“``, ``”``, ``\\`` or ``¶``
  (``"a\\"b"`` is ``a"b``, ``"a\\\\b"`` is ``a\\b``). Before any other character
  the backslash is ordinary content (``"a\\nb"`` is the four characters ``a\\nb``).
  FileMaker stores a doubled quote as the backslash form (``"a""b"`` comes back
  as ``"a\\"b"``).
* Inside a literal a delimiter immediately followed by another delimiter is the
  doubled escape: the second character is content (``"a""b"`` is ``a"b``).
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

The human-readable splitters use a narrower comment rule (``hr_calc_comment_span_at``),
because a step line mixes calculations with bare values such as file paths.
Stdlib only.
"""

from __future__ import annotations

CALC_QUOTES = frozenset('"“”')
# Characters a backslash escapes inside a literal.
_ESCAPABLE = frozenset('"“”\\¶')


def is_backslash_escaped(s: str, at: int) -> bool:
    """True when the character at ``at`` is preceded by an odd run of backslashes."""
    run = 0
    while at > 0 and s[at - 1] == "\\":
        run += 1
        at -= 1
    return run % 2 == 1


def is_unescaped_calc_quote(s: str, at: int) -> bool:
    """True when ``s[at]`` is a literal delimiter not preceded by an odd backslash run.

    In a toggle-style scanner every such character flips in/out of a literal, because
    the three delimiters pair freely (the doubled escape toggles twice).
    """
    return at < len(s) and s[at] in CALC_QUOTES and not is_backslash_escaped(s, at)


def is_calc_escape(s: str, at: int) -> bool:
    """True when the backslash at ``at`` (inside a literal) escapes the next character."""
    return s[at] == "\\" and at + 1 < len(s) and s[at + 1] in _ESCAPABLE


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
        if c == "\\" and is_calc_escape(s, i):
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
        if c in CALC_QUOTES:
            out.append("\\" + c)
        elif c == "\\" and (i == last or is_calc_escape(v, i)):
            out.append("\\\\")
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


def calc_comment_len(s: str, at: int) -> tuple[int, bool]:
    """Length of the calculation comment that opens at ``at`` and whether it closes.

    ``(0, False)`` when no ``/*`` or ``//`` starts there (the caller has established
    that ``at`` is outside a literal). A block comment runs past its matching ``*/``
    (block comments nest), or to the end of ``s`` when it has none (not closed). A
    line comment runs up to, not including, the next CR or LF (or to the end); it is
    always closed.
    """
    n = len(s)
    if at + 1 >= n or s[at] != "/":
        return 0, False
    if s[at + 1] == "/":
        i = at + 2
        while i < n and s[i] not in "\r\n":
            i += 1
        return i - at, True
    if s[at + 1] != "*":
        return 0, False
    depth = 1
    i = at + 2
    while i + 1 < n:
        if s[i] == "/" and s[i + 1] == "*":
            depth += 1
            i += 2
        elif s[i] == "*" and s[i + 1] == "/":
            i += 2
            depth -= 1
            if depth == 0:
                return i - at, True
        else:
            i += 1
    return n - at, False


# A comment opens in human-readable text only after one of these (or at the start).
_HR_COMMENT_MAY_FOLLOW = frozenset(' \t\r\n()[]{};,&+=<>^"“”')


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
    if at + 1 >= len(s) or s[at] != "/" or s[at + 1] not in "/*":
        return 0
    if not hr_calc_comment_may_open_after(s, at):
        return 0
    span, closed = calc_comment_len(s, at)
    if not closed:
        return 0
    if s[at + 1] == "/" and at + span == len(s) and stops:
        for j in range(at + 2, len(s)):
            if s[j] in stops:
                return j - at
    return span


def hr_unterminated_calc_comment_at(s: str, at: int) -> bool:
    """True when an unmatched ``/*`` (one ``hr_calc_comment_span_at`` declines only
    because it never closes) opens at ``at``."""
    if at + 1 >= len(s) or s[at] != "/" or s[at + 1] != "*":
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
            if token[i + 1] == "/" and i + c == n:
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
