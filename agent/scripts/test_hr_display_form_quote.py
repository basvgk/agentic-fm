#!/usr/bin/env python3
"""test_hr_display_form_quote.py — a human-readable line in FileMaker's display
form with an odd number of quotes ends at its own ``]``.

FileMaker draws a literal text parameter as ``“`` + value + ``”`` and never escapes
the value (measured against FileMaker Pro 26.0.3), so the value ``He said “hi``
shows as ``Insert Text [ Select ; Target: $x ; “He said “hi” ]``: three
delimiters. Read with the calculation literal grammar, the last one opened a
literal that swallowed the step's ``]``, and the multi-line merge folded every
following line into the step's text (one more odd line closed it again). A literal
that opens at the step's own bracket level, does not close on its line, and whose
line ends with a delimiter and ``]`` is FileMaker's closing quote and the step's
``]``: the statement ends there, flagged ``display_form_quote``. Mirrors the
webviewer ``hr-display-form-quote.test.ts``. Runs under pytest, or standalone.
"""

from __future__ import annotations

import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (HERE, REPO_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from catalog_emit import EmptyResolver, convert_step_with_catalog, match_param_values
from catalog_grammar import load_catalog

from agent.fmlint.formats.hr_parser import parse_hr

_CATALOG = {
    e.name: e
    for e in load_catalog(os.path.join(REPO_ROOT, "agent", "catalogs", "step-catalog-en.json"))
}


def _texts(hr: str) -> list:
    out = []
    for pl in parse_hr(hr):
        if pl.step_name != "Insert Text":
            continue
        entry = _CATALOG[pl.step_name]
        xml = convert_step_with_catalog(entry, pl.disabled, match_param_values(entry, pl.params), EmptyResolver())
        out += re.findall(r"<Text>(.*?)</Text>", xml, re.DOTALL)
    return out


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def test_odd_quote_line_does_not_swallow_the_steps_after_it():
    lines = parse_hr("Insert Text [ Select ; Target: $x ; “He said “hi” ]\nBeep\nSet Variable [ $y ; Value: 1 ]")
    assert [pl.step_name for pl in lines] == ["Insert Text", "Beep", "Set Variable"]
    assert [pl.display_form_quote for pl in lines] == [True, False, False]
    assert _texts("Insert Text [ Select ; Target: $x ; “He said “hi” ]\nBeep") == ["He said “hi"]


def test_two_odd_lines_stay_two_steps():
    hr = "Insert Text [ Select ; Target: $x ; “He said “hi” ]\nBeep\nInsert Text [ Select ; Target: $z ; “a “b” ]\nBeep"
    lines = parse_hr(hr)
    assert [pl.step_name for pl in lines] == ["Insert Text", "Beep", "Insert Text", "Beep"]
    assert [pl.line_number for pl in lines if pl.display_form_quote] == [1, 3]
    assert _texts(hr) == ["He said “hi", "a “b"]


def test_single_line_shapes():
    cases = [
        ("Insert Text [ Select ; Target: $x ; “He said “hi” ]", "He said “hi"),
        ('Insert Text [ Select ; Target: $x ; “a"” ]', 'a"'),
        ("Insert Text [ Select ; Target: $x ; “a\\” ]", "a\\"),
        ('Insert Text [ Select ; Target: $x ; “x;y"z” ]', 'x;y"z'),
        ('Insert Text [ Select ; Target: $x ; “a [b] "c”   ]  ', 'a [b] "c'),
        ('Insert Text [ Select ; Target: $x ; "He said "hi" ]', 'He said "hi'),
    ]
    for line, text in cases:
        lines = parse_hr(line + "\nBeep")
        assert [pl.step_name for pl in lines] == ["Insert Text", "Beep"], line
        assert lines[0].display_form_quote, line
        assert len(lines[0].params) == 3, line
        assert _texts(line) == [_esc(text)], line


def test_balanced_lines_and_multi_line_calcs_unchanged():
    for line in (
        "Insert Text [ Select ; Target: $x ; “He said “hi”” ]",
        "Insert Text [ Select ; Target: $x ; “He said \\“hi” ]",
        'Set Variable [ $x ; Value: "a" ]',
    ):
        assert not parse_hr(line)[0].display_form_quote, line
    for calc in ('"a\nb"', '"Items [1]\nnext"', '"x ]\ny"', 'Let ( [\n  a = "q" ;\n  b = 2\n] ; a & b )'):
        lines = parse_hr(f"Set Variable [ $x ; Value: {calc} ]\nBeep")
        assert len(lines) == 2, calc
        assert not lines[0].display_form_quote
        assert lines[0].params == ["$x", f"Value: {calc}"]
        assert lines[1].step_name == "Beep"


def test_quotes_nested_in_a_calc_bracket_or_a_comment_do_not_trigger():
    inner = parse_hr('Set Variable [ $x ; Value: Let ( [ a = "p" ] ; a ) ]\n# a stray " quote in a comment\nBeep')
    assert [pl.step_name for pl in inner] == ["Set Variable", "# (comment)", "Beep"]
    cmt = parse_hr('Set Variable [ $x ; Value: 1 /* say " */ ]\nBeep')
    assert len(cmt) == 2 and not cmt[0].display_form_quote
    assert not parse_hr('Set Variable [ $x ; Value: Let ( [ a = "p ]" ]')[0].display_form_quote


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                failed += 1
                print(f"FAIL {name}: {e}")
    sys.exit(1 if failed else 0)
