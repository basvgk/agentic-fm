#!/usr/bin/env python3
"""test_catalog_emit.py — gate the P6.4 emit engine against the reference fixtures.

``catalog_emit.py`` is a faithful port of the reference HR→fmxmlsnippet emit path and a
line-for-line counterpart of the shipped TS ``catalog-emit.ts``. Since the reference
converter has no SaXML direction (P6.4's defining constraint), the emitter is
gated the same way the TS port was: byte-identity against the committed
``webviewer/test/fixtures/hr-to-xml.json`` — the reference ``/api/hr-to-xml`` output.

For each corpus step: parse the fixture HR into bracket params, run
``match_param_values`` → ``convert_step_with_catalog`` (empty-context resolver → the
``id="0"`` name-only refs the fixtures use), and assert the emitted ``<Step>`` block is
byte-identical to the fixture's XML. Control-flow steps (hand-coded, not the engine's
job) and the 3 FM26-AI grammar-gap steps are excluded — mirroring the TS routing.

Run: ``uvx pytest agent/scripts/test_catalog_emit.py`` (stdlib + pytest only).
"""

from __future__ import annotations

import json
import os
import re

from catalog_emit import (
    EmptyResolver,
    convert_step_with_catalog,
    esc_xml,
    match_param_values,
)
from catalog_grammar import load_catalog

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
_CATALOG = os.path.join(_REPO, "agent", "catalogs", "step-catalog-en.json")
_FIXTURES = os.path.join(_REPO, "webviewer", "test", "fixtures", "hr-to-xml.json")

# Control-flow steps are hand-coded in the converters (the sanctioned exception), not
# rendered by the engine — exactly as catalog-converter.ts routes them to control.ts.
CONTROL_FLOW = {
    "# (comment)", "If", "Else If", "Else", "End If",
    "Loop", "Exit Loop If", "End Loop", "Exit Script", "Set Variable",
}
# The FM26-AI grammar-gap steps stay excluded from every gate (plan §"known gap"):
# FM26 AI steps whose reference fixtures (captured from an earlier FileMaker
# serialization) no longer match the emit engine's FileMaker-26-correct output.
# Configure AI Account is NO LONGER excluded — its wrapper spelling
# (<SetLLMAccout>/<AccoutName> -> <SetLLMAccount>/<AccountName>) and its
# LLMType-governed <VerifySSLCertificates> visibility are now modeled in the
# catalog and its fixture is regenerated, so it round-trips byte-identical
# (verified against live FileMaker 26), mirroring the TS byte-identity gate which
# already includes it.
FM26_AI_SKIP = {
    "Fine-Tune Model",
    "Generate Response from Model",
    "Install Menu Set",
}


# --- minimal HR line parser (port of parser.ts parseLine + splitParams) ---------
def _find_top_level_bracket(text: str) -> int:
    in_quote = False
    for i, c in enumerate(text):
        if c == '"':
            in_quote = not in_quote
        if not in_quote and c == "[":
            return i
    return -1


def _find_matching_bracket(text: str, open_idx: int) -> int:
    depth = 0
    in_quote = False
    for i in range(open_idx, len(text)):
        c = text[i]
        if c == '"':
            in_quote = not in_quote
        if in_quote:
            continue
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                return i
    return -1


def _split_params(content: str) -> list[str]:
    params: list[str] = []
    cur = ""
    in_quote = False
    paren = bracket = 0
    for c in content:
        if c == '"':
            in_quote = not in_quote
            cur += c
            continue
        if in_quote:
            cur += c
            continue
        if c == "(":
            paren += 1
        elif c == ")":
            paren -= 1
        elif c == "[":
            bracket += 1
        elif c == "]":
            bracket -= 1
        if c == ";" and paren == 0 and bracket == 0:
            params.append(cur.strip())
            cur = ""
            continue
        cur += c
    if cur.strip():
        params.append(cur.strip())
    return params


def _parse_hr_line(raw: str) -> tuple[bool, str, list[str]]:
    trimmed = raw.lstrip()
    if not trimmed.strip():
        return (False, "", [])
    if trimmed.startswith("#"):
        return (False, "# (comment)", [])
    disabled = False
    work = trimmed
    if trimmed.startswith("//"):
        disabled = True
        work = trimmed[2:].strip()
    bi = _find_top_level_bracket(work)
    if bi < 0:
        return (disabled, work.strip(), [])
    step_name = work[:bi].strip()
    close = _find_matching_bracket(work, bi)
    content = work[bi + 1 : close].strip() if close >= 0 else work[bi + 1 :].strip()
    return (disabled, step_name, _split_params(content))


def _extract_step_block(xml: str) -> str | None:
    m = re.search(r"^  <Step\b.*?</Step>", xml, re.DOTALL | re.MULTILINE)
    if m:
        return m.group(0)
    m = re.search(r"^  <Step\b[^>]*/>", xml, re.MULTILINE)
    return m.group(0) if m else None


def _emit_self_close(entry, disabled: bool) -> str:
    step_id = entry.id if entry.id is not None else 0
    return (
        '  <Step enable="'
        + ("False" if disabled else "True")
        + f'" id="{step_id}" name="'
        + esc_xml(entry.name)
        + '"/>'
    )


def _load():
    catalog = load_catalog(_CATALOG)
    by_name = {e.name: e for e in catalog}
    for e in catalog:  # trim-tolerant: the one trailing-space name "Configure RAG Account "
        by_name.setdefault(e.name.strip(), e)
    with open(_FIXTURES, encoding="utf-8") as fh:
        fixtures = json.load(fh)
    return by_name, fixtures


def test_emit_byte_identical_to_reference():
    """Every non-control corpus step emits byte-identically to /api/hr-to-xml."""
    by_name, fixtures = _load()
    resolver = EmptyResolver()
    checked = 0
    mismatches: list[str] = []

    for relpath in sorted(fixtures):
        hr = fixtures[relpath]["hr"]
        xml = fixtures[relpath]["xml"]
        disabled, step_name, params = _parse_hr_line(hr)
        if step_name in CONTROL_FLOW or step_name in FM26_AI_SKIP:
            continue
        entry = by_name.get(step_name)
        assert entry is not None, f"{relpath}: no catalog entry for {step_name!r}"

        if entry.self_closing and not entry.params:
            got = _emit_self_close(entry, disabled)
        else:
            values = match_param_values(entry, params)
            got = convert_step_with_catalog(entry, disabled, values, resolver)
        want = _extract_step_block(xml)
        checked += 1
        if got != want:
            mismatches.append(f"{relpath} ({step_name})")

    assert not mismatches, f"{len(mismatches)} emit mismatches: {mismatches[:10]}"
    # Guard against the corpus silently shrinking (203 engine steps at time of writing).
    assert checked >= 200, f"only {checked} engine steps checked — corpus shrank?"


# ---------------------------------------------------------------------------
# Governed-visibility boolean — the hrHidden gate derived on emit.
#
# The facet: an ``hrHidden`` boolean that a sibling's ``visibleWhen`` gates on
# carries no HR token of its own, so HR→XML must DERIVE its state from whether a
# gated companion contributed a token. Letting ``defaultValue`` answer instead
# turns "no stored import order" into "restore the stored order" on every
# round-trip — and FileMaker obeys that flag, discarding what it gated.
#
# The byte-identity gate above cannot catch a regression here: every corpus step
# carrying one of these gates also carries its companion, so the derived value
# and the catalog default agree. Only the companion-absent case separates them.
#
# Mirrors webviewer/test/catalog-emit.engine.test.ts (tests 1-3) — test 4 is
# Python-only because the SaXML reader is.
# ---------------------------------------------------------------------------
def _emit_hr(by_name, hr: str) -> str:
    """HR line -> emitted <Step> block, context-free (the fixtures' id="0" shape)."""
    _disabled, step_name, params = _parse_hr_line(hr)
    entry = by_name[step_name]
    values = match_param_values(entry, params)
    return convert_step_with_catalog(entry, False, values, EmptyResolver())


def test_governed_visibility_derives_gate_open_from_companion():
    """A companion token present => the gate serializes the gate-open value."""
    by_name, _ = _load()
    assert '<Restore state="True"/>' in _emit_hr(
        by_name, "Import Records [ Table: Customers ]")
    assert '<Restore state="True"/>' in _emit_hr(
        by_name, "Export Records [ Export options: CharacterSet=UTF-8 ]")


def test_governed_visibility_derives_gate_closed_not_default_value():
    """No companion token => the closed value, NOT the catalog default of True."""
    by_name, _ = _load()
    assert '<Restore state="False"/>' in _emit_hr(
        by_name, "Import Records [ Import fields: Customers::Name ]")
    assert '<Restore state="False"/>' in _emit_hr(
        by_name, "Export Records [ Create folders: On ]")


def test_governed_visibility_survives_xml_hr_xml_round_trip():
    """The gate carries no HR token — only the companions can preserve it."""
    from snippet_to_hr import snippet_to_hr

    by_name, _ = _load()
    head = ('<fmxmlsnippet type="FMObjectList">'
            '<Step enable="True" id="35" name="Import Records">')
    tail = ('<ImportOptions CharacterSet="UTF-8" method="Add"/>'
            '<Table id="7" name="Customers"/></Step></fmxmlsnippet>')
    for state in ("True", "False"):
        hr = "\n".join(snippet_to_hr(f'{head}<Restore state="{state}"/>{tail}'))
        assert f'<Restore state="{state}"/>' in _emit_hr(by_name, hr), state


def test_hr_hidden_without_gating_sibling_keeps_catalog_default():
    """The derive rule fires ONLY for a gate something actually gates on."""
    by_name, _ = _load()
    out = _emit_hr(
        by_name, "Insert from URL [ Select ; With dialog: Off ; Target: $file ; $url ]")
    assert '<DontEncodeURL state="False"/>' in out


def test_saxml_reading_of_the_gate_wins_over_the_derived_value():
    """A SaXML decoder that read the gate itself keeps its value — the emitter
    derives only into an EMPTY slot.

    ``convert_step_with_catalog`` has two callers in this repo and one in the
    reference: the SaXML reader feeds it a values[] built from a <Step>, where
    the gate may already carry the source's own reading. Export Records' decoder
    sets Restore explicitly; an unconditional derive would throw that away and
    substitute a value derived from HR semantics that never applied here.
    """
    import xml.etree.ElementTree as ET

    from saxml_read import read_saxml_step

    by_name, _ = _load()
    entry = by_name["Export Records"]
    sample = os.path.join(
        _REPO, "agent", "fixtures", "converter", "saxml", "export-records.xml")
    step_el = ET.parse(sample).getroot().find(".//Step")
    assert step_el is not None

    disabled, values, resolver = read_saxml_step(entry, step_el)
    gi = next(i for i, p in enumerate(entry.params) if p.xml_element == "Restore")
    assert values[gi] == "On", "decoder no longer seeds Restore — test premise stale"

    out = convert_step_with_catalog(entry, disabled, values, resolver)
    assert '<Restore state="True"/>' in out

    # And the guard is load-bearing: with the decoder's reading blanked, the
    # derive takes over rather than the slot silently emitting a default.
    values[gi] = ""
    blanked = convert_step_with_catalog(entry, disabled, values, resolver)
    assert '<Restore state="True"/>' in blanked  # this sample DOES carry ExportOptions


# ---------------------------------------------------------------------------
# Cross-file Perform Script (id 1) — the fromFileElement grammar primitive.
#
# FM renders a call into another file as the positional token
# `"NAME" from file: "FILE"`. A script param that opts into the from-file
# grammar (``fromFileElement`` set) must split that infix clause into a
# <FileReference name="FILE"> sibling carrying a
# <UniversalPathList>file:FILE</UniversalPathList> child, emitted BEFORE a
# name-only <Script name="NAME"/>. Live-verified against FileMaker (FM26): FM
# binds the reference by the external-data-source NAME when one exists (the path
# is ignored, no dialog, no regression) and the path preserves the file name
# (`from file: "FILE"`, fail-loud + FM's normal locate prompt) when it does not
# — instead of a name-only reference's silent `from file: ""` drop.
# ---------------------------------------------------------------------------
def test_cross_file_perform_script_emits_filereference_with_universal_path_list():
    by_name, _ = _load()
    out = _emit_hr(
        by_name,
        'Perform Script [ "Sandbox" from file: "QuickStart" ; '
        "Specified: From list ; Parameter: \"hi\" ]",
    )
    # The from-file clause splits off a <FileReference> sibling with a
    # <UniversalPathList>file:NAME</> child (the display name as path — the only
    # value available offline).
    assert '<FileReference name="QuickStart">' in out
    assert "<UniversalPathList>file:QuickStart</UniversalPathList>" in out
    # The <Script> keeps ONLY the name (no ` from file:` swallowed in) and is
    # NOT resolved to a same-file id (the binding lives in the other file).
    assert '<Script name="Sandbox"/>' in out
    assert "from file:" not in out  # clause fully consumed, not leaked into a name


def test_same_file_perform_script_unaffected_by_from_file_grammar():
    by_name, _ = _load()
    out = _emit_hr(by_name, 'Perform Script [ "Sandbox" ; Parameter: "hi" ]')
    # No `from file:` clause => no FileReference; the <Script> is emitted as usual.
    assert "<FileReference" not in out
    assert "<Script " in out


# ---------------------------------------------------------------------------
# Field / variable repetitions — `[N]` in HR, `repetition="N"` in XML.
#
# FileMaker writes a repetition as an attribute on the <Field> element, after
# `id` and before `name` for a field reference (`<Field table="T" id="31"
# repetition="2" name="F"/>`) and on the bare element for a variable
# (`<Field repetition="2">$rep</Field>`), only for N > 1: repetition 1 is
# written as no attribute at all and renders with no subscript. Its Script
# Workspace line shows `T::F[2]` / `$rep[2]`. This holds for step-level field
# and fieldOrVariable params and for the same kinds inside repeatGroup /
# attrGroup entries (Show Custom Dialog inputs, Insert from Device's barcode
# scan source). Shapes captured from FileMaker Pro 26.0.2.
# ---------------------------------------------------------------------------
_SCD_HEAD = (
    '<fmxmlsnippet type="FMObjectList"><Step enable="True" id="87" name="Show Custom Dialog">'
    '<Title><Calculation><![CDATA["T"]]></Calculation></Title>'
    '<Message><Calculation><![CDATA[""]]></Calculation></Message>'
    '<Buttons><Button CommitState="True"><Calculation><![CDATA["OK"]]></Calculation></Button>'
    '<Button CommitState="False"><Calculation><![CDATA["Cancel"]]></Calculation></Button>'
    '<Button CommitState="False"></Button></Buttons><InputFields>'
    '<InputField UsePasswordCharacter="False">'
)
_SCD_TAIL = (
    '</InputField><InputField UsePasswordCharacter="False"><Field table="" id="0" name=""></Field></InputField>'
    '<InputField UsePasswordCharacter="False"><Field table="" id="0" name=""></Field></InputField>'
    "</InputFields></Step></fmxmlsnippet>"
)


def _hr_of(xml: str) -> str:
    from snippet_to_hr import snippet_to_hr

    return "\n".join(snippet_to_hr(xml)).strip()


def test_repetition_renders_as_subscript_in_group_entries():
    """XML -> HR: a repeatGroup / attrGroup entry keeps FileMaker's `[N]`."""
    assert _hr_of(_SCD_HEAD + '<Field repetition="2">$rep</Field>' + _SCD_TAIL) == (
        'Show Custom Dialog [ "T" ; "" ; $rep[2] ]')
    assert _hr_of(
        _SCD_HEAD + '<Field table="Invoices" id="31" repetition="2" name="Description"></Field>'
        + _SCD_TAIL) == 'Show Custom Dialog [ "T" ; "" ; Invoices::Description[2] ]'
    device = _hr_of(
        '<fmxmlsnippet type="FMObjectList"><Step enable="True" id="161" name="Insert from Device">'
        '<InsertFrom value="Barcode"/><Text/><Field>$out</Field><DeviceOptions>'
        '<ScanFrom type="Field"><Field table="Invoices" id="31" repetition="2" name="Description"></Field>'
        '</ScanFrom><Barcodes types="4194303"/></DeviceOptions></Step></fmxmlsnippet>')
    assert "source=Invoices::Description[2]" in device


def test_repetition_renders_as_subscript_at_step_level():
    """XML -> HR: step-level field and fieldOrVariable params keep `[N]`."""
    assert _hr_of(
        '<fmxmlsnippet type="FMObjectList"><Step enable="True" id="76" name="Set Field">'
        '<Calculation><![CDATA[1]]></Calculation>'
        '<Field table="Invoices" id="31" repetition="2" name="Description"/></Step></fmxmlsnippet>'
    ) == "Set Field [ Invoices::Description[2] ; 1 ]"
    assert "Target: $rep[2]" in _hr_of(
        '<fmxmlsnippet type="FMObjectList"><Step enable="True" id="61" name="Insert Text">'
        '<SelectAll state="True"/><Text>x</Text><Field repetition="2">$rep</Field></Step></fmxmlsnippet>')


def test_repetition_one_has_no_subscript():
    """FileMaker never writes repetition="1"; a stray one still renders bare."""
    assert _hr_of(_SCD_HEAD + '<Field repetition="1">$rep</Field>' + _SCD_TAIL) == (
        'Show Custom Dialog [ "T" ; "" ; $rep ]')


def test_repetition_subscript_emits_attribute_in_group_entries():
    """HR -> XML: the subscript leaves the name and becomes repetition="N"."""
    by_name, _ = _load()
    out = _emit_hr(by_name, 'Show Custom Dialog [ "T" ; "" ; $rep[2] ]')
    assert '<Field repetition="2">$rep</Field>' in out
    out = _emit_hr(by_name, 'Show Custom Dialog [ "T" ; "" ; Invoices::Description[2] ]')
    assert '<Field table="Invoices" id="0" repetition="2" name="Description"/>' in out
    out = _emit_hr(
        by_name,
        "Insert from Device [ Type: Barcode ; Target: $out ; Device: "
        "ScanFrom=(type=Field, source=Invoices::Description[2]), Barcodes=(types=4194303) ]")
    assert '<Field table="Invoices" id="0" repetition="2" name="Description"/>' in out


def test_repetition_subscript_emits_attribute_at_step_level():
    by_name, _ = _load()
    out = _emit_hr(by_name, "Set Field [ Invoices::Description[2] ; 1 ]")
    assert '<Field table="Invoices" id="0" repetition="2" name="Description"/>' in out
    out = _emit_hr(by_name, 'Insert Text [ Select ; Target: $rep[2] ; "x" ]')
    assert '<Field repetition="2">$rep</Field>' in out
    out = _emit_hr(by_name, "Insert Calculated Result [ Select ; Target: Invoices::Description[2] ; 1 ]")
    assert '<Field table="Invoices" id="0" repetition="2" name="Description"/>' in out


def test_repetition_one_and_non_numeric_subscripts():
    """`[1]` is the default (no attribute); a non-literal subscript is not a repetition."""
    by_name, _ = _load()
    out = _emit_hr(by_name, "Set Field [ Invoices::Description[1] ; 1 ]")
    assert '<Field table="Invoices" id="0" name="Description"/>' in out
    out = _emit_hr(by_name, 'Show Custom Dialog [ "T" ; "" ; $rep[1] ]')
    assert "<Field>$rep</Field>" in out
    for ref in ("$rep[0]", "$rep[]", "$rep[$i]"):
        out = _emit_hr(by_name, 'Insert Text [ Select ; Target: ' + ref + ' ; "x" ]')
        assert "repetition=" not in out, ref


def _saxml_target(inner: str) -> str:
    return (
        '<Step index="0" id="76" name="Set Field" enable="True"><UUID>X</UUID><ParameterValues membercount="2">'
        '<Parameter type="FieldReference">' + inner + '</Parameter>'
        '<Parameter type="Calculation"><Calculation datatype="1" position="0"><Calculation>'
        "<Text><![CDATA[1]]></Text></Calculation></Calculation></Parameter></ParameterValues></Step>"
    )


def _saxml_rep(text: str) -> str:
    return ('<repetition><Calculation datatype="1" position="10"><Calculation>'
            "<Text><![CDATA[" + text + "]]></Text></Calculation></Calculation></repetition>")


def test_saxml_reference_repetition_becomes_attribute():
    """SaXML -> XML: every SaXML field/variable reference carries a <repetition>
    calc; a literal N > 1 becomes repetition="N", 1 becomes nothing."""
    import xml.etree.ElementTree as ET

    from saxml_read import read_saxml_step

    by_name, _ = _load()
    entry = by_name["Set Field"]
    tor = '<TableOccurrenceReference id="1" name="Invoices" UUID="T"/>'
    for text, want in (("2", ' repetition="2"'), ("1", "")):
        step = ET.fromstring(_saxml_target(
            '<FieldReference id="31" name="Description" UUID="F">' + _saxml_rep(text) + tor
            + "</FieldReference>"))
        disabled, values, resolver = read_saxml_step(entry, step)
        out = convert_step_with_catalog(entry, disabled, values, resolver)
        assert '<Field table="Invoices" id="31"' + want + ' name="Description"/>' in out, text


def test_saxml_calculated_repetition_is_refused_not_dropped():
    """A computed repetition has no fmxmlsnippet form: refuse it loudly."""
    import xml.etree.ElementTree as ET

    import pytest

    from saxml_read import UnsupportedSaXML, read_saxml_step

    by_name, _ = _load()
    step = ET.fromstring(_saxml_target(
        '<FieldReference id="31" name="Description" UUID="F">' + _saxml_rep("$i")
        + '<TableOccurrenceReference id="1" name="Invoices" UUID="T"/></FieldReference>'))
    with pytest.raises(UnsupportedSaXML):
        read_saxml_step(by_name["Set Field"], step)
