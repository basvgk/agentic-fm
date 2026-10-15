#!/usr/bin/env python3
"""test_icon_replace_keeps_returns.py — replacing a button icon leaves the rest
of the layout snippet byte for byte as it was.

FileMaker writes a return in a text object as ``&#13;``. XML parsing turns that
reference into a CR, and an XML serializer writes the CR back raw; FileMaker
reads a raw CR as a line feed, so a two-line text object copied in the same
snippet as the button would paste back with its return changed to a line feed.
``replace_icon_in_xml`` used to re-serialize the whole snippet that way. Runs
under pytest, or standalone:
``python3 agent/scripts/test_icon_replace_keeps_returns.py``.
"""

from __future__ import annotations

import os
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from fm_icon_extract import (
    extract_icons,
    hex_encode,
    replace_icon_in_xml,
    replace_icons_in_file,
)

OLD_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8"/></svg>'
NEW_SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><rect x="4" y="4" width="16" height="16"/></svg>'


def _stream(svg: str) -> str:
    return (
        f'<Stream size="{len(svg.encode("utf-8"))}">\n'
        f'            <Type>SVG </Type>\n'
        f'            <HexData>{hex_encode(svg)}</HexData>\n'
        f'          </Stream>'
    )


def _snippet(svg: str) -> str:
    # A button with an icon and a two-line text object, in FileMaker's own form:
    # the return as &#13;, a calculation in CDATA.
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<fmxmlsnippet type="LayoutObjectList">\n'
        '  <Layout enclosingRectTop="10.0000000" enclosingRectLeft="10.0000000" '
        'enclosingRectBottom="90.0000000" enclosingRectRight="200.0000000">\n'
        '    <Object type="Button" key="1" LabelKey="0" flags="0" rotation="0">\n'
        '      <ButtonObj buttonFlags="0" iconSize="16">\n'
        '        <Step enable="True" id="16" name="Go to Layout">\n'
        '          <Calculation><![CDATA["a" & ¶ & "b"]]></Calculation>\n'
        '        </Step>\n'
        f'        {_stream(svg)}\n'
        '      </ButtonObj>\n'
        '    </Object>\n'
        '    <Object type="Text" key="2" LabelKey="0" flags="0" rotation="0">\n'
        '      <TextObj flags="0">\n'
        '        <CharacterStyleVector>\n'
        '          <Style>\n'
        '            <Data>L1&#13;L2</Data>\n'
        '          </Style>\n'
        '        </CharacterStyleVector>\n'
        '      </TextObj>\n'
        '    </Object>\n'
        '  </Layout>\n'
        '</fmxmlsnippet>\n'
    )


def test_replace_icon_keeps_text_return_as_reference():
    out = replace_icon_in_xml(_snippet(OLD_SVG), 0, NEW_SVG)
    assert "<Data>L1&#13;L2</Data>" in out
    assert "\r" not in out


def test_replace_icon_changes_only_the_stream():
    out = replace_icon_in_xml(_snippet(OLD_SVG), 0, NEW_SVG)
    assert out == _snippet(NEW_SVG)
    icons = extract_icons(xml_text=out)
    assert len(icons) == 1
    assert icons[0]["svg_text"] == NEW_SVG
    assert icons[0]["stream_size"] == len(NEW_SVG.encode("utf-8"))


def test_replace_icon_out_of_range_raises():
    try:
        replace_icon_in_xml(_snippet(OLD_SVG), 1, NEW_SVG)
    except IndexError:
        return
    raise AssertionError("expected IndexError for icon index 1 of 1")


def test_replace_icons_in_file_keeps_a_raw_cr_in_the_file():
    # A file written with a raw CR keeps it: reading does not translate it to LF.
    src = _snippet(OLD_SVG) + "<!--\r-->"
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "in.xml")
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(src)
        out = replace_icons_in_file(path, {0: NEW_SVG})
    assert out == _snippet(NEW_SVG) + "<!--\r-->"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    sys.exit(1 if failures else 0)
