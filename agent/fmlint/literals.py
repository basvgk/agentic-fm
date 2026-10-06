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
