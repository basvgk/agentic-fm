#!/usr/bin/env python3
"""test_fmlint_literals.py — FMLint string-literal grammar.

Checks ``agent.fmlint.literals`` against literal forms whose meaning was
measured in FileMaker Pro 26.0.2 (backslash escapes, doubled quotes, curly
double quotes as interchangeable delimiters), and checks that the calculation
rules C001/C002/C003 no longer read tokens out of such literals.  Runs under
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
]

UNCLOSED_CASES = [
    ('"a\\"b"', False),
    ('"a\\\\"', False),
    ('"a\\"', True),
    ('"open', True),
    ('“open', True),
    ('"a" & "b"', False),
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


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
