/**
 * Path params FileMaker labels read with their label.
 *
 * FileMaker labels the file path on four steps' Script Workspace lines (Delete File
 * `Target file:`, Rename File `Source file:`, Save a Copy as XML `Destination file:`,
 * Set Dictionary `User Dictionary:`), plus two calculations on the same lines
 * (Rename File `New name:`, Save a Copy as XML `Window name:`, which FileMaker also
 * draws first). It does not label `Output path` on Save a Copy as. The catalog marks
 * the labeled params `hrLabeled`.
 * The cases below were pasted into FileMaker Pro 26.0.3 and read back: each pair is
 * the stored step and the line FileMaker displays. XML→HR must print that line, and
 * the line must convert back to the same step. Mirrors
 * agent/scripts/test_path_param_labels_hr.py.
 *
 * FileMaker's line drops a leading `file:` from a path (`file:a.txt` shows as
 * `“a.txt”`); XML→HR keeps it, so the cases use paths without that prefix.
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

// [step name, id, stored step body, FileMaker's displayed line], measured 2026-10-11.
const CASES: Array<[string, number, string, string]> = [
  [
    'Delete File', 197,
    '<UniversalPathList>$path</UniversalPathList>',
    'Delete File [ Target file: “$path” ]',
  ],
  [
    'Rename File', 199,
    '<UniversalPathList>$path</UniversalPathList><Calculation><![CDATA["x.txt"]]></Calculation>',
    'Rename File [ Source file: “$path” ; New name: "x.txt" ]',
  ],
  [
    'Save a Copy as XML', 3,
    '<Option state="False"/><OutputEntireBinaryData state="False"/>' +
      '<SpecifyJSONOptions state="False"/><UniversalPathList>$out</UniversalPathList>' +
      '<Calculation><![CDATA[Get ( WindowName )]]></Calculation>',
    'Save a Copy as XML [ Window name: Get ( WindowName ) ; Destination file: “$out” ]',
  ],
  [
    'Save a Copy as XML', 3,
    '<Option state="True"/><OutputEntireBinaryData state="True"/>' +
      '<SpecifyJSONOptions state="True"/><UniversalPathList>$out</UniversalPathList>' +
      '<Calculation><![CDATA[$win]]></Calculation>' +
      '<SaXML><JSONOptions><Calculation><![CDATA["{}"]]></Calculation></JSONOptions></SaXML>',
    'Save a Copy as XML [ Window name: $win ; Destination file: “$out” ;' +
      ' Include details for analysis tools ;' +
      " Save each layout object's binary data under its node ;" +
      ' Specify options as JSON: "{}" ]',
  ],
  [
    'Set Dictionary', 209,
    '<MainDictionary value="US English"/><UniversalPathList>$dict</UniversalPathList>',
    'Set Dictionary [ Spelling Language: US English ; User Dictionary: “$dict” ]',
  ],
  [
    'Set Dictionary', 209,
    '<MainDictionary value="US English"/>',
    'Set Dictionary [ Spelling Language: US English ]',
  ],
];

// FileMaker shows Save a Copy as's path unlabeled: `Save a Copy as [ “$out” ; … ]`.
const SAVE_A_COPY_AS =
  '<CreateDirectories state="True"/><AutoOpen state="False"/><CreateEmail state="False"/>' +
  '<SaveAsType value="Copy"/><UniversalPathList>$out</UniversalPathList>';

const snippet = (name: string, id: number, body: string) =>
  '<fmxmlsnippet type="FMObjectList">' +
  `<Step enable="True" id="${id}" name="${name}">${body}</Step>` +
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

describe('path param labels in HR', () => {
  it.each(CASES)('XML→HR prints FileMaker\'s line (%s %#)', (name, id, body, fmLine) => {
    expect(xmlToHr(snippet(name, id, body))).toBe(fmLine);
  });

  it.each(CASES)('FileMaker\'s line converts back to the stored step (%s %#)', (name, id, body, fmLine) => {
    expect(shape(hrToXml(fmLine).xml)).toBe(shape(snippet(name, id, body)));
  });

  it('Save a Copy as keeps its output path unlabeled', () => {
    const line = xmlToHr(snippet('Save a Copy as', 37, SAVE_A_COPY_AS));
    expect(line).toContain('“$out”');
    expect(line).not.toContain('Output path');
  });
});
