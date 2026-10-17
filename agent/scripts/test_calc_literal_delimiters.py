#!/usr/bin/env python3
"""test_calc_literal_delimiters.py — the converters read all six text-literal
delimiters and all three backslash forms FileMaker reads.

FileMaker delimits a calculation text literal with any of ``"``, ``“``, ``”``,
``„`` (U+201E), ``‟`` (U+201F) and ``＂`` (U+FF02), pairing them freely, and reads
``＼`` (U+FF3C) and ``﹨`` (U+FE68) as the escaping backslash (measured against
FileMaker Pro 26.0.2 and 26.0.3: ``"x„ & Upper ( „y, z„ ) & ＂w＂`` is
``"x" & Upper ( "y, z" ) & "w"``, ``"a＼"b"`` is ``a"b``). The splitters knew only
the first three delimiters and the ASCII backslash, so
``Set Variable [ $x ; Value: „a ; b„ ]`` split at the ``;`` inside the literal and
``"a＼"b ; c"`` closed early. Mirrors the webviewer
``calc-literal-delimiters.test.ts``. Runs under pytest, or standalone.
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
    decode_whole_calc_literal,
    hr_calc_comment_may_open_after,
    is_unescaped_calc_quote,
    quote_calc_literal,
    skip_calc_literal,
)
from catalog_emit import EmptyResolver, convert_step_with_catalog, match_param_values
from catalog_grammar import _group_quote_value, _group_unquote_value, load_catalog

from agent.fmlint.formats.hr_parser import parse_hr

_CATALOG = {
    e.name: e
    for e in load_catalog(os.path.join(REPO_ROOT, "agent", "catalogs", "step-catalog-en.json"))
}

DELIMS = '"“”„‟＂'


def _params(hr: str) -> list:
    return parse_hr(hr)[0].params


def test_every_delimiter_pair_is_one_literal():
    for o in DELIMS:
        for c in DELIMS:
            assert decode_whole_calc_literal(f"{o}a ; b{c}") == "a ; b", (o, c)
            assert _params(f"Set Variable [ $x ; Value: {o}a ; b{c} ]") == ["$x", f"Value: {o}a ; b{c}"]


def test_not_delimiters():
    for ch in "‚‘’«»「」〝〞〟＇":
        assert not is_unescaped_calc_quote(f"{ch}a{ch}", 0), ch


def test_backslash_forms_escape():
    assert decode_whole_calc_literal('"a＼"b"') == 'a"b'
    assert decode_whole_calc_literal('"a﹨"b"') == 'a"b'
    assert decode_whole_calc_literal('"a＼＼b"') == "a＼b"
    assert decode_whole_calc_literal('"a\\＼b"') == "a＼b"
    assert decode_whole_calc_literal('"a＼¶b"') == "a¶b"
    assert decode_whole_calc_literal('"a\\„b"') == "a„b"
    assert decode_whole_calc_literal('"a＼nb"') == "a＼nb"  # before other text it is content
    assert decode_whole_calc_literal('"a"＂b"') == "a＂b"  # doubled delimiter
    for bs in "＼﹨":
        assert _params(f'Set Variable [ $x ; Value: "a{bs}"b ; c" ]') == ["$x", f'Value: "a{bs}"b ; c"']
    # An odd run of mixed forms escapes; an even run does not.
    assert _params('Set Variable [ $x ; Value: "a\\＼" ; 2 ]') == ["$x", 'Value: "a\\＼"', "2"]


def test_quote_round_trips():
    for v in ('a„b', "a＂b", "a‟b", "a＼", "a﹨„", "x＼＼y", 'q\\"', "plain＼z"):
        assert skip_calc_literal(quote_calc_literal(v), 0)[2] == v, v
        assert _group_unquote_value(_group_quote_value(v)) == v, v
    assert quote_calc_literal("plain＼z") == "“plain＼z”"


def test_comment_may_open_after_new_delimiters():
    for q in "„‟＂":
        assert hr_calc_comment_may_open_after(f"{q}a{q}／＊ c ＊／", 3)


def test_emit_keeps_one_calculation():
    calc = '„a ; b„ & ＂x＂ & "a＼"b" ／＊ c ; d ＊／'
    [pl] = parse_hr(f'Show Custom Dialog [ Title: ＂T ; 1＂ ; Message: {calc} ]')
    entry = _CATALOG[pl.step_name]
    xml = convert_step_with_catalog(entry, False, match_param_values(entry, pl.params), EmptyResolver())
    assert re.findall(r"<!\[CDATA\[(.*?)\]\]>", xml)[:2] == ["＂T ; 1＂", calc]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
