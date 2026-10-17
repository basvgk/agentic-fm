#!/usr/bin/env python3
"""test_calc_comments.py — calculation comments in the human-readable splitters.

FileMaker stores a calculation comment verbatim (``/* … */``, nesting, and ``// …``
to the next return), and the punctuation inside it is not structure. These cases
were pasted into FileMaker Pro 26.0.2 and copied back unchanged; before the comment
span joined the shared grammar (``calc_literal.py``), a ``;``, ``]``, ``,`` or quote
inside a comment split or ended the step on the way XML -> HR -> XML. Mirrors the
webviewer ``catalog-emit.engine.test.ts`` cases of the same names. Runs under
pytest, or standalone: ``python3 agent/scripts/test_calc_comments.py``.
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

import snippet_to_hr
from calc_literal import (
    calc_comment_len,
    hr_calc_comment_span_at,
    hr_needs_line_break_after,
)
from catalog_emit import EmptyResolver, convert_step_with_catalog, match_param_values
from catalog_grammar import load_catalog

from agent.fmlint.formats.hr_parser import parse_hr

_CATALOG = {
    e.name: e
    for e in load_catalog(os.path.join(REPO_ROOT, "agent", "catalogs", "step-catalog-en.json"))
}


def _cd(c: str) -> str:
    return "<![CDATA[" + c + "]]>"


def _pjs(params: list[str]) -> str:
    ps = "".join("<P><Calculation>" + _cd(p) + "</Calculation></P>" for p in params)
    return (
        '<Step enable="True" id="175" name="Perform JavaScript in Web Viewer">'
        "<ObjectName><Calculation>" + _cd('"wv"') + "</Calculation></ObjectName>"
        "<FunctionName><Calculation>" + _cd('"f"') + "</Calculation></FunctionName>"
        f'<Parameters Count="{len(params)}">' + ps + "</Parameters></Step>"
    )


def _scd(title: str, msg: str) -> str:
    return (
        '<Step enable="True" id="87" name="Show Custom Dialog">'
        "<Title><Calculation>" + _cd(title) + "</Calculation></Title>"
        "<Message><Calculation>" + _cd(msg) + "</Calculation></Message></Step>"
    )


_AFTER = '<Step enable="True" id="89" name="# (comment)"><Text>after</Text></Step>'


def _calcs(xml: str) -> list[str]:
    return [c.replace("\r", "\n") for c in re.findall(r"<!\[CDATA\[(.*?)\]\]>", xml, re.DOTALL)]


def _hr_to_xml(hr: str) -> str:
    out = []
    for pl in parse_hr(hr):
        if pl.is_comment:
            out.append("<Text>" + pl.comment_text + "</Text>")
            continue
        entry = _CATALOG[pl.step_name]
        values = match_param_values(entry, pl.params)
        out.append(convert_step_with_catalog(entry, pl.disabled, values, EmptyResolver()))
    return "\n".join(out)


def _round_trip(steps: str) -> tuple[str, str]:
    xml = '<fmxmlsnippet type="FMObjectList">' + steps + "</fmxmlsnippet>"
    hr = "\n".join(snippet_to_hr.snippet_to_hr(xml))
    back = _hr_to_xml(hr)
    want = _calcs(xml)
    assert _calcs(back)[: len(want)] == want, (hr, back)
    return hr, back


def test_grammar_block_nests_line_ends_at_return():
    assert calc_comment_len("/* a /* b */ c */ + 2", 0) == (17, True)
    assert calc_comment_len('/* "*/" */', 0) == (6, True)
    assert calc_comment_len("/* a /* b */", 0) == (12, False)
    assert calc_comment_len("// a /* b\r+ 2", 0) == (9, True)


def test_hr_rule_glued_openers_and_one_line_form():
    assert hr_calc_comment_span_at("filewin://srv/a.csv", 8) == 0
    assert hr_calc_comment_span_at("$y//note", 2) == 0
    assert hr_calc_comment_span_at("1 /* x", 2) == 0
    assert hr_calc_comment_span_at("400 // Pixels ; Width: 600", 4, ";") == 10
    assert hr_calc_comment_span_at("1 // a ; b\n& 2", 2, ";") == 8
    assert not hr_needs_line_break_after("Height: 400 // Pixels", " ; ")
    assert hr_needs_line_break_after('"T" // a ; b', " ; ")
    assert hr_needs_line_break_after("0 // 1 = on, 0 = off", ", ")


def test_block_comments_in_split_values_round_trip():
    _round_trip(_pjs(['/* a, b ; ] */ "x"', '"y"']) + _AFTER)
    _round_trip(_scd('"T" /* ; ] */', '"M"'))
    _round_trip(_scd('"T" /* it"s ; */', '"M"'))
    _round_trip(_pjs(['/* it"s, */ "x"', '"y"']))


def test_line_comments_in_split_values_round_trip():
    _round_trip(_pjs(['"x" // a, b ; ]\r& "y"', '"z"']) + _AFTER)
    _round_trip(_pjs(['"x" // it"s, ;\r& "y"', '"z"']))
    hr, _ = _round_trip(_scd('"T" // x', '"M"'))
    assert '[ "T" // x ; "M"' in hr  # FileMaker's own one-line form stays
    hr, _ = _round_trip(_scd('"T" // a ; b', '"M"'))
    assert '"T" // a ; b\n; "M"' in hr  # a comment holding the separator breaks the line
    _round_trip(_pjs(['"x" // c, d', '"y" // e ] f']) + _AFTER)


def test_authored_one_line_comments_end_at_the_separator():
    [pl] = parse_hr(
        "Move/Resize Window [ Current Window ; Height: 400 // Pixels ; Width: 600 // P ; Top: 100 ]"
    )
    assert pl.params == ["Current Window", "Height: 400 // Pixels", "Width: 600 // P", "Top: 100"]
    lines = parse_hr("Set Variable [ $x ; Value: $y // note ]\nBeep\nSet Variable [ $z ; Value: 2 ]")
    assert [line.step_name for line in lines] == ["Set Variable", "Beep", "Set Variable"]
    assert lines[0].params == ["$x", "Value: $y // note"]
    # A disabled step's // prefix is not a comment; an unmatched /* is plain text.
    d = parse_hr("// Set Variable [ $x ; Value: 1 /* ; */ ]\nShow Custom Dialog [ \"T\" /* x ; \"M\" ]\nBeep")
    assert d[0].disabled and d[0].params == ["$x", "Value: 1 /* ; */"]
    assert d[1].params == ['"T" /* x', '"M"'] and d[2].step_name == "Beep"


def test_many_trailing_comments_then_a_multi_line_comment():
    n = 3000
    hr = "".join(f"Set Variable [ $x ; Value: {i} // n ]\n" for i in range(n))
    hr += (
        'Perform JavaScript in Web Viewer [ Object Name: "wv" ; Function Name: "f" ; '
        'Parameters: "x" // a, b ; ]\n& "y", "z" ]\nSet Variable [ $last ; Value: 1 ]'
    )
    lines = parse_hr(hr)
    assert len(lines) == n + 2
    assert lines[n - 1].params[1] == f"Value: {n - 1} // n"
    assert lines[n].params[2] == 'Parameters: "x" // a, b ; ]\n& "y", "z"'
    assert lines[n + 1].params[0] == "$last"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
