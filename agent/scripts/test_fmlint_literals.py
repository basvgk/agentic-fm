#!/usr/bin/env python3
"""test_fmlint_literals.py — FMLint string-literal grammar.

Checks ``agent.fmlint.literals`` against literal forms whose meaning was
measured in FileMaker Pro 26.0.2 and 26.0.3 (backslash escapes in all three
backslash forms, doubled quotes, the six interchangeable delimiters, comments in
every slash/star form), and checks that the calculation rules C001/C002/C003 no
longer read tokens out of such literals or comments and read the fullwidth
parentheses as parentheses.  Runs under
pytest, or standalone: ``python3 agent/scripts/test_fmlint_literals.py``.
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(os.path.dirname(HERE))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from agent.fmlint import lint
from agent.fmlint.literals import has_unclosed_literal, mask_string_literals

# (calculation text, masked text). Each literal's FileMaker value is noted.
MASK_CASES = [
    ('"Total (net)"', '""'),
    ('"a\\"b"', '""'),                                  # a"b
    ('"a""b"', '""""'),                                  # a"b (doubled quote)
    ('"a\\\\b" & Upper ( x )', '"" & Upper ( x )'),      # a\b, then a real call
    ('"a\\\\\\"b"', '""'),                               # a\"b
    ('"say \\"Save (now)\\" ok"', '""'),                 # say "Save (now)" ok
    ('“Total (net)”', '“”'),         # “Total (net)”
    ('”ab“', '”“'),                   # ”ab“ is a literal too
    ('"ab”', '"”'),                             # "ab” closes on a curly quote
    ('"x“ & Upper ( "y" ) & ”z"',               # "x" & Upper ( "y" ) & "z"
     '"“ & Upper ( "" ) & ”"'),
    ('“a\\”b”', '“”'),           # a”b (escaped curly quote)
    ('"it‘s (x)"', '""'),                           # single curly quotes are content
    ('‘Note (x)’ & Abs ( 1 )', '‘’ & Abs ( 1 )'),
    ('„Total (net)„', '„„'),                     # low-9 quotes delimit
    ('‟ab"', '‟"'),                               # high-reversed-9 pairs with "
    ('＂Foo ( 1 )＂ & Abs ( 1 )', '＂＂ & Abs ( 1 )'),  # fullwidth quote
    ('"x„ & Upper ( „y, z„ ) & ＂w＂', '"„ & Upper ( „„ ) & ＂＂'),
    ('"a＼"b"', '""'),                            # a"b (fullwidth backslash)
    ('"a﹨"b"', '""'),                            # a"b (small backslash)
    ('"a\\＼" & Abs ( 1 )', '"" & Abs ( 1 )'),  # even mixed run: the " closes
    ('"a"＂b" & Upper ( 1 )', '""＂" & Upper ( 1 )'),  # a＂b (doubled delimiter)
    ('1 /* Foo ( 1 ) */ + 2', '1   + 2'),         # a comment is one space
    ('1 ／＊ Foo ( "x ) ＊／ + 2', '1   + 2'),     # nothing inside a comment is code
    ('Abs ( 1 ) // why? Foo (', 'Abs ( 1 )  '),
    ('"a /* b" & 1', '"" & 1'),                   # an opener inside a literal is text
]

UNCLOSED_CASES = [
    ('"a\\"b"', False),
    ('"a\\\\"', False),
    ('"a\\"', True),
    ('"open', True),
    ('“open', True),
    ('"a" & "b"', False),
    ('"a＼"', True),
    ('„open', True),
    ('＂a＂ & ‟b„', False),
    ('1 /* "x */ + 2', False),
]


def test_mask_string_literals():
    for text, expected in MASK_CASES:
        assert mask_string_literals(text) == expected, (text, mask_string_literals(text))


def test_has_unclosed_literal():
    for text, expected in UNCLOSED_CASES:
        assert has_unclosed_literal(text) is expected, text


def _rule_hits(hr, rule_ids):
    result = lint(hr, fmt="hr", config={"max_tier": 1})
    return [(d.rule_id, d.message) for d in result.diagnostics if d.rule_id in rule_ids]


def test_no_phantom_tokens_inside_literals():
    lines = [
        'Set Variable [ $x ; Value: "say \\"Save (now)\\" ok" ]',
        'Set Variable [ $x ; Value: “Total (net)” ]',
        'Set Variable [ $x ; Value: "Total (net)" ]',
        'Set Variable [ $x ; Value: "a\\"b" & Upper ( "c" ) ]',
        'Set Variable [ $x ; Value: "a\\\\" & Lower ( "Q" ) ]',
        'Set Variable [ $x ; Value: „Total (net„ ]',
        'Set Variable [ $x ; Value: ＂Foo ( 1 )＂ & Upper （ "a" ） ]',
        'Set Variable [ $x ; Value: "a＼"Foo ( 1 )" ]',
        'Set Variable [ $x ; Value: 1 ／＊ Foo ( 1 ) ＊／ + 2 ]',
    ]
    for hr in lines:
        assert _rule_hits(hr, {"C001", "C002", "C003"}) == [], hr


def test_real_calls_outside_literals_still_checked():
    hr = 'Set Variable [ $x ; Value: "say \\"hi\\"" & Bogus ( 1 ) ]'
    assert _rule_hits(hr, {"C003"}) == [("C003", 'Unknown function "Bogus" in calculation')]
    hr = 'Set Variable [ $x ; Value: "a\\"" & Upper ( "b" ]'
    assert [r for r, _ in _rule_hits(hr, {"C002"})] == ["C002"]
    hr = 'Set Variable [ $x ; Value: "a\\" ]'
    assert [r for r, _ in _rule_hits(hr, {"C001"})] == ["C001"]
    hr = 'Set Variable [ $x ; Value: "a＼" ]'
    assert [r for r, _ in _rule_hits(hr, {"C001"})] == ["C001"]
    # FileMaker reads （ ﹙ as ( and ） ﹚ as ), so a call written with them is a call.
    hr = "Set Variable [ $x ; Value: Bogus （ 1 ） ]"
    assert _rule_hits(hr, {"C003"}) == [("C003", 'Unknown function "Bogus" in calculation')]
    hr = "Set Variable [ $x ; Value: Abs﹙1﹚＆Bogus（2）、Abs ( 3 ) ]"
    assert _rule_hits(hr, {"C003"}) == [("C003", 'Unknown function "Bogus" in calculation')]
    hr = "Set Variable [ $x ; Value: Upper （ \"a\" ]"
    assert [r for r, _ in _rule_hits(hr, {"C002"})] == ["C002"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
