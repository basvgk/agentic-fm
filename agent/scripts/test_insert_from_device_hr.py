#!/usr/bin/env python3
"""test_insert_from_device_hr.py — Insert from Device reads and prints its line as
FileMaker draws it.

FileMaker draws the target bare first, then ``Type: <device>``, then the options
that device keeps, joined with ``; ``:
``Insert from Device [ $out ; Type: Camera ; Camera: Back; Resolution: Full; Flash: Auto ]``,
``[ $out ; Type: Barcode ; Scan from: Invoices::Description ]``,
``[ $out ; Type: Signature ; Title: "T"; Message: "M"; Prompt: "P"; Presentation: Full Screen ]``.
The cases in ``agent/fixtures/converter/insert-from-device-fm-lines.json`` were
pasted into FileMaker Pro 26.0.3 and read back: the stored step and the line
FileMaker displays. Mirrors the webviewer ``insert-from-device-hr.test.ts``. Runs
under pytest, or standalone.

FileMaker's line is lossy in two places (``lineHides``): it never draws the
barcode-type mask, and it draws no flashlight mode for a barcode scan from the
front camera. HR to XML of such a line writes all barcode types and leaves the
flashlight mode out (FileMaker fills Auto on paste); the converter's own line
prints both, so its round trip is lossless.
"""

from __future__ import annotations

import json
import os
import sys
import xml.etree.ElementTree as ET

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
with open(
    os.path.join(REPO_ROOT, "agent", "fixtures", "converter", "insert-from-device-fm-lines.json"),
    encoding="utf-8",
) as fh:
    CASES = json.load(fh)["cases"]


def _snippet(step_xml: str) -> str:
    return f'<fmxmlsnippet type="FMObjectList">{step_xml}</fmxmlsnippet>'


def _emit(hr: str) -> str:
    (pl,) = parse_hr(hr)
    entry = _CATALOG[pl.step_name]
    return convert_step_with_catalog(entry, pl.disabled, match_param_values(entry, pl.params), EmptyResolver())


def _canon(step_xml: str, drop: tuple[str, ...] = ()) -> str:
    """The stored step for comparison: no DisableStepCollapsed, no element that is
    empty and attribute-less (FileMaker fills those on paste: Signature's unset
    Title / Message / Prompt), no field id (resolved on paste), no ``drop``."""
    out: list[str] = []

    def walk(e: ET.Element) -> None:
        if e.tag == "DisableStepCollapsed" or e.tag in drop:
            return
        if e.tag != "Step" and not e.attrib and not (e.text or "").strip() and len(e) == 0:
            return
        attrs = {k: v for k, v in e.attrib.items() if not (e.tag == "Step" and k == "enable")}
        if e.tag == "Field":
            attrs.pop("id", None)
        out.append("<" + e.tag + "".join(f' {k}="{attrs[k]}"' for k in sorted(attrs)) + ">")
        if (e.text or "").strip():
            out.append(e.text.strip())
        for c in e:
            walk(c)
        out.append("</" + e.tag + ">")

    root = ET.fromstring(step_xml[step_xml.index("<Step"):step_xml.rindex("</Step>") + 7])
    walk(root)
    return "".join(out)


def test_xml_to_hr_prints_filemakers_line():
    for c in CASES:
        (line,) = snippet_to_hr(_snippet(c["xml"]))
        if not c["lineHides"]:
            assert line == c["fmLine"], (c["label"], line)
        if "Barcodes" in c["lineHides"]:
            assert "Barcode types: " in line, line
        if "LightMode" in c["lineHides"]:
            assert "Flashlight: " in line, line


def test_filemakers_line_converts_back_to_the_stored_step():
    for c in CASES:
        drop = tuple(c["lineHides"])
        assert _canon(_emit(c["fmLine"]), drop) == _canon(c["xml"], drop), c["label"]


def test_our_line_converts_back_to_the_stored_step():
    for c in CASES:
        (line,) = snippet_to_hr(_snippet(c["xml"]))
        assert _canon(_emit(line)) == _canon(c["xml"]), (c["label"], line)


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
