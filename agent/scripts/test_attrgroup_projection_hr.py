#!/usr/bin/env python3
"""test_attrgroup_projection_hr.py — Export Records, Save Records as Excel and
Save Records as PDF read and print their grouped options as FileMaker draws them.

FileMaker draws parts of these steps' attribute groups as tokens of their own:
Export Records' stored character set bare (``Unicode (UTF-8)``, only with Restore
on), Save Records as PDF's ``Save to: File`` and its records source bare and last
(``Blank record, with boxes``). The catalog models each as a ``groupFields``
projection of the group, so the line reads back into the group. With no path,
Export Records and Save Records as Excel draw an empty slot exactly when the step
has a <Profile> (``hrEmptySlotWith``). What FileMaker never draws (Profile, the
export field order, Excel's Worksheet / Title / Subject / Author / Use field
names, the PDF document options) still prints, labeled, after FileMaker's tokens,
so our own line round-trips.

The cases in ``agent/fixtures/converter/attrgroup-fm-lines.json`` were pasted into
FileMaker Pro 26.0.3 and read back: the stored step and the line FileMaker
displays. Mirrors the webviewer ``attrgroup-projection-hr.test.ts``. Runs under
pytest, or standalone.
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
    os.path.join(REPO_ROOT, "agent", "fixtures", "converter", "attrgroup-fm-lines.json"), encoding="utf-8"
) as fh:
    CASES = json.load(fh)["cases"]

# FileMaker-only display quirks the converters do not reproduce (see the fixture).
LINE_QUIRKS = {"pdf-restoreF-nopath", "pdf-restoreF-nopath-current", "pdf-restoreF-nopath-append",
               "pdf-file-nopath-ao-cfOff"}


def _snippet(step_xml: str) -> str:
    return f'<fmxmlsnippet type="FMObjectList">{step_xml}</fmxmlsnippet>'


def _emit(hr: str) -> str:
    (pl,) = parse_hr(hr)
    entry = _CATALOG[pl.step_name]
    return convert_step_with_catalog(entry, pl.disabled, match_param_values(entry, pl.params), EmptyResolver())


def _step(xml: str) -> ET.Element:
    root = ET.fromstring(xml if xml.lstrip().startswith("<Step") else xml.split("?>", 1)[-1])
    return root if root.tag == "Step" else root.find("Step")


def _probe(s: ET.Element, el: str, attr: str) -> str:
    n = s.find(el)
    if n is None:
        return "<absent>"
    return (n.text or "") if not attr else n.get(attr, "<none>")


def _line_state(cid: str, s: ET.Element) -> dict[str, str]:
    """The stored state FileMaker's line shows (it hides the PDF file options in
    Save to: Target mode, a no-path PDF's option flags, and the records source of
    a Restore-off no-path PDF)."""
    m: dict[str, str] = {}
    pdf = s.find("PDFOptions")
    target = pdf is not None and (pdf.findtext("PDFSaveType") or "") == "Target"
    no_path = s.find("UniversalPathList") is None
    m["Restore"] = _probe(s, "Restore", "state")
    m["SaveType"] = _probe(s, "SaveType", "value")
    if not target:
        for el in ("NoInteract", "CreateDirectories", "Option"):
            m[el] = _probe(s, el, "state")
        m["UniversalPathList"] = _probe(s, "UniversalPathList", "")
        if not (pdf is not None and no_path):
            m["AutoOpen"] = _probe(s, "AutoOpen", "state")
            m["CreateEmail"] = _probe(s, "CreateEmail", "state")
    if pdf is None and no_path and cid not in LINE_QUIRKS:
        m["Profile"] = "present" if s.find("Profile") is not None else "<absent>"
    if _probe(s, "Restore", "state") == "True":
        m["CharacterSet"] = _probe(s, "ExportOptions", "CharacterSet")
    if pdf is not None:
        m["PDFSaveType"] = pdf.findtext("PDFSaveType") or ""
        if cid not in LINE_QUIRKS:
            m["source"] = pdf.get("source", "")
            m["appearance"] = pdf.get("appearance", "")
        f = s.find("Field")
        m["Field"] = "<absent>" if f is None else (f.text or "") + "|" + f.get("name", "")
    return m


def _canon(node: ET.Element, skip: set[str]) -> str:
    """Element names, sorted attributes (ids and an empty <Text/> marker left out)
    and trimmed text."""
    out = ""
    for c in node:
        if c.tag in skip or c.tag == "DisableStepCollapsed":
            continue
        if c.tag == "Text" and len(c) == 0 and not (c.text or "").strip():
            continue
        attrs = sorted(f"{k}={v}" for k, v in c.attrib.items() if k != "id")
        out += "<" + c.tag + "".join(" " + a for a in attrs) + ">" + (c.text or "").strip()
        out += _canon(c, skip) + "</" + c.tag + ">"
    return out


def test_filemakers_line_converts_back_to_the_state_it_shows():
    for c in CASES:
        want = _line_state(c["id"], _step(c["xml"]))
        got = _line_state(c["id"], _step(_emit(c["fmLine"])))
        assert got == want, (c["id"], c["fmLine"])


def test_a_no_path_line_never_puts_a_token_into_the_path():
    for c in CASES:
        if "<UniversalPathList>" not in c["xml"]:
            assert "<UniversalPathList" not in _emit(c["fmLine"]), c["fmLine"]


def test_our_line_round_trips_the_whole_step():
    # Lossy by design, as on FileMaker's line: Export Records' character set with
    # Restore off, and the PDF file options with Save to: Target. FileMaker adds
    # FileName / WorksheetName / SelectedSheet to an XLSX Profile and writes them
    # back on paste; the catalog does not model them.
    for c in CASES:
        if c["id"] in ("pdf-target-all", "exp-XLSX"):
            continue
        skip = set()
        if c["step"] == "Export Records" and _probe(_step(c["xml"]), "Restore", "state") == "False":
            skip.add("ExportOptions")
        (line,) = snippet_to_hr(_snippet(c["xml"]))
        assert _canon(_step(_emit(line)), skip) == _canon(_step(c["xml"]), skip), (c["id"], line)


def test_our_line_is_filemakers_plus_labeled_hidden_content():
    hidden_labels = {
        p.hr_label + ":"
        for e in _CATALOG.values()
        if e.name in ("Export Records", "Save Records as Excel", "Save Records as PDF")
        for p in e.params
        if p.raw.get("fmLineHidden") and p.hr_label
    }
    for c in CASES:
        if c["id"] in LINE_QUIRKS:
            continue
        (line,) = snippet_to_hr(_snippet(c["xml"]))
        body = line[line.index("[") + 1 : line.rindex("]")]
        toks = [t.strip() for t in body.split(" ;")]
        kept = [t for t in toks if not any(t.startswith(h) for h in hidden_labels)]
        fm = c["fmLine"]
        fm_toks = [t.strip() for t in fm[fm.index("[") + 1 : fm.rindex("]")].split(" ;")]
        assert kept == fm_toks, (c["id"], line, fm)


def test_old_group_body_still_reads():
    xml = _emit("Save Records as PDF [ Records: source=CurrentRecord, PDFSaveType=File ]")
    assert '<PDFOptions source="CurrentRecord">' in xml
    assert "<PDFSaveType>File</PDFSaveType>" in xml
    xml = _emit("Export Records [ Export options: FormatUsingCurrentLayout=True, CharacterSet=Macintosh ]")
    assert '<Restore state="True"/>' in xml and 'CharacterSet="Macintosh"' in xml


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
