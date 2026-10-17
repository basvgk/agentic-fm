#!/usr/bin/env python3
"""test_comment_line_breaks.py — a comment whose text holds a line break reads
back from HR as ONE step.

FileMaker draws such a comment on several Script Workspace lines, each
continuation aligned under the comment text (a CR and an LF draw alike). HR
writes it the same way: the break becomes a new line indented past the
comment's own indentation, two spaces for a CR (the return FileMaker stores for
its own comments) and one tab for an LF (kept from a pasted ``&#10;``). The XML
to HR converter used to write the LF raw, so the text after it parsed as a new
line, a step FMLint could not name. Mirrors the webviewer
``hr-comment-line-breaks.test.ts`` cases. Runs under pytest, or standalone:
``python3 agent/scripts/test_comment_line_breaks.py``.

A disabled comment is ``// # text``, as the converter writes it and FileMaker
draws it; the parser used to read it as a disabled step named ``# text``.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (HERE, REPO_ROOT):
    if p not in sys.path:
        sys.path.insert(0, p)

from snippet_to_hr import snippet_to_hr

from agent.fmlint.formats.hr_parser import parse_hr


def _snippet(steps: str) -> str:
    return f'<fmxmlsnippet type="FMObjectList">{steps}</fmxmlsnippet>'


def _comment(text: str) -> str:
    return f'<Step enable="True" id="89" name="# (comment)"><Text>{text}</Text></Step>'


def _disabled_comment(text: str) -> str:
    return f'<Step enable="False" id="89" name="# (comment)"><Text>{text}</Text></Step>'


def _hr(steps: str) -> str:
    return "\n".join(snippet_to_hr(_snippet(steps)))


def _fm(text: str) -> str:
    """FileMaker's escaped text as the parser's decoded comment text."""
    return text.replace("&#13;", "\r").replace("&#10;", "\n").replace("&#9;", "\t")


def test_hr_form():
    assert _hr(_comment("a&#13;b")) == "# a\n  b"
    assert _hr(_comment("a&#10;b")) == "# a\n\tb"
    assert _hr(_comment("a&#13;&#10;b")) == "# a\n  \n\tb"
    nested = _hr(
        '<Step enable="True" id="68" name="If"><Calculation><![CDATA[1]]></Calculation></Step>'
        + _comment("a&#13;b")
        + '<Step enable="True" id="70" name="End If"/>'
    )
    assert nested == "If [ 1 ]\n    # a\n      b\nEnd If"


def test_round_trip_one_comment_per_step():
    texts = [
        "a&#10;b", "a&#13;b", "a&#13;&#10;b", "one&#10;two&#10;&#10;four",
        "one&#13;two&#13;&#13;four", "a&#10;", "a&#13;", "&#10;a", "&#13;a",
        "a&#13;b&#10;c", "a&#10;    b", "a&#13;  b  &#13;c", "a&#10;# b", "a&#13;Beep",
        "a &#13;&#9;b",
    ]
    for t in texts:
        lines = parse_hr(_hr(_comment(t)))
        assert [(ln.is_comment, ln.comment_text) for ln in lines] == [(True, _fm(t))], t


def test_adjacent_comments_and_blank_line():
    lines = parse_hr(_hr(_comment("a&#10;b") + _comment("c&#13;d") + _comment("e")))
    assert [ln.comment_text for ln in lines] == ["a\nb", "c\rd", "e"]
    assert len(parse_hr("# a\n\n  b")) == 3


def test_authored_form():
    lines = parse_hr("If [ 1 ]\n  # first line\n    second line\n  Beep\nEnd If")
    assert [ln.step_name for ln in lines] == ["If", "# (comment)", "Beep", "End If"]
    assert lines[1].comment_text == "first line\rsecond line"
    crlf = parse_hr("# a\r\n  b\r\nBeep")
    assert crlf[0].comment_text == "a\rb" and crlf[1].step_name.strip() == "Beep"


def test_disabled_comment_round_trip():
    assert _hr(_disabled_comment("a")) == "// # a"
    assert _hr(_disabled_comment("a&#13;b")) == "// # a\n  b"
    for t in ["a", "a&#13;b", "a&#10;b", "one&#13;two&#13;&#13;four", "// note", "# hash", "a&#13;Beep"]:
        lines = parse_hr(_hr(_disabled_comment(t)))
        assert [(ln.is_comment, ln.disabled, ln.comment_text) for ln in lines] == [(True, True, _fm(t))], t


def test_disabled_comment_nested_beside_enabled_and_disabled_step():
    hr = _hr(
        '<Step enable="True" id="68" name="If"><Calculation><![CDATA[1]]></Calculation></Step>'
        + _disabled_comment("inner&#13;more")
        + _comment("b")
        + '<Step enable="False" id="93" name="Beep"/>'
        + '<Step enable="True" id="70" name="End If"/>'
    )
    assert hr == "If [ 1 ]\n    // # inner\n      more\n    # b\n    // Beep\nEnd If"
    lines = parse_hr(hr)
    assert [(ln.step_name.strip(), ln.disabled) for ln in lines] == [
        ("If", False), ("# (comment)", True), ("# (comment)", False), ("Beep", True), ("End If", False)]
    assert lines[1].comment_text == "inner\rmore"
    tight = parse_hr("//# a\n  b")
    assert [(ln.is_comment, ln.disabled, ln.comment_text) for ln in tight] == [(True, True, "a\rb")]


def test_leading_and_trailing_blanks_round_trip():
    """HR writes ``# `` + the text and the parser drops only that one space, so a
    comment's own leading tab, leading spaces and trailing spaces survive (measured
    on FileMaker Pro 26.0.3: it stores, copies back and draws them)."""
    assert _hr(_comment("&#9;[1.0.8]")) == "# \t[1.0.8]"
    texts = ["&#9;[1.0.8]", "   History:", "a  ", "&#9;tab end&#9;", " one",
             "  multi first&#13;  second  ", "&#9;", " &#13; ", "&#13;x"]
    for t in texts:
        lines = parse_hr(_hr(_comment(t)))
        assert [(ln.is_comment, ln.comment_text) for ln in lines] == [(True, _fm(t))], t
        lines = parse_hr(_hr(_disabled_comment(t)))
        assert [(ln.is_comment, ln.disabled, ln.comment_text) for ln in lines] == [(True, True, _fm(t))], t


def test_authored_spacing_after_hash():
    cases = {
        "#comment": "comment", "# comment": "comment", "#  comment": " comment",
        "#\tcomment": "\tcomment", "# comment  ": "comment  ", "//#comment": "comment",
        "// #  comment": " comment", "#": "", "# ": "", "// # ": "",
    }
    for hr, text in cases.items():
        lines = parse_hr(hr)
        assert [(ln.is_comment, ln.comment_text) for ln in lines] == [(True, text)], hr
    crlf = parse_hr("# comment\r\nBeep")
    assert crlf[0].comment_text == "comment"

if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print("ok", name)
