/**
 * Insert Calculated Result reads target first, calculation last, the way
 * FileMaker shows it.
 *
 * FileMaker stores the step's elements as SelectAll, Calculation, then the target
 * (Field, or Text + Field for a variable), but its Script Workspace line puts the
 * target before the calculation:
 * `Insert Calculated Result [ Select ; Target: Invoices::Description[2] ; 1 ]`.
 * The cases below were pasted into FileMaker Pro 26.0.3 and read back: each pair
 * is FileMaker's stored step and the line it displays. XML→HR must print that
 * line, and the line must convert back to the same step. Mirrors
 * agent/scripts/test_insert_calculated_result_hr_order.py.
 *
 * The round trip compares the target and the calculation. SelectAll is checked
 * only for lines that show `Select`: a line without it still converts to
 * `SelectAll state="True"` here (the catalog's default for a new step), where
 * FileMaker stores `False`.
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

// [FileMaker's stored step body, FileMaker's displayed line], measured 2026-10-11.
const CASES: Array<[string, string]> = [
  [
    '<SelectAll state="True"/><Calculation><![CDATA[1]]></Calculation>' +
      '<Field table="Invoices" id="31" repetition="2" name="Description"/>',
    'Insert Calculated Result [ Select ; Target: Invoices::Description[2] ; 1 ]',
  ],
  [
    '<SelectAll state="False"/><Calculation><![CDATA["abc"]]></Calculation>' +
      '<Field table="Invoices" id="31" name="Description"/>',
    'Insert Calculated Result [ Target: Invoices::Description ; "abc" ]',
  ],
  [
    '<SelectAll state="True"/><Calculation><![CDATA[1]]></Calculation><Text/><Field>$v</Field>',
    'Insert Calculated Result [ Select ; Target: $v ; 1 ]',
  ],
  [
    '<SelectAll state="False"/><Calculation><![CDATA[$a & "x"]]></Calculation>' +
      '<Text/><Field repetition="2">$v</Field>',
    'Insert Calculated Result [ Target: $v[2] ; $a & "x" ]',
  ],
  [
    '<SelectAll state="True"/><Calculation><![CDATA[Get ( CurrentDate )]]></Calculation>',
    'Insert Calculated Result [ Select ; Get ( CurrentDate ) ]',
  ],
  [
    '<SelectAll state="False"/><Calculation><![CDATA[2]]></Calculation>',
    'Insert Calculated Result [ 2 ]',
  ],
];

const snippet = (body: string) =>
  '<fmxmlsnippet type="FMObjectList">' +
  `<Step enable="True" id="77" name="Insert Calculated Result">${body}</Step>` +
  '</fmxmlsnippet>';

// The step body without whitespace, SelectAll or the resolver-dependent field id.
const shape = (xml: string) =>
  (/<Step[^>]*>([\s\S]*)<\/Step>/.exec(xml)?.[1] ?? '')
    .replace(/>\s+</g, '><')
    .trim()
    .replace(/\s*\/>/g, '/>')
    .replace(/<SelectAll state="\w+"\/>/g, '')
    .replace(/ id="\d+"/g, '');

describe('Insert Calculated Result HR order', () => {
  it.each(CASES)('XML→HR prints FileMaker\'s line (%#)', (body, fmLine) => {
    expect(xmlToHr(snippet(body))).toBe(fmLine);
  });

  it.each(CASES)('FileMaker\'s line converts back to the stored step (%#)', (body, fmLine) => {
    expect(shape(hrToXml(fmLine).xml)).toBe(shape(snippet(body)));
  });

  it.each(CASES.filter(([, fmLine]) => fmLine.includes('[ Select ;')))(
    'Select converts back to SelectAll True (%#)',
    (_body, fmLine) => {
      expect(hrToXml(fmLine).xml).toContain('<SelectAll state="True"/>');
    },
  );
});
