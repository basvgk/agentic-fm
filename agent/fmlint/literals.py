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
(block comments nest) and ``// …`` (to the end of the line) are comments, measured
against FileMaker Pro 26.0.2. Because a step line mixes calculations with bare
values such as file paths, a comment opens there only where a calculation token can
end (``hr_comment_may_open_after``), and an unmatched ``/*`` is plain text. The
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


def comment_len(text, idx):
    """``(length, closed)`` of the calculation comment that opens at *idx*.

    ``(0, False)`` when no ``/*`` or ``//`` starts there. A block comment runs past
    its matching ``*/`` (block comments nest) or to the end (not closed); a line
    comment runs up to, not including, the next CR or LF and is always closed.
    """
    n = len(text)
    if idx + 1 >= n or text[idx] != "/":
        return 0, False
    if text[idx + 1] == "/":
        j = idx + 2
        while j < n and text[j] not in "\r\n":
            j += 1
        return j - idx, True
    if text[idx + 1] != "*":
        return 0, False
    depth = 1
    j = idx + 2
    while j + 1 < n:
        if text[j] == "/" and text[j + 1] == "*":
            depth += 1
            j += 2
        elif text[j] == "*" and text[j + 1] == "/":
            j += 2
            depth -= 1
            if depth == 0:
                return j - idx, True
        else:
            j += 1
    return n - idx, False


_COMMENT_MAY_FOLLOW = frozenset(' \t\r\n()[]{};,&+=<>^"“”')


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
    if idx + 1 >= len(text) or text[idx] != "/" or text[idx + 1] not in "/*":
        return 0
    if not hr_comment_may_open_after(text, idx):
        return 0
    span, closed = comment_len(text, idx)
    if not closed:
        return 0
    if text[idx + 1] == "/" and idx + span == len(text) and stops:
        for j in range(idx + 2, len(text)):
            if text[j] in stops:
                return j - idx
    return span


def hr_opaque_span_at(text, idx, stops=""):
    """Length of the literal or comment a step-line splitter steps over whole at *idx*."""
    return literal_span_at(text, idx) or hr_comment_span_at(text, idx, stops)
