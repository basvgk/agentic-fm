/**
 * Engine-level regression net for the governed-visibility boolean in
 * catalog-emit.ts, mirroring the Python agent/scripts/test_catalog_emit.py cases
 * of the same name so the two ports stay structurally parallel.
 *
 * The facet: an `hrHidden` boolean that a sibling's `visibleWhen` gates on
 * carries no HR token of its own, so HR→XML must DERIVE its state from whether
 * a gated companion contributed a token. Letting `defaultValue` answer instead
 * turns "no stored import order" into "restore the stored order" on every
 * round-trip — and FileMaker obeys that flag, discarding what it gated.
 *
 * The 216-step byte-identity suite cannot catch a regression here: every corpus
 * step that carries one of these gates also carries its companion, so the
 * derived value and the catalog default agree. Only the companion-absent case
 * below separates them.
 *
 * Test 4 of the shared list (a SaXML reading of the gate survives unchanged) has
 * no counterpart here — the SaXML reader is Python-only. It lives in
 * agent/scripts/test_catalog_emit.py.
 */
import { describe, it, expect, beforeAll } from 'vitest';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { hrToXml, loadCatalog } from '@/converter/hr-to-xml';
import { xmlToHr } from '@/converter/xml-to-hr';
import type { StepCatalogEntry } from '@/converter/catalog-types';

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const CATALOG_PATH = path.join(REPO_ROOT, 'agent', 'catalogs', 'step-catalog-en.json');

beforeAll(() => {
  const rawCatalog = JSON.parse(readFileSync(CATALOG_PATH, 'utf-8'));
  const entries: StepCatalogEntry[] = rawCatalog.steps ?? rawCatalog;
  loadCatalog(entries);
});

describe('governed-visibility boolean (hrHidden gate derived on emit)', () => {
  it('derives the gate OPEN when a gated companion carries a token', () => {
    // A companion token present => the gate must serialize True, or FileMaker
    // would drop the import order the HR just described.
    expect(hrToXml('Import Records [ Table: Customers ]').xml).toContain(
      '<Restore state="True"/>',
    );
    expect(
      hrToXml('Export Records [ Export options: CharacterSet=UTF-8 ]').xml,
    ).toContain('<Restore state="True"/>');
  });

  it('derives the gate CLOSED when no gated companion does — not defaultValue', () => {
    // Both Restore params default to True in the catalog. This is the case the
    // byte-identity corpus never exercises and the only one that catches a
    // regression.
    expect(
      hrToXml('Import Records [ Import fields: Customers::Name ]').xml,
    ).toContain('<Restore state="False"/>');
    expect(hrToXml('Export Records [ Create folders: On ]').xml).toContain(
      '<Restore state="False"/>',
    );
  });

  it('survives an XML → HR → XML round-trip in both states', () => {
    // The gate carries no HR token, so the round-trip can only preserve it via
    // the companions.
    const head =
      '<fmxmlsnippet type="FMObjectList">' +
      '<Step enable="True" id="35" name="Import Records">';
    const tail =
      '<ImportOptions CharacterSet="UTF-8" method="Add"/>' +
      '<Table id="7" name="Customers"/></Step></fmxmlsnippet>';

    for (const state of ['True', 'False']) {
      const hr = xmlToHr(`${head}<Restore state="${state}"/>${tail}`);
      expect(hrToXml(hr).xml).toContain(`<Restore state="${state}"/>`);
    }
  });

  it('leaves an hrHidden boolean with no gating sibling on its catalog default', () => {
    // The derive rule must fire ONLY for a gate something actually gates on. A
    // plain hidden flag keeps the established behaviour: emit the catalog
    // default and let FileMaker re-canonicalize.
    expect(
      hrToXml('Insert from URL [ Select ; With dialog: Off ; Target: $file ; $url ]').xml,
    ).toContain('<DontEncodeURL state="False"/>');
  });
});

// ---------------------------------------------------------------------------
// Cross-file Perform Script (id 1) — the fromFileElement grammar primitive.
//
// FM renders a call into another file as the positional token
// `"NAME" from file: "FILE"`. A script param that opts into the from-file
// grammar (`fromFileElement` set) must split that infix clause into a
// <FileReference name="FILE"> sibling carrying a
// <UniversalPathList>file:FILE</UniversalPathList> child, emitted BEFORE a
// name-only <Script name="NAME"/>. Live-verified against FileMaker (FM26): FM
// binds the reference by the external-data-source NAME when one exists (path
// ignored, no dialog, no regression) and the path preserves the file name
// (`from file: "FILE"`, fail-loud + FM's normal locate prompt) when it does not
// — instead of a name-only reference's silent `from file: ""` drop. Mirrors the
// Python test_catalog_emit.py cross-file cases.
// ---------------------------------------------------------------------------
describe('cross-file Perform Script (fromFileElement grammar)', () => {
  it('splits the from-file clause into FileReference + UniversalPathList + name-only Script', () => {
    const out = hrToXml(
      'Perform Script [ "Sandbox" from file: "QuickStart" ; Specified: From list ; Parameter: "hi" ]',
    ).xml;
    expect(out).toContain('<FileReference name="QuickStart">');
    expect(out).toContain('<UniversalPathList>file:QuickStart</UniversalPathList>');
    expect(out).toContain('<Script name="Sandbox"/>');
    // The clause is fully consumed — never leaked into a swallowed script name.
    expect(out).not.toContain('from file:');
  });

  it('leaves a same-file call untouched (no FileReference)', () => {
    const out = hrToXml('Perform Script [ "Sandbox" ; Parameter: "hi" ]').xml;
    expect(out).not.toContain('<FileReference');
    expect(out).toContain('<Script ');
  });
});

// Field / variable repetitions: `[N]` in HR, `repetition="N"` in XML. FileMaker
// writes the attribute after `id` and before `name` on a field reference and on
// the bare <Field> of a variable, only for N > 1 (repetition 1 is no attribute
// and no subscript). Holds for step-level field / fieldOrVariable params and for
// the same kinds inside group entries (Show Custom Dialog inputs, Insert from
// Device's scan source). Shapes captured from FileMaker Pro 26.0.2; mirrors the
// Python agent/scripts/test_catalog_emit.py cases of the same name.
describe('field / variable repetitions', () => {
  const scd = (field: string) =>
    '<fmxmlsnippet type="FMObjectList"><Step enable="True" id="87" name="Show Custom Dialog">'
    + '<Title><Calculation><![CDATA["T"]]></Calculation></Title>'
    + '<Message><Calculation><![CDATA[""]]></Calculation></Message>'
    + '<Buttons><Button CommitState="True"><Calculation><![CDATA["OK"]]></Calculation></Button>'
    + '<Button CommitState="False"><Calculation><![CDATA["Cancel"]]></Calculation></Button>'
    + '<Button CommitState="False"></Button></Buttons><InputFields>'
    + `<InputField UsePasswordCharacter="False">${field}</InputField>`
    + '<InputField UsePasswordCharacter="False"><Field table="" id="0" name=""></Field></InputField>'
    + '<InputField UsePasswordCharacter="False"><Field table="" id="0" name=""></Field></InputField>'
    + '</InputFields></Step></fmxmlsnippet>';

  it('renders a group entry repetition as a subscript', () => {
    expect(xmlToHr(scd('<Field repetition="2">$rep</Field>')).trim()).toBe(
      'Show Custom Dialog [ "T" ; "" ; $rep[2] ]',
    );
    expect(
      xmlToHr(scd('<Field table="Invoices" id="31" repetition="2" name="Description"></Field>')).trim(),
    ).toBe('Show Custom Dialog [ "T" ; "" ; Invoices::Description[2] ]');
    expect(
      xmlToHr(
        '<fmxmlsnippet type="FMObjectList"><Step enable="True" id="161" name="Insert from Device">'
        + '<InsertFrom value="Barcode"/><Text/><Field>$out</Field><DeviceOptions>'
        + '<ScanFrom type="Field"><Field table="Invoices" id="31" repetition="2" name="Description"></Field>'
        + '</ScanFrom><Barcodes types="4194303"/></DeviceOptions></Step></fmxmlsnippet>',
      ),
    ).toContain('source=Invoices::Description[2]');
  });

  it('renders a step-level repetition as a subscript', () => {
    expect(
      xmlToHr(
        '<fmxmlsnippet type="FMObjectList"><Step enable="True" id="76" name="Set Field">'
        + '<Calculation><![CDATA[1]]></Calculation>'
        + '<Field table="Invoices" id="31" repetition="2" name="Description"/></Step></fmxmlsnippet>',
      ).trim(),
    ).toBe('Set Field [ Invoices::Description[2] ; 1 ]');
    expect(
      xmlToHr(
        '<fmxmlsnippet type="FMObjectList"><Step enable="True" id="61" name="Insert Text">'
        + '<SelectAll state="True"/><Text>x</Text><Field repetition="2">$rep</Field></Step></fmxmlsnippet>',
      ),
    ).toContain('Target: $rep[2]');
  });

  it('gives repetition 1 no subscript', () => {
    expect(xmlToHr(scd('<Field repetition="1">$rep</Field>')).trim()).toBe(
      'Show Custom Dialog [ "T" ; "" ; $rep ]',
    );
  });

  it('emits a group entry subscript as the repetition attribute', () => {
    expect(hrToXml('Show Custom Dialog [ "T" ; "" ; $rep[2] ]').xml).toContain(
      '<Field repetition="2">$rep</Field>',
    );
    expect(hrToXml('Show Custom Dialog [ "T" ; "" ; Invoices::Description[2] ]').xml).toContain(
      '<Field table="Invoices" id="0" repetition="2" name="Description"/>',
    );
    expect(
      hrToXml(
        'Insert from Device [ Type: Barcode ; Target: $out ; Device: '
        + 'ScanFrom=(type=Field, source=Invoices::Description[2]), Barcodes=(types=4194303) ]',
      ).xml,
    ).toContain('<Field table="Invoices" id="0" repetition="2" name="Description"/>');
  });

  it('emits a step-level subscript as the repetition attribute', () => {
    expect(hrToXml('Set Field [ Invoices::Description[2] ; 1 ]').xml).toContain(
      '<Field table="Invoices" id="0" repetition="2" name="Description"/>',
    );
    expect(hrToXml('Insert Text [ Select ; Target: $rep[2] ; "x" ]').xml).toContain(
      '<Field repetition="2">$rep</Field>',
    );
    expect(
      hrToXml('Insert Calculated Result [ Select ; Target: Invoices::Description[2] ; 1 ]').xml,
    ).toContain('<Field table="Invoices" id="0" repetition="2" name="Description"/>');
  });

  it('treats [1] as the default and a non-literal subscript as no repetition', () => {
    expect(hrToXml('Set Field [ Invoices::Description[1] ; 1 ]').xml).toContain(
      '<Field table="Invoices" id="0" name="Description"/>',
    );
    expect(hrToXml('Show Custom Dialog [ "T" ; "" ; $rep[1] ]').xml).toContain('<Field>$rep</Field>');
    for (const ref of ['$rep[0]', '$rep[]', '$rep[$i]']) {
      expect(hrToXml(`Insert Text [ Select ; Target: ${ref} ; "x" ]`).xml).not.toContain('repetition=');
    }
  });
});
