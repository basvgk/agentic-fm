#!/usr/bin/env python3
"""test_hr_fullwidth_comments.py — the human-readable splitters open a calculation
comment on every slash/star form FileMaker reads.

FileMaker reads ``⁄ ∕ ／`` as ``/`` and ``∗ ﹡ ＊`` as ``*`` in every comment position:
any slash then any star opens a block comment, any two slashes open a line comment,
and a paste stores the outer delimiters as ASCII (measured against FileMaker Pro
26.0.2 and 26.0.3). The splitters opened a comment on ASCII ``/*`` and ``//`` only,
so ``Set Variable [ $b ; Value: 1 ／＊ c ; d ＊／ + 2 ]`` split at the ``;`` inside
the comment and ``If [ 1 ／＊ c ; d ＊／ = 1 ]`` dropped everything after it. Outside
a comment the forms are the division and multiplication operators (``6 ／ 3`` is 2)
and open nothing. Every calculation below was pasted into FileMaker and copied back
with its comment delimiters folded to ASCII. Mirrors the webviewer
``hr-fullwidth-comments.test.ts``. Runs under pytest, or standalone.
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

from calc_literal import (
    calc_block_comment_open_len,
    calc_comment_len,
    calc_line_comment_open_len,
    hr_calc_comment_span_at,
    hr_needs_line_break_after,
    hr_unterminated_calc_comment_at,
)
from catalog_emit import EmptyResolver, _parse_field_subscript, convert_step_with_catalog, match_param_values
from catalog_grammar import load_catalog

from agent.fmlint.formats.hr_parser import parse_hr

_CATALOG = {
    e.name: e
    for e in load_catalog(os.path.join(REPO_ROOT, "agent", "catalogs", "step-catalog-en.json"))
}


def _params(hr: str) -> list:
    return parse_hr(hr)[0].params


def test_block_comment_in_every_form_holds_the_semicolon():
    for calc in (
        "1 ／＊ c ; d ＊／ + 2",
        "1 ⁄∗ c ; d ∗⁄ + 2",
        "1 /﹡ c ; d ﹡/ + 2",
        "1 /＊ c ; d ＊/ + 2",
        "1 ∕﹡ a ⁄＊ b ＊⁄ c ∗∕ + 2",
        "1　／＊　c ; d　＊／　+ 2",
        'Left （／＊ c ; ＊／ "abc" ; 1 ）',
    ):
        assert _params(f"Set Variable [ $b ; Value: {calc} ]") == ["$b", f"Value: {calc}"]
    assert _params("If [ 1 ／＊ c ; d ＊／ = 1 ]") == ["1 ／＊ c ; d ＊／ = 1"]


def test_line_comment_runs_to_the_line_break():
    assert _params("Set Variable [ $b ; Value: 1 ／／ c ; d\n+ 2 ]") == ["$b", "Value: 1 ／／ c ; d\n+ 2"]
    # On the last line it ends before the `;`, exactly as the ASCII one-line form.
    assert len(_params("Set Variable [ $b ; Value: 1 ／／ c ; d ]")) == len(
        _params("Set Variable [ $b ; Value: 1 // c ; d ]")
    )
    # A trailing comment before the step's `]` yields it, as `// note ]` does.
    assert _params("Set Variable [ $x ; Value: $y ／／ note ]") == ["$x", "Value: $y ／／ note"]
    assert hr_needs_line_break_after('"T" ／／ a ; b', " ; ")
    assert not hr_needs_line_break_after("400 ／／ Pixels", " ; ")


def test_parameters_list_comma_inside_comment():
    [pl] = parse_hr(
        'Perform JavaScript in Web Viewer [ Object Name: "wv" ; Function Name: "f" ; '
        "Parameters: 1 ／＊ a , b ＊／ , 2 ]"
    )
    entry = _CATALOG[pl.step_name]
    xml = convert_step_with_catalog(entry, False, match_param_values(entry, pl.params), EmptyResolver())
    assert '<Parameters Count="2">' in xml
    assert re.findall(r"<!\[CDATA\[(.*?)\]\]>", xml)[2] == "1 ／＊ a , b ＊／"


def test_field_subscript_comment_holds_bracket():
    assert _parse_field_subscript("$x[1 ／＊ ] ＊／ + 1]") == ("$x", 0, "1 ／＊ ] ＊／ + 1")


def test_not_a_comment():
    # Division and multiplication.
    assert len(_params("If [ 6 ／ 3 ; 4 ]")) == 2
    assert _params("If [ 6 ／ 3 ＊ 2 ]") == ["6 ／ 3 ＊ 2"]
    # A form inside a literal is text.
    assert len(_params('Set Variable [ $b ; Value: "／＊" ; 2 ]')) == 3
    # `；` stays a calculation separator, never the HR one.
    assert _params("Set Variable [ $b ; Value: Let ( x = 1 ； x + 1 ) ／＊ c ; d ＊／ ]") == [
        "$b",
        "Value: Let ( x = 1 ； x + 1 ) ／＊ c ; d ＊／",
    ]
    # Glued to a word, an opener stays plain text (the HR rule, as for `$y//x`).
    assert len(_params("Set Variable [ $b ; Value: $y／＊ ; 2 ]")) == 3


def test_unterminated_and_helpers():
    assert hr_unterminated_calc_comment_at("1 ⁄∗ x", 2)
    assert not hr_unterminated_calc_comment_at("1 ／／ x", 2)
    assert hr_calc_comment_span_at("／＊ ; ＊／", 0) == 7
    assert calc_comment_len("∕∗ a ⁄﹡ b ﹡∕ c ＊⁄ + 2", 0) == (17, True)
    assert calc_line_comment_open_len("／⁄", 0) == 2
    assert calc_line_comment_open_len("/*", 0) == 0
    assert calc_block_comment_open_len("∕﹡", 0) == 2
    assert calc_block_comment_open_len("／ ", 0) == 0


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
