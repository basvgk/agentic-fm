#!/usr/bin/env python3
"""test_path_param_labels_hr.py — path params FileMaker labels read with their label.

FileMaker labels the file path on four steps' Script Workspace lines
(Delete File ``Target file:``, Rename File ``Source file:``, Save a Copy as XML
``Destination file:``, Set Dictionary ``User Dictionary:``), plus two calculations
on the same lines (Rename File ``New name:``, Save a Copy as XML ``Window name:``,
which FileMaker also draws first). It does not label ``Output path`` on Save a Copy
as. The catalog marks the labeled params ``hrLabeled``.
The cases below were pasted into FileMaker Pro 26.0.3 and read back: each pair is
the stored step and the line FileMaker displays. XML -> HR must print that line, and
the line must convert back to the same step. Mirrors the webviewer
``path-param-labels-hr.test.ts``. Runs under pytest, or standalone.

FileMaker's line drops a leading ``file:`` from a path (``file:a.txt`` shows as
``“a.txt”``); XML -> HR keeps it, so the cases use paths without that prefix.
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

# (step name, id, stored step body, FileMaker's displayed line), measured 2026-10-11.
CASES = [
    (
        "Delete File", 197,
        "<UniversalPathList>$path</UniversalPathList>",
        "Delete File [ Target file: “$path” ]",
    ),
    (
        "Rename File", 199,
        '<UniversalPathList>$path</UniversalPathList><Calculation><![CDATA["x.txt"]]></Calculation>',
        'Rename File [ Source file: “$path” ; New name: "x.txt" ]',
    ),
    (
        "Save a Copy as XML", 3,
        '<Option state="False"/><OutputEntireBinaryData state="False"/>'
        '<SpecifyJSONOptions state="False"/><UniversalPathList>$out</UniversalPathList>'
        "<Calculation><![CDATA[Get ( WindowName )]]></Calculation>",
        "Save a Copy as XML [ Window name: Get ( WindowName ) ; Destination file: “$out” ]",
    ),
    (
        "Save a Copy as XML", 3,
        '<Option state="True"/><OutputEntireBinaryData state="True"/>'
        '<SpecifyJSONOptions state="True"/><UniversalPathList>$out</UniversalPathList>'
        "<Calculation><![CDATA[$win]]></Calculation>"
        '<SaXML><JSONOptions><Calculation><![CDATA["{}"]]></Calculation></JSONOptions></SaXML>',
        "Save a Copy as XML [ Window name: $win ; Destination file: “$out” ;"
        " Include details for analysis tools ;"
        " Save each layout object's binary data under its node ;"
        ' Specify options as JSON: "{}" ]',
    ),
    (
        "Set Dictionary", 209,
        '<MainDictionary value="US English"/><UniversalPathList>$dict</UniversalPathList>',
        "Set Dictionary [ Spelling Language: US English ; User Dictionary: “$dict” ]",
    ),
    (
        "Set Dictionary", 209,
        '<MainDictionary value="US English"/>',
        "Set Dictionary [ Spelling Language: US English ]",
    ),
]

# FileMaker shows Save a Copy as's path unlabeled: `Save a Copy as [ “$out” ; … ]`.
_SAVE_A_COPY_AS = (
    '<CreateDirectories state="True"/><AutoOpen state="False"/><CreateEmail state="False"/>'
    '<SaveAsType value="Copy"/><UniversalPathList>$out</UniversalPathList>'
)


def _snippet(name: str, step_id: int, body: str) -> str:
    return (
        '<fmxmlsnippet type="FMObjectList">'
        f'<Step enable="True" id="{step_id}" name="{name}">{body}</Step>'
        "</fmxmlsnippet>"
    )


def _emit(hr: str) -> str:
    (pl,) = parse_hr(hr)
    entry = _CATALOG[pl.step_name]
    return convert_step_with_catalog(entry, pl.disabled, match_param_values(entry, pl.params), EmptyResolver())


def _shape(xml: str) -> str:
    """The step body without whitespace, with an empty element self-closed and an
    empty path list removed (FileMaker drops an empty one on paste)."""
    body = re.search(r"<Step[^>]*>(.*)</Step>", xml, re.DOTALL).group(1)
    body = re.sub(r">\s+<", "><", body).strip()
    body = re.sub(r"<(\w+)([^<>]*)></\1>", r"<\1\2/>", body)
    body = re.sub(r"\s*/>", "/>", body)
    return body.replace("<UniversalPathList/>", "")


def test_xml_to_hr_prints_filemakers_line():
    for name, step_id, body, fm_line in CASES:
        assert snippet_to_hr(_snippet(name, step_id, body)) == [fm_line]


def test_filemakers_line_converts_back_to_the_stored_step():
    for name, step_id, body, fm_line in CASES:
        assert _shape(_emit(fm_line)) == _shape(_snippet(name, step_id, body)), fm_line


def test_save_a_copy_as_output_path_stays_unlabeled():
    (line,) = snippet_to_hr(_snippet("Save a Copy as", 37, _SAVE_A_COPY_AS))
    assert "“$out”" in line and "Output path" not in line, line


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
