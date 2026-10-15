#!/usr/bin/env python3
"""test_save_a_copy_as_hr.py — Save a Copy as reads and prints FileMaker's line.

FileMaker draws Save a Copy as as ``[ path ; copy type ; Automatically open ;
Create email ; Create folders: On|Off ]``: the path first (quoted, unlabeled), the
copy type bare, the two options as bare flags only when on, Create folders last.
With no path it starts at the copy type (``[ copy of current file ; … ]``). The
catalog puts the params in that order with ``hrSlot`` (XML element order is
unchanged), marks the two options ``flagStyle`` and closes the copy type's
vocabulary with ``enumValues``. A bare token naming a later closed-vocabulary
enum's value is that enum's token when the line is short a slot, so the copy type
is not read as the path. The cases below were pasted into FileMaker Pro 26.0.3 and
read back: each pair is the stored step and the line FileMaker displays. XML -> HR
must print that line, and the line must convert back to the same step. Mirrors the
webviewer ``save-a-copy-as-hr.test.ts``. Runs under pytest, or standalone.

FileMaker's line is lossy in two places, both measured: with no path it draws no
option flag although the step keeps them on, and it drops a leading ``file:`` from
a path. XML -> HR prints the flags and keeps the prefix.
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


def _body(cd: str = "True", ao: str = "False", ce: str = "False", kind: str = "Copy", path: str | None = "$out") -> str:
    body = (
        f'<CreateDirectories state="{cd}"/><AutoOpen state="{ao}"/>'
        f'<CreateEmail state="{ce}"/><SaveAsType value="{kind}"/>'
    )
    return body + (f"<UniversalPathList>{path}</UniversalPathList>" if path is not None else "")


# (stored step body, FileMaker's displayed line), measured 2026-10-11.
CASES = [
    (_body(), "Save a Copy as [ “$out” ; copy of current file ; Create folders: On ]"),
    (_body(kind="CompactedCopy"), "Save a Copy as [ “$out” ; compacted copy (smaller) ; Create folders: On ]"),
    (_body(kind="Clone"), "Save a Copy as [ “$out” ; clone (no records) ; Create folders: On ]"),
    (
        _body(kind="SelfContainedCopy"),
        "Save a Copy as [ “$out” ; self-contained copy (single file) ; Create folders: On ]",
    ),
    (_body(ao="True"), "Save a Copy as [ “$out” ; copy of current file ; Automatically open ; Create folders: On ]"),
    (_body(ce="True"), "Save a Copy as [ “$out” ; copy of current file ; Create email ; Create folders: On ]"),
    (
        _body(ao="True", ce="True"),
        "Save a Copy as [ “$out” ; copy of current file ; Automatically open ; Create email ; Create folders: On ]",
    ),
    (_body(cd="False"), "Save a Copy as [ “$out” ; copy of current file ; Create folders: Off ]"),
    (_body(path=None), "Save a Copy as [ copy of current file ; Create folders: On ]"),
    (_body(cd="False", path=None), "Save a Copy as [ copy of current file ; Create folders: Off ]"),
    (_body(kind="Clone", path=None), "Save a Copy as [ clone (no records) ; Create folders: On ]"),
    (
        _body(cd="False", ao="True", ce="True", kind="SelfContainedCopy"),
        "Save a Copy as [ “$out” ; self-contained copy (single file) ; Automatically open ; Create email ;"
        " Create folders: Off ]",
    ),
]


def _snippet(body: str) -> str:
    return (
        '<fmxmlsnippet type="FMObjectList">'
        f'<Step enable="True" id="37" name="Save a Copy as">{body}</Step>'
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
    for body, fm_line in CASES:
        assert snippet_to_hr(_snippet(body)) == [fm_line]


def test_filemakers_line_converts_back_to_the_stored_step():
    for body, fm_line in CASES:
        assert _shape(_emit(fm_line)) == _shape(_snippet(body)), fm_line


def test_no_path_with_options_on_prints_the_flags_filemaker_hides():
    body = _body(ao="True", ce="True", path=None)
    (line,) = snippet_to_hr(_snippet(body))
    assert line == "Save a Copy as [ copy of current file ; Automatically open ; Create email ; Create folders: On ]"
    assert _shape(_emit(line)) == _shape(_snippet(body))


def test_a_path_token_is_never_read_as_the_copy_type():
    # The old element-order line: the path stays a path, and the copy type stays Copy.
    xml = _emit("Save a Copy as [ copy of current file ; “$out” ]")
    assert '<SaveAsType value="Copy"/>' in _shape(xml), xml


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
