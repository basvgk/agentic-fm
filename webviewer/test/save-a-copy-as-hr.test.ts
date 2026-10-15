/**
 * Save a Copy as reads and prints FileMaker's line.
 *
 * FileMaker draws Save a Copy as as `[ path ; copy type ; Automatically open ;
 * Create email ; Create folders: On|Off ]`: the path first (quoted, unlabeled), the
 * copy type bare, the two options as bare flags only when on, Create folders last.
 * With no path it starts at the copy type (`[ copy of current file ; … ]`). The
 * catalog puts the params in that order with `hrSlot` (XML element order is
 * unchanged), marks the two options `flagStyle` and closes the copy type's
 * vocabulary with `enumValues`. A bare token naming a later closed-vocabulary
 * enum's value is that enum's token when the line is short a slot, so the copy type
 * is not read as the path. The cases below were pasted into FileMaker Pro 26.0.3 and
 * read back: each pair is the stored step and the line FileMaker displays. XML→HR
 * must print that line, and the line must convert back to the same step. Mirrors
 * agent/scripts/test_save_a_copy_as_hr.py.
 *
 * FileMaker's line is lossy in two places, both measured: with no path it draws no
 * option flag although the step keeps them on, and it drops a leading `file:` from
 * a path. XML→HR prints the flags and keeps the prefix.
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

const body = ({ cd = 'True', ao = 'False', ce = 'False', kind = 'Copy', out = '$out' as string | null } = {}) =>
  `<CreateDirectories state="${cd}"/><AutoOpen state="${ao}"/>` +
  `<CreateEmail state="${ce}"/><SaveAsType value="${kind}"/>` +
  (out === null ? '' : `<UniversalPathList>${out}</UniversalPathList>`);

// [stored step body, FileMaker's displayed line], measured 2026-10-11.
const CASES: Array<[string, string]> = [
  [body(), 'Save a Copy as [ “$out” ; copy of current file ; Create folders: On ]'],
  [body({ kind: 'CompactedCopy' }), 'Save a Copy as [ “$out” ; compacted copy (smaller) ; Create folders: On ]'],
  [body({ kind: 'Clone' }), 'Save a Copy as [ “$out” ; clone (no records) ; Create folders: On ]'],
  [
    body({ kind: 'SelfContainedCopy' }),
    'Save a Copy as [ “$out” ; self-contained copy (single file) ; Create folders: On ]',
  ],
  [body({ ao: 'True' }), 'Save a Copy as [ “$out” ; copy of current file ; Automatically open ; Create folders: On ]'],
  [body({ ce: 'True' }), 'Save a Copy as [ “$out” ; copy of current file ; Create email ; Create folders: On ]'],
  [
    body({ ao: 'True', ce: 'True' }),
    'Save a Copy as [ “$out” ; copy of current file ; Automatically open ; Create email ; Create folders: On ]',
  ],
  [body({ cd: 'False' }), 'Save a Copy as [ “$out” ; copy of current file ; Create folders: Off ]'],
  [body({ out: null }), 'Save a Copy as [ copy of current file ; Create folders: On ]'],
  [body({ cd: 'False', out: null }), 'Save a Copy as [ copy of current file ; Create folders: Off ]'],
  [body({ kind: 'Clone', out: null }), 'Save a Copy as [ clone (no records) ; Create folders: On ]'],
  [
    body({ cd: 'False', ao: 'True', ce: 'True', kind: 'SelfContainedCopy' }),
    'Save a Copy as [ “$out” ; self-contained copy (single file) ; Automatically open ; Create email ;' +
      ' Create folders: Off ]',
  ],
];

const snippet = (b: string) =>
  '<fmxmlsnippet type="FMObjectList">' +
  `<Step enable="True" id="37" name="Save a Copy as">${b}</Step>` +
  '</fmxmlsnippet>';

// The step body without whitespace, with an empty element self-closed and an empty
// path list removed (FileMaker drops an empty one on paste).
const shape = (xml: string) =>
  (/<Step[^>]*>([\s\S]*)<\/Step>/.exec(xml)?.[1] ?? '')
    .replace(/>\s+</g, '><')
    .trim()
    .replace(/<(\w+)([^<>]*)><\/\1>/g, '<$1$2/>')
    .replace(/\s*\/>/g, '/>')
    .replace('<UniversalPathList/>', '');

describe('Save a Copy as HR', () => {
  it.each(CASES)("XML→HR prints FileMaker's line (%#)", (b, fmLine) => {
    expect(xmlToHr(snippet(b))).toBe(fmLine);
  });

  it.each(CASES)("FileMaker's line converts back to the stored step (%#)", (b, fmLine) => {
    expect(shape(hrToXml(fmLine).xml)).toBe(shape(snippet(b)));
  });

  it('prints the option flags FileMaker hides when there is no path', () => {
    const b = body({ ao: 'True', ce: 'True', out: null });
    const line = xmlToHr(snippet(b));
    expect(line).toBe(
      'Save a Copy as [ copy of current file ; Automatically open ; Create email ; Create folders: On ]',
    );
    expect(shape(hrToXml(line).xml)).toBe(shape(snippet(b)));
  });

  it('never reads a path token as the copy type', () => {
    const xml = shape(hrToXml('Save a Copy as [ copy of current file ; “$out” ]').xml);
    expect(xml).toContain('<SaveAsType value="Copy"/>');
  });
});
