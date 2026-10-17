/**
 * Insert from Device reads and prints its line as FileMaker draws it.
 *
 * FileMaker draws the target bare first, then `Type: <device>`, then the options
 * that device keeps, joined with `; `:
 * `Insert from Device [ $out ; Type: Camera ; Camera: Back; Resolution: Full; Flash: Auto ]`,
 * `[ $out ; Type: Barcode ; Scan from: Invoices::Description ]`. The cases in
 * agent/fixtures/converter/insert-from-device-fm-lines.json were pasted into
 * FileMaker Pro 26.0.3 and read back: the stored step and the line FileMaker
 * displays. Mirrors agent/scripts/test_insert_from_device_hr.py.
 *
 * FileMaker's line is lossy in two places (`lineHides`): it never draws the
 * barcode-type mask, and it draws no flashlight mode for a barcode scan from the
 * front camera. HR→XML of such a line writes all barcode types and leaves the
 * flashlight mode out (FileMaker fills Auto on paste); the converter's own line
 * prints both, so its round trip is lossless.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { hrToXml, loadCatalog } from '@/converter/hr-to-xml';
import { xmlToHr } from '@/converter/xml-to-hr';
import type { StepCatalogEntry } from '@/converter/catalog-types';

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const rawCatalog = JSON.parse(
  readFileSync(path.join(REPO_ROOT, 'agent', 'catalogs', 'step-catalog-en.json'), 'utf-8'),
);
const entries: StepCatalogEntry[] = rawCatalog.steps ?? rawCatalog;
loadCatalog(entries);

interface DeviceCase {
  label: string;
  xml: string;
  fmLine: string;
  lineHides: string[];
}
const CASES: DeviceCase[] = JSON.parse(
  readFileSync(
    path.join(REPO_ROOT, 'agent', 'fixtures', 'converter', 'insert-from-device-fm-lines.json'),
    'utf-8',
  ),
).cases;

const snippet = (stepXml: string) => `<fmxmlsnippet type="FMObjectList">${stepXml}</fmxmlsnippet>`;

// The stored step for comparison: no DisableStepCollapsed, no element that is
// empty and attribute-less (FileMaker fills those on paste: Signature's unset
// Title / Message / Prompt), no field id (resolved on paste), no `drop`.
function canon(xml: string, drop: string[] = []): string {
  const doc = new DOMParser().parseFromString(xml.slice(xml.indexOf('<Step'), xml.lastIndexOf('</Step>') + 7), 'text/xml');
  const out: string[] = [];
  const walk = (e: Element): void => {
    if (e.tagName === 'DisableStepCollapsed' || drop.includes(e.tagName)) return;
    const text = Array.from(e.childNodes)
      .filter((n) => n.nodeType === 3 || n.nodeType === 4)
      .map((n) => n.nodeValue ?? '')
      .join('')
      .trim();
    if (e.tagName !== 'Step' && e.attributes.length === 0 && !text && e.children.length === 0) return;
    const attrs = Array.from(e.attributes)
      .filter((a) => !(e.tagName === 'Step' && a.name === 'enable') && !(e.tagName === 'Field' && a.name === 'id'))
      .map((a) => ` ${a.name}="${a.value}"`)
      .sort();
    out.push(`<${e.tagName}${attrs.join('')}>`);
    if (text) out.push(text);
    for (const c of Array.from(e.children)) walk(c);
    out.push(`</${e.tagName}>`);
  };
  walk(doc.documentElement);
  return out.join('');
}

describe('Insert from Device HR', () => {
  it.each(CASES)("XML→HR prints FileMaker's line ($label)", (c) => {
    const line = xmlToHr(snippet(c.xml));
    if (c.lineHides.length === 0) expect(line).toBe(c.fmLine);
    if (c.lineHides.includes('Barcodes')) expect(line).toContain('Barcode types: ');
    if (c.lineHides.includes('LightMode')) expect(line).toContain('Flashlight: ');
  });

  it.each(CASES)("FileMaker's line converts back to the stored step ($label)", (c) => {
    expect(canon(hrToXml(c.fmLine).xml, c.lineHides)).toBe(canon(c.xml, c.lineHides));
  });

  it.each(CASES)('our line converts back to the stored step ($label)', (c) => {
    expect(canon(hrToXml(xmlToHr(snippet(c.xml))).xml)).toBe(canon(c.xml));
  });
});
