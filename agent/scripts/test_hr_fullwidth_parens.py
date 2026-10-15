#!/usr/bin/env python3
"""test_hr_fullwidth_parens.py — the human-readable splitters read every form
FileMaker reads as a parenthesis or bracket.

FileMaker reads ``﹙ （`` as ``(``, ``﹚ ）`` as ``)``, ``［`` as ``[`` and ``］`` as
``]`` in a calculation, pairing them freely with the ASCII forms, and stores them as
ASCII on paste (measured against FileMaker Pro 26.0.2 and 26.0.3). The splitters
counted ASCII parentheses only, so ``If [ Left （ "abc" ; 2 ） = "ab" ]`` split at
the ``;`` and dropped the rest. The step's own ``[ ]`` stay ASCII: a stray ``］``
never closes a step. Every calculation below was pasted into FileMaker and copied
back with its punctuation folded to ASCII. Mirrors the webviewer
``hr-fullwidth-parens.test.ts``. Runs under pytest, or standalone.
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

from calc_literal import hr_bracket_depth_delta
from catalog_emit import EmptyResolver, _parse_field_subscript, convert_step_with_catalog, match_param_values
from catalog_grammar import load_catalog

from agent.fmlint.formats.hr_parser import parse_hr

_CATALOG = {
    e.name: e
    for e in load_catalog(os.path.join(REPO_ROOT, "agent", "catalogs", "step-catalog-en.json"))
}


def _params(hr: str) -> list:
    [pl] = parse_hr(hr)
    return pl.params


def test_semicolon_inside_fullwidth_parens_stays_in_the_calculation():
    assert _params('Set Variable [ $b ; Value: Left （ "abc" ; 2 ） ]') == [
        "$b",
        'Value: Left （ "abc" ; 2 ）',
    ]
    assert _params('If [ Left （ "abc" ; 2 ） = "ab" ]') == ['Left （ "abc" ; 2 ） = "ab"']
    assert _params('If [ Left ﹙ "abc" ; 2 ﹚ = "ab" ]') == ['Left ﹙ "abc" ; 2 ﹚ = "ab"']
    assert _params('If [ Left （ Middle ( "abcd" ; 1 ; 3 ） ; 2 ) = "ab" ]') == [
        'Left （ Middle ( "abcd" ; 1 ; 3 ） ; 2 ) = "ab"'
    ]


def test_fullwidth_semicolon_and_literals_unchanged():
    assert len(_params('Set Variable [ $a ; Value: Left （ "abc" ； 2 ） ]')) == 2
    assert _params('Set Variable [ $f ; Value: "（ ; ）" & Left （ "a;b" ; 1 ） ]') == [
        "$f",
        'Value: "（ ; ）" & Left （ "a;b" ; 1 ）',
    ]
    assert len(_params('Set Variable [ $u ; Value: "（" ; 2 ]')) == 3
    assert len(_params('Set Variable [ $d ; Value: Left ( "abc" ; 2 ) ]')) == 2


def test_calc_brackets_in_every_form_and_the_step_bracket_ascii():
    assert _params("Set Variable [ $h ; Value: Let ( ［ a = 1 ; b = 2 ] ; a + b ) ]")[1] == (
        "Value: Let ( ［ a = 1 ; b = 2 ] ; a + b )"
    )
    assert _params("Set Variable [ $g ; Value: Let ( [ a = 1 ; b = 2 ］ ; a + b ) ]")[1] == (
        "Value: Let ( [ a = 1 ; b = 2 ］ ; a + b )"
    )
    assert _params('Set Variable [ $k ; Value: "］" & Let ( ［ a = 1 ］ ; a ) ]')[1] == (
        'Value: "］" & Let ( ［ a = 1 ］ ; a )'
    )
    assert _params("Set Variable [ $s ; Value: 1 ］ ]") == ["$s", "Value: 1 ］"]


def test_multi_line_statement_ends_on_mixed_brackets():
    lines = parse_hr("Set Variable [ $m ; Value: Let ( [\n  a = 1 ］ ; a ) ]\n# after\nSet Variable [ $z ; Value: 2 ]")
    assert len(lines) == 3
    assert lines[0].params[1] == "Value: Let ( [\n  a = 1 ］ ; a )"
    assert lines[1].is_comment
    assert lines[2].params == ["$z", "Value: 2"]


def test_parameters_list_comma_inside_fullwidth_parens():
    [pl] = parse_hr(
        'Perform JavaScript in Web Viewer [ Object Name: "wv" ; Function Name: "f" ; '
        'Parameters: Left （ "abc" , 2 ）, "x" ]'
    )
    entry = _CATALOG[pl.step_name]
    xml = convert_step_with_catalog(entry, False, match_param_values(entry, pl.params), EmptyResolver())
    assert '<Parameters Count="2">' in xml
    assert re.findall(r"<!\[CDATA\[(.*?)\]\]>", xml)[2] == 'Left （ "abc" , 2 ）'


def test_field_subscript_calc_brackets_in_every_form():
    assert _parse_field_subscript("$x[Let ( [ a = 1 ］ ; a )]") == ("$x", 0, "Let ( [ a = 1 ］ ; a )")
    assert _parse_field_subscript("$x[$i］") == ("$x[$i］", 0, "")


def test_bracket_depth_delta():
    assert hr_bracket_depth_delta("[", 0, 0) == 1
    assert hr_bracket_depth_delta("]", 0, 1) == -1
    assert hr_bracket_depth_delta("［", 0, 0) == 0
    assert hr_bracket_depth_delta("［", 0, 1) == 1
    assert hr_bracket_depth_delta("］", 0, 1) == 0
    assert hr_bracket_depth_delta("］", 0, 2) == -1


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
