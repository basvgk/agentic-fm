/**
 * An HR line in FileMaker's display form with an odd number of quotes ends at its
 * own `]`.
 *
 * FileMaker draws a literal text parameter as `“` + value + `”` and never escapes
 * the value (measured against FileMaker Pro 26.0.3), so the value `He said “hi`
 * shows as `Insert Text [ Select ; Target: $x ; “He said “hi” ]`: three delimiters.
 * Read with the calculation literal grammar, the last one opened a literal that
 * swallowed the step's `]`, and the multi-line merge folded every following line
 * into the step's text (one more odd line closed it again, with no warning). A
 * literal that opens at the step's own bracket level, does not close on its line,
 * and whose line ends with a delimiter and `]` is FileMaker's closing quote and the
 * step's `]`: the statement ends there and hrToXml says so. Mirrors
 * agent/scripts/test_hr_display_form_quote.py.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { hrToXml, loadCatalog } from '@/converter/hr-to-xml';
import { parseLine, parseScript } from '@/converter/parser';
import type { StepCatalogEntry } from '@/converter/catalog-types';

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const rawCatalog = JSON.parse(
  readFileSync(path.join(REPO_ROOT, 'agent', 'catalogs', 'step-catalog-en.json'), 'utf-8'),
);
const entries: StepCatalogEntry[] = rawCatalog.steps ?? rawCatalog;
loadCatalog(entries);

const stepNames = (xml: string) => [...xml.matchAll(/<Step [^>]*name="([^"]*)"/g)].map((m) => m[1]);
const texts = (xml: string) => [...xml.matchAll(/<Text>([\s\S]*?)<\/Text>/g)].map((m) => m[1]);
const displayWarnings = (r: ReturnType<typeof hrToXml>) =>
  r.warnings.filter((w) => w.message.startsWith('Unbalanced quote'));
const esc = (s: string) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

describe('FileMaker display-form lines with an odd quote', () => {
  it('does not swallow the steps after the line', () => {
    const r = hrToXml('Insert Text [ Select ; Target: $x ; “He said “hi” ]\nBeep\nSet Variable [ $y ; Value: 1 ]');
    expect(stepNames(r.xml)).toEqual(['Insert Text', 'Beep', 'Set Variable']);
    expect(texts(r.xml)).toEqual(['He said “hi']);
    expect(displayWarnings(r).map((w) => w.line)).toEqual([1]);
  });

  it('keeps two odd lines two steps', () => {
    const r = hrToXml(
      'Insert Text [ Select ; Target: $x ; “He said “hi” ]\nBeep\n' +
        'Insert Text [ Select ; Target: $z ; “a “b” ]\nBeep',
    );
    expect(stepNames(r.xml)).toEqual(['Insert Text', 'Beep', 'Insert Text', 'Beep']);
    expect(texts(r.xml)).toEqual(['He said “hi', 'a “b']);
    expect(displayWarnings(r).map((w) => w.line)).toEqual([1, 3]);
  });

  it('reads every single-line shape', () => {
    const cases: [string, string][] = [
      ['Insert Text [ Select ; Target: $x ; “He said “hi” ]', 'He said “hi'],
      ['Insert Text [ Select ; Target: $x ; “a"” ]', 'a"'],
      ['Insert Text [ Select ; Target: $x ; “a\\” ]', 'a\\'],
      ['Insert Text [ Select ; Target: $x ; “x;y"z” ]', 'x;y"z'],
      ['Insert Text [ Select ; Target: $x ; “a [b] "c”   ]  ', 'a [b] "c'],
      ['Insert Text [ Select ; Target: $x ; "He said "hi" ]', 'He said "hi'],
    ];
    for (const [line, text] of cases) {
      const pl = parseLine(line, 1);
      expect(pl.displayFormQuote).toBe(true);
      expect(pl.params).toHaveLength(3);
      const r = hrToXml(line + '\nBeep');
      expect(stepNames(r.xml)).toEqual(['Insert Text', 'Beep']);
      expect(texts(r.xml)).toEqual([esc(text)]);
    }
  });

  it('leaves balanced lines and multi-line calculations alone', () => {
    for (const line of [
      'Insert Text [ Select ; Target: $x ; “He said “hi”” ]',
      'Insert Text [ Select ; Target: $x ; “He said \\“hi” ]',
      'Set Variable [ $x ; Value: "a" ]',
    ]) {
      expect(parseLine(line, 1).displayFormQuote).toBeUndefined();
    }
    for (const calc of ['"a\nb"', '"Items [1]\nnext"', '"x ]\ny"', 'Let ( [\n  a = "q" ;\n  b = 2\n] ; a & b )']) {
      const lines = parseScript(`Set Variable [ $x ; Value: ${calc} ]\nBeep`);
      expect(lines).toHaveLength(2);
      expect(lines[0].displayFormQuote).toBeUndefined();
      expect(lines[0].params).toEqual(['$x', `Value: ${calc}`]);
      expect(lines[1].stepName).toBe('Beep');
    }
  });

  it('ignores quotes nested in a calculation bracket or a comment', () => {
    const inner = parseScript(
      'Set Variable [ $x ; Value: Let ( [ a = "p" ] ; a ) ]\n# a stray " quote in a comment\nBeep',
    );
    expect(inner.map((l) => l.stepName)).toEqual(['Set Variable', '# (comment)', 'Beep']);
    const cmt = parseScript('Set Variable [ $x ; Value: 1 /* say " */ ]\nBeep');
    expect(cmt).toHaveLength(2);
    expect(cmt[0].displayFormQuote).toBeUndefined();
    expect(parseLine('Set Variable [ $x ; Value: Let ( [ a = "p ]" ]', 1).displayFormQuote).toBeUndefined();
  });
});
