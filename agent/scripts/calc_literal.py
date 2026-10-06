"""calc_literal.py — the FileMaker calculation text-literal grammar for the converters.

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
