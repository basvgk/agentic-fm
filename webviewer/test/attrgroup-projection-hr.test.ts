/**
 * Export Records, Save Records as Excel and Save Records as PDF read and print
 * their grouped options as FileMaker draws them.
 *
 * FileMaker draws parts of these steps' attribute groups as tokens of their own:
 * Export Records' stored character set bare (`Unicode (UTF-8)`, only with Restore
 * on), Save Records as PDF's `Save to: File` and its records source bare and last
 * (`Blank record, with boxes`). The catalog models each as a `groupFields`
 * projection of the group, so the line reads back into the group. With no path,
 * Export Records and Save Records as Excel draw an empty slot exactly when the
 * step has a <Profile> (`hrEmptySlotWith`). What FileMaker never draws still
 * prints, labeled, after FileMaker's tokens, so our own line round-trips.
 *
 * The cases in agent/fixtures/converter/attrgroup-fm-lines.json were pasted into
 * FileMaker Pro 26.0.3 and read back. Mirrors
 * agent/scripts/test_attrgroup_projection_hr.py.
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

interface FmCase {
  id: string;
  step: string;
  xml: string;
  fmLine: string;
}
const CASES: FmCase[] = JSON.parse(
  readFileSync(path.join(REPO_ROOT, 'agent', 'fixtures', 'converter', 'attrgroup-fm-lines.json'), 'utf-8'),
).cases;

// FileMaker-only display quirks the converters do not reproduce (see the fixture).
const LINE_QUIRKS = new Set([
  'pdf-restoreF-nopath', 'pdf-restoreF-nopath-current', 'pdf-restoreF-nopath-append',
  'pdf-file-nopath-ao-cfOff',
]);

const snippet = (stepXml: string) => `<fmxmlsnippet type="FMObjectList">${stepXml}</fmxmlsnippet>`;

const stepOf = (xml: string): Element => {
  const doc = new DOMParser().parseFromString(xml.replace(/^<\?xml[^>]*\?>/, ''), 'text/xml');
  const root = doc.documentElement;
  return root.tagName === 'Step' ? root : (Array.from(root.children).find((c) => c.tagName === 'Step') as Element);
};
const child = (s: Element, el: string): Element | null =>
  Array.from(s.children).find((c) => c.tagName === el) ?? null;
const probe = (s: Element, el: string, attr: string): string => {
  const n = child(s, el);
  if (n === null) return '<absent>';
  return attr ? (n.getAttribute(attr) ?? '<none>') : (n.textContent ?? '');
};

// The stored state FileMaker's line shows (it hides the PDF file options in Save
// to: Target mode, a no-path PDF's option flags, and the records source of a
// Restore-off no-path PDF).
function lineState(id: string, s: Element): Record<string, string> {
  const m: Record<string, string> = {};
  const pdf = child(s, 'PDFOptions');
  const saveType = pdf ? (child(pdf, 'PDFSaveType')?.textContent ?? '') : '';
  const target = saveType === 'Target';
  const noPath = child(s, 'UniversalPathList') === null;
  m.Restore = probe(s, 'Restore', 'state');
  m.SaveType = probe(s, 'SaveType', 'value');
  if (!target) {
    for (const el of ['NoInteract', 'CreateDirectories', 'Option']) m[el] = probe(s, el, 'state');
    m.UniversalPathList = probe(s, 'UniversalPathList', '');
    if (!(pdf && noPath)) {
      m.AutoOpen = probe(s, 'AutoOpen', 'state');
      m.CreateEmail = probe(s, 'CreateEmail', 'state');
    }
  }
  if (!pdf && noPath && !LINE_QUIRKS.has(id)) m.Profile = child(s, 'Profile') ? 'present' : '<absent>';
  if (probe(s, 'Restore', 'state') === 'True') m.CharacterSet = probe(s, 'ExportOptions', 'CharacterSet');
  if (pdf) {
    m.PDFSaveType = saveType;
    if (!LINE_QUIRKS.has(id)) {
      m.source = pdf.getAttribute('source') ?? '';
      m.appearance = pdf.getAttribute('appearance') ?? '';
    }
    const f = child(s, 'Field');
    m.Field = f === null ? '<absent>' : `${f.textContent ?? ''}|${f.getAttribute('name') ?? ''}`;
  }
  return m;
}

// Element names, sorted attributes (ids and an empty <Text/> marker left out) and
// trimmed text.
function canon(node: Element, skip: Set<string>): string {
  let out = '';
  for (const c of Array.from(node.children)) {
    if (skip.has(c.tagName) || c.tagName === 'DisableStepCollapsed') continue;
    if (c.tagName === 'Text' && c.children.length === 0 && !(c.textContent ?? '').trim()) continue;
    const attrs = Array.from(c.attributes).filter((a) => a.name !== 'id').map((a) => `${a.name}=${a.value}`).sort();
    const text = c.children.length === 0 ? (c.textContent ?? '').trim() : '';
    out += `<${c.tagName}${attrs.map((a) => ' ' + a).join('')}>${text}${canon(c, skip)}</${c.tagName}>`;
  }
  return out;
}

const HIDDEN_LABELS = entries
  .filter((e) => ['Export Records', 'Save Records as Excel', 'Save Records as PDF'].includes(e.name))
  .flatMap((e) => e.params)
  .filter((p) => (p as unknown as Record<string, unknown>).fmLineHidden && p.hrLabel)
  .map((p) => `${p.hrLabel}:`);

const tokens = (line: string): string[] =>
  line.slice(line.indexOf('[') + 1, line.lastIndexOf(']')).split(' ;').map((t) => t.trim());

describe('Export Records / Save Records as Excel / PDF attrGroup HR', () => {
  it.each(CASES)("FileMaker's line converts back to the state it shows ($id)", (c) => {
    expect(lineState(c.id, stepOf(hrToXml(c.fmLine).xml))).toEqual(lineState(c.id, stepOf(c.xml)));
  });

  it.each(CASES)('a no-path line never puts a token into the path ($id)', (c) => {
    if (!c.xml.includes('<UniversalPathList>')) expect(hrToXml(c.fmLine).xml).not.toContain('<UniversalPathList');
  });

  it.each(CASES)('our line round-trips the whole step ($id)', (c) => {
    // Lossy by design, as on FileMaker's line: Export Records' character set with
    // Restore off, and the PDF file options with Save to: Target. FileMaker adds
    // FileName / WorksheetName / SelectedSheet to an XLSX Profile on its own.
    if (c.id === 'pdf-target-all' || c.id === 'exp-XLSX') return;
    const skip = new Set<string>();
    if (c.step === 'Export Records' && probe(stepOf(c.xml), 'Restore', 'state') === 'False') skip.add('ExportOptions');
    const line = xmlToHr(snippet(c.xml));
    expect(canon(stepOf(hrToXml(line).xml), skip), line).toBe(canon(stepOf(c.xml), skip));
  });

  it.each(CASES)("our line is FileMaker's plus labeled hidden content ($id)", (c) => {
    if (LINE_QUIRKS.has(c.id)) return;
    const kept = tokens(xmlToHr(snippet(c.xml))).filter((t) => !HIDDEN_LABELS.some((h) => t.startsWith(h)));
    expect(kept).toEqual(tokens(c.fmLine));
  });

  it('still reads the old group body', () => {
    const pdf = hrToXml('Save Records as PDF [ Records: source=CurrentRecord, PDFSaveType=File ]').xml;
    expect(pdf).toContain('<PDFOptions source="CurrentRecord">');
    expect(pdf).toContain('<PDFSaveType>File</PDFSaveType>');
    const exp = hrToXml('Export Records [ Export options: FormatUsingCurrentLayout=True, CharacterSet=Macintosh ]').xml;
    expect(exp).toContain('<Restore state="True"/>');
    expect(exp).toContain('CharacterSet="Macintosh"');
  });
});
