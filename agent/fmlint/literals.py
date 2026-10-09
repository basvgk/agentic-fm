"""String-literal grammar for FileMaker calculation text.

Lint rules that scan calculations for tokens (function calls, parentheses,
operators, entities, variable names) must ignore anything inside a text
literal.  A plain ``"[^"]*"`` regex is not enough, because FileMaker's literal
grammar has three features that regex misses (measured against FileMaker Pro
26.0.2):

* A backslash escapes the next quote: ``"a\\"b"`` is the three characters
  ``a"b``, and ``"a\\\\b"`` is ``a\\b``.  A quote preceded by an odd run of
  backslashes is content, not a delimiter.  The doubled form ``"a""b"`` also
  yields ``a"b``; masking it as two adjacent literals is equivalent.
* The curly double quotes are delimiters too, and they are interchangeable
  with the straight quote: ``“Total (net)”``, ``”ab“``, ``"ab”`` and
  ``“ab"`` each evaluate to a literal, and ``"x“ & Upper ( "y" ) & ”z"`` is
  ``"x" & Upper ( "y" ) & "z"``.  A backslash escapes a curly quote as well
  (``“a\\”b”`` is ``a”b``).
* Curly single quotes are not calculation delimiters (``‘ab’`` is an error),
  but human-readable script text uses ``‘…’`` to wrap opaque text parameters,
  so a ``‘`` outside any literal is treated as opening a region that runs to
  the next ``’``.  Inside a double-quoted literal both are ordinary content.

``mask_string_literals`` keeps each literal's delimiters and drops its
interior, so callers' regexes see ``""`` (or ``“”``) where a literal was.

The human-readable step-line splitters (``formats/hr_parser.py``) also step over
calculation comments with ``hr_opaque_span_at``: outside a literal ``/* … */``
(block comments nest) and ``// …`` (to the end of the line) are comments, in every
slash/star form FileMaker reads (``／＊ … ＊／``, ``⁄∗``, ``／／``), measured against
FileMaker Pro 26.0.2. Because a step line mixes calculations with bare
values such as file paths, a comment opens there only where a calculation token can
end (``hr_comment_may_open_after``), and an unmatched ``/*`` is plain text. Their
parenthesis and bracket depth reads every form FileMaker reads as one
(``CALC_OPEN_PARENS`` and its siblings, ``hr_bracket_depth_delta``). The
converters' copy of this grammar is ``agent/scripts/calc_literal.py``.
"""

_DOUBLE_DELIMS = frozenset('"“”')  # "  “  ”
_SINGLE_OPEN = "‘"   # ‘
_SINGLE_CLOSE = "’"  # ’

_NONE, _DOUBLE, _SINGLE = 0, 1, 2


def _is_escaped(text, idx):
    """True when the character at *idx* is preceded by an odd run of backslashes."""
    run = 0
    while idx > 0 and text[idx - 1] == "\\":
        run += 1
        idx -= 1
    return run % 2 == 1


def is_double_delimiter(text, idx):
    """True when ``text[idx]`` is an unescaped ``"``, ``“`` or ``”``.

    The three pair freely, so in a toggle-style scanner every such character flips
    in or out of a double-quoted literal (a doubled ``""`` toggles twice).
    """
    return text[idx] in _DOUBLE_DELIMS and not _is_escaped(text, idx)


def _scan(text):
    """Return (masked_text, final_state) for *text*."""
    out = []
    state = _NONE
    for i, ch in enumerate(text):
        if state == _DOUBLE:
            if ch in _DOUBLE_DELIMS and not _is_escaped(text, i):
                out.append(ch)
                state = _NONE
            continue
        if state == _SINGLE:
            if ch == _SINGLE_CLOSE:
                out.append(ch)
                state = _NONE
            continue
        if ch in _DOUBLE_DELIMS and not _is_escaped(text, i):
            out.append(ch)
            state = _DOUBLE
            continue
        if ch == _SINGLE_OPEN:
            out.append(ch)
            state = _SINGLE
            continue
        out.append(ch)
    return "".join(out), state


def mask_string_literals(text):
    """Drop the interior of every text literal in *text*, keeping its delimiters."""
    return _scan(text)[0]


def has_unclosed_literal(text):
    """True when *text* ends inside a text literal."""
    return _scan(text)[1] != _NONE


def literal_span_at(text, idx):
    """Length of the double-quoted literal that opens at *idx* (0 when none does).

    The literal closes at the next unescaped delimiter (a doubled ``""`` is two
    adjacent literals, which masks and splits the same); an unterminated one runs
    to the end of *text*.
    """
    if not is_double_delimiter(text, idx):
        return 0
    j = idx + 1
    while j < len(text):
        if is_double_delimiter(text, j):
            return j + 1 - idx
        j += 1
    return len(text) - idx


# FileMaker reads ``⁄`` (U+2044), ``∕`` (U+2215) and ``／`` (U+FF0F) as ``/`` and ``∗``
# (U+2217), ``﹡`` (U+FE61) and ``＊`` (U+FF0A) as ``*`` in every comment position
# (measured against FileMaker Pro 26.0.2 and 26.0.3): any slash then any star opens a
# block comment (``1 ／＊ c ; d ＊／ + 2`` is 3), any star then any slash closes one,
# the forms nest together, and any two slashes open a line comment. A paste stores
# the outer delimiters as ASCII. Outside a comment they are the division and
# multiplication operators (``6 ／ 3`` is 2).
CALC_SLASHES = frozenset("/\u2044\u2215\uff0f")
CALC_STARS = frozenset("*\u2217\ufe61\uff0a")


def line_comment_open_len(text, idx):
    """Length (2) of a line-comment opener (two slash forms) at *idx*, 0 when none."""
    first, second = text[idx : idx + 1], text[idx + 1 : idx + 2]
    return 2 if first in CALC_SLASHES and second in CALC_SLASHES else 0


def block_comment_open_len(text, idx):
    """Length (2) of a block-comment opener (a slash form, then a star form) at
    *idx*, 0 when none."""
    first, second = text[idx : idx + 1], text[idx + 1 : idx + 2]
    return 2 if first in CALC_SLASHES and second in CALC_STARS else 0


def comment_len(text, idx):
    """``(length, closed)`` of the calculation comment that opens at *idx*.

    ``(0, False)`` when no ``/*`` or ``//``, in any of their forms, starts there. A
    block comment runs past its matching ``*/`` (block comments nest) or to the end
    (not closed); a line comment runs up to, not including, the next CR or LF and is
    always closed.
    """
    n = len(text)
    if line_comment_open_len(text, idx):
        j = idx + 2
        while j < n and text[j] not in "\r\n":
            j += 1
        return j - idx, True
    if not block_comment_open_len(text, idx):
        return 0, False
    depth = 1
    j = idx + 2
    while j + 1 < n:
        if text[j] in CALC_SLASHES and text[j + 1] in CALC_STARS:
            depth += 1
            j += 2
        elif text[j] in CALC_STARS and text[j + 1] in CALC_SLASHES:
            j += 2
            depth -= 1
            if depth == 0:
                return j - idx, True
        else:
            j += 1
    return n - idx, False


_COMMENT_MAY_FOLLOW = frozenset(
    ' \t\r\n\v\f()[]{};,&+=<>^"“”'
    # The other forms FileMaker reads as whitespace, a parenthesis, a bracket, an
    # argument separator or ``&`` (``1　／＊ c ＊／`` after U+3000 opens).
    "\u0085\u00a0\u1680\u180e"
    "\u2000\u2001\u2002\u2003\u2004\u2005\u2006\u2007\u2008\u2009\u200a\u200b"
    "\u2028\u2029\u202f\u205f\u2060\u3000\ufeff"
    "\ufe59\uff08\ufe5a\uff09\uff3b\uff3d"
    "\u060c\u061b\u3001\ufe50\ufe51\ufe54\uff0c\uff1b\uff64"
    "\ufe60\uff06"
)


def hr_comment_may_open_after(text, idx):
    """True when a comment opener at *idx* is not glued to a word or path character
    (``filewin://srv``, ``file:a//b`` and ``$y//note`` stay plain text)."""
    return idx == 0 or text[idx - 1] in _COMMENT_MAY_FOLLOW


def hr_comment_span_at(text, idx, stops=""):
    """Length of the comment a step-line splitter steps over at *idx* (0 if none):
    the opener must not be glued to a word character, and an unmatched ``/*`` is not
    a comment (FileMaker rejects it; reading it as one would swallow the step).

    On the last line of *text* (no line break follows) a ``//`` comment ends before
    the first character of *stops*, the caller's separator: FileMaker's Script
    Workspace draws a calculation's returns as spaces, so its one-line form reads
    ``Height: 400 // Pixels ; Width: 600 // Pixels``.
    """
    line = line_comment_open_len(text, idx)
    if not line and not block_comment_open_len(text, idx):
        return 0
    if not hr_comment_may_open_after(text, idx):
        return 0
    span, closed = comment_len(text, idx)
    if not closed:
        return 0
    if line and idx + span == len(text) and stops:
        for j in range(idx + line, len(text)):
            if text[j] in stops:
                return j - idx
    return span


def hr_opaque_span_at(text, idx, stops=""):
    """Length of the literal or comment a step-line splitter steps over whole at *idx*."""
    return literal_span_at(text, idx) or hr_comment_span_at(text, idx, stops)


# FileMaker reads ``﹙`` and ``（`` as ``(``, ``﹚`` and ``）`` as ``)``, ``［`` as ``[``
# and ``］`` as ``]`` in a calculation, pairing them freely with the ASCII forms
# (``Left （ "abc" ; 2 ）`` is ``ab``, ``Let ( ［ a = 1 ; b = 2 ] ; a + b )`` is 3;
# measured against FileMaker Pro 26.0.2 and 26.0.3). A paste stores them as ASCII.
# Inside a literal they are ordinary text.
CALC_OPEN_PARENS = frozenset("(\ufe59\uff08")
CALC_CLOSE_PARENS = frozenset(")\ufe5a\uff09")
CALC_OPEN_BRACKETS = frozenset("[\uff3b")
CALC_CLOSE_BRACKETS = frozenset("]\uff3d")


def hr_bracket_depth_delta(text, idx, depth):
    """Depth change (+1, -1 or 0) for the bracket at *idx* in a step-line scan that
    tracks a step's own ``[ ]`` (or a field subscript's) with the calculation inside,
    *depth* brackets being open before *idx*. The outer brackets are human-readable
    syntax and ASCII only; inside them the calculation's brackets count in every
    form, so ``［`` opens only once a bracket is open and ``］`` closes only a
    bracket nested inside the outer one: a stray ``］`` never closes the step."""
    ch = text[idx]
    if ch == "[":
        return 1
    if ch == "]":
        return -1
    if depth > 0 and ch in CALC_OPEN_BRACKETS:
        return 1
    if depth > 1 and ch in CALC_CLOSE_BRACKETS:
        return -1
    return 0
