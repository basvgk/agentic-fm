#!/usr/bin/env python3
"""test_insert_calculated_result_hr_order.py — Insert Calculated Result reads
target first, calculation last, the way FileMaker shows it.

FileMaker stores the step's elements as ``SelectAll``, ``Calculation``, then the
target (``Field``, or ``Text`` + ``Field`` for a variable), but its Script
Workspace line puts the target before the calculation:
``Insert Calculated Result [ Select ; Target: Invoices::Description[2] ; 1 ]``.
The cases below were pasted into FileMaker Pro 26.0.3 and read back: each pair is
FileMaker's stored step and the line it displays. XML -> HR must print that line,
and the line must convert back to the same step. Mirrors the webviewer
``insert-calculated-result-hr-order.test.ts``. Runs under pytest, or standalone.

The round trip compares the target and the calculation. ``SelectAll`` is checked
only for lines that show ``Select``: a line without it still converts to
``SelectAll state="True"`` here (the catalog's default for a new step), where
FileMaker stores ``False``.
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
from snippet_to_hr import snippet_to_hr

from agent.fmlint.formats.hr_parser import parse_hr

_CATALOG = {
    e.name: e
    for e in load_catalog(os.path.join(REPO_ROOT, "agent", "catalogs", "step-catalog-en.json"))
}

_STEP = 'Insert Calculated Result'

# (FileMaker's stored step body, FileMaker's displayed line), measured 2026-10-11.
CASES = [
    (
        '<SelectAll state="True"/><Calculation><![CDATA[1]]></Calculation>'
        '<Field table="Invoices" id="31" repetition="2" name="Description"/>',
        "Insert Calculated Result [ Select ; Target: Invoices::Description[2] ; 1 ]",
    ),
    (
        '<SelectAll state="False"/><Calculation><![CDATA["abc"]]></Calculation>'
        '<Field table="Invoices" id="31" name="Description"/>',
        'Insert Calculated Result [ Target: Invoices::Description ; "abc" ]',
    ),
    (
        '<SelectAll state="True"/><Calculation><![CDATA[1]]></Calculation><Text/><Field>$v</Field>',
        "Insert Calculated Result [ Select ; Target: $v ; 1 ]",
    ),
    (
        '<SelectAll state="False"/><Calculation><![CDATA[$a & "x"]]></Calculation>'
        '<Text/><Field repetition="2">$v</Field>',
        'Insert Calculated Result [ Target: $v[2] ; $a & "x" ]',
    ),
    (
        '<SelectAll state="True"/><Calculation><![CDATA[Get ( CurrentDate )]]></Calculation>',
        "Insert Calculated Result [ Select ; Get ( CurrentDate ) ]",
    ),
    (
        '<SelectAll state="False"/><Calculation><![CDATA[2]]></Calculation>',
        "Insert Calculated Result [ 2 ]",
    ),
]


def _snippet(body: str) -> str:
    return (
        '<fmxmlsnippet type="FMObjectList">'
        f'<Step enable="True" id="77" name="{_STEP}">{body}</Step>'
        "</fmxmlsnippet>"
    )


def _emit(hr: str) -> str:
    (pl,) = parse_hr(hr)
    entry = _CATALOG[pl.step_name]
    return convert_step_with_catalog(entry, pl.disabled, match_param_values(entry, pl.params), EmptyResolver())


def _shape(xml: str) -> str:
    """The step body without whitespace, SelectAll or the resolver-dependent field id."""
    body = re.search(r"<Step[^>]*>(.*)</Step>", xml, re.DOTALL).group(1)
    body = re.sub(r">\s+<", "><", body).strip()
    body = re.sub(r'\s*/>', "/>", body)
    body = re.sub(r'<SelectAll state="\w+"/>', "", body)
    return re.sub(r' id="\d+"', "", body)


def test_xml_to_hr_prints_filemakers_line():
    for body, fm_line in CASES:
        assert snippet_to_hr(_snippet(body)) == [fm_line]


def test_filemakers_line_converts_back_to_the_stored_step():
    for body, fm_line in CASES:
        assert _shape(_emit(fm_line)) == _shape(_snippet(body)), fm_line


def test_select_converts_back_to_selectall_true():
    for body, fm_line in CASES:
        if "[ Select ;" in fm_line:
            assert '<SelectAll state="True"/>' in _emit(fm_line), fm_line


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
