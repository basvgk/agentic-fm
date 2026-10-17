/**
 * A comment whose text holds a line break round-trips through HR as ONE step.
 *
 * FileMaker draws such a comment on several Script Workspace lines, each
 * continuation aligned under the comment text (a CR and an LF draw alike). HR
 * writes it the same way: the break becomes a new line indented past the
 * comment's own indentation, two spaces for a CR (the return FileMaker stores
 * for its own comments) and one tab for an LF (kept from a pasted `&#10;`).
 * xmlToHr used to write the LF raw, so the text after it parsed as a new line
 * and became an `[UNKNOWN STEP]` comment.
 *
 * A disabled comment is `// # text`, as xmlToHr writes it and FileMaker draws
 * it; the parser used to read it as a disabled step named `# text`.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { hrToXml, loadCatalog } from '@/converter/hr-to-xml';
import { xmlToHr } from '@/converter/xml-to-hr';
import type { StepCatalogEntry } from '@/converter/catalog-types';

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const CATALOG_PATH = path.join(REPO_ROOT, 'agent', 'catalogs', 'step-catalog-en.json');
const rawCatalog = JSON.parse(readFileSync(CATALOG_PATH, 'utf-8'));
const entries: StepCatalogEntry[] = rawCatalog.steps ?? rawCatalog;
loadCatalog(entries);

const snippet = (steps: string) => `<fmxmlsnippet type="FMObjectList">${steps}</fmxmlsnippet>`;
const disabledComment = (t: string) =>
  `<Step enable="False" id="89" name="# (comment)"><Text>${t}</Text></Step>`;
const comment = (t: string) => `<Step enable="True" id="89" name="# (comment)"><Text>${t}</Text></Step>`;
const texts = (xml: string) => [...xml.matchAll(/<Text>([\s\S]*?)<\/Text>/g)].map((m) => m[1]);
// How hrToXml writes FileMaker's text back: a CR as `&#13;`, an LF and a tab raw.
const asEmitted = (t: string) => t.replace(/&#10;/g, '\n').replace(/&#9;/g, '\t');

describe('comment line breaks in HR', () => {
  it('writes a CR as a two-space continuation and an LF as a tab one', () => {
    expect(xmlToHr(snippet(comment('a&#13;b')))).toBe('# a\n  b');
    expect(xmlToHr(snippet(comment('a&#10;b')))).toBe('# a\n\tb');
    expect(xmlToHr(snippet(comment('a&#13;&#10;b')))).toBe('# a\n  \n\tb');
    const nested = xmlToHr(snippet(
      '<Step enable="True" id="68" name="If"><Calculation><![CDATA[1]]></Calculation></Step>' +
      comment('a&#13;b') + '<Step enable="True" id="70" name="End If"/>'));
    expect(nested).toBe('If [ 1 ]\n    # a\n      b\nEnd If');
  });

  it.each([
    'a&#10;b', 'a&#13;b', 'a&#13;&#10;b', 'one&#10;two&#10;&#10;four', 'one&#13;two&#13;&#13;four',
    'a&#10;', 'a&#13;', '&#10;a', '&#13;a', 'a&#13;b&#10;c', 'a&#10;    b', 'a&#13;  b  &#13;c',
    'a&#10;# b', 'a&#13;Beep', 'a &#13;&#9;b',
  ])('round-trips %s as one step', (t) => {
    const { xml, errors } = hrToXml(xmlToHr(snippet(comment(t))));
    expect(errors).toEqual([]);
    expect(texts(xml)).toEqual([asEmitted(t)]);
  });

  it('keeps adjacent comments apart and ends a comment at a blank line', () => {
    const { xml } = hrToXml(xmlToHr(snippet(comment('a&#10;b') + comment('c&#13;d') + comment('e'))));
    expect(texts(xml)).toEqual(['a\nb', 'c&#13;d', 'e']);
    expect(hrToXml('# a\n\n  b').xml.match(/<Step /g)).toHaveLength(3);
  });

  it('reads the authored form as one comment holding CRs', () => {
    const { xml, warnings } = hrToXml('If [ 1 ]\n  # first line\n    second line\n  Beep\nEnd If');
    expect(texts(xml)).toEqual(['first line&#13;second line']);
    expect(xml.match(/<Step /g)).toHaveLength(4);
    expect(warnings).toEqual([]);
    expect(texts(hrToXml('# a\r\n  b\r\nBeep').xml)).toEqual(['a&#13;b']);
  });

  it('warns when a continuation line reads as a step', () => {
    const { xml, warnings } = hrToXml('If [ 1 ]\n# note\n  Beep\nEnd If');
    expect(texts(xml)).toEqual(['note&#13;Beep']);
    expect(warnings.map((w) => w.line)).toEqual([3]);
    expect(hrToXml('# note\n  see Beep below').warnings).toEqual([]);
  });

  it.each(['a', 'a&#13;b', 'a&#10;b', 'one&#13;two&#13;&#13;four', '// note', '# hash', 'a&#13;Beep'])(
    'round-trips the disabled comment %s as one disabled comment',
    (t) => {
      const hr = xmlToHr(snippet(disabledComment(t)));
      expect(hr.startsWith('// # ')).toBe(true);
      const { xml, errors } = hrToXml(hr);
      expect(errors).toEqual([]);
      expect(texts(xml)).toEqual([asEmitted(t)]);
      expect(xml.match(/enable="False"/g)).toHaveLength(1);
      expect(xml).not.toContain('UNKNOWN STEP');
    },
  );

  it('keeps a nested disabled comment beside an enabled comment and a disabled step', () => {
    const hr = xmlToHr(snippet(
      '<Step enable="True" id="68" name="If"><Calculation><![CDATA[1]]></Calculation></Step>' +
      disabledComment('inner&#13;more') + comment('b') +
      '<Step enable="False" id="86" name="Beep"/>' +
      '<Step enable="True" id="70" name="End If"/>'));
    expect(hr).toBe('If [ 1 ]\n    // # inner\n      more\n    # b\n    // Beep\nEnd If');
    const { xml } = hrToXml(hr);
    expect(xml.match(/<Step /g)).toHaveLength(5);
    expect(xml.match(/enable="False"/g)).toHaveLength(2);
    expect(texts(xml)).toEqual(['inner&#13;more', 'b']);
    expect(xml).not.toContain('UNKNOWN STEP');
    expect(texts(hrToXml('//# a\n  b').xml)).toEqual(['a&#13;b']);
  });

  // HR writes `# ` + the text and the parser drops only that one space, so a
  // comment's own leading tab, leading spaces and trailing spaces survive
  // (measured on FileMaker Pro 26.0.3: it stores, copies back and draws them).
  it.each([
    '&#9;[1.0.8]', '   History:', 'a  ', '&#9;tab end&#9;', ' one', '  multi first&#13;  second  ',
    '&#9;', ' &#13; ', '&#13;x',
  ])('keeps the leading and trailing blanks of %j, enabled and disabled', (t) => {
    for (const step of [comment(t), disabledComment(t)]) {
      const { xml, errors } = hrToXml(xmlToHr(snippet(step)));
      expect(errors).toEqual([]);
      expect(texts(xml)).toEqual([asEmitted(t)]);
    }
  });

  it('drops only the one space after the # an author writes', () => {
    expect(xmlToHr(snippet(comment('&#9;[1.0.8]')))).toBe('# \t[1.0.8]');
    const cases: Array<[string, string[]]> = [
      ['#comment', ['comment']], ['# comment', ['comment']], ['#  comment', [' comment']],
      ['#\tcomment', ['\tcomment']], ['# comment  ', ['comment  ']], ['//#comment', ['comment']],
      ['// #  comment', [' comment']], ['# comment\r\nBeep', ['comment']],
      ['#', []], ['# ', []], ['// # ', []],
    ];
    for (const [hr, want] of cases) expect(texts(hrToXml(hr).xml), hr).toEqual(want);
  });
});
