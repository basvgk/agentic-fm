/**
 * The HR splitters read every form FileMaker reads as a parenthesis or bracket.
 *
 * FileMaker reads `﹙ （` as `(`, `﹚ ）` as `)`, `［` as `[` and `］` as `]` in a
 * calculation, pairing them freely with the ASCII forms, and stores them as ASCII
 * on paste (measured against FileMaker Pro 26.0.2 and 26.0.3). The splitters
 * counted ASCII parentheses only, so `If [ Left （ "abc" ; 2 ） = "ab" ]` split at
 * the `;` and dropped the rest. The step's own `[ ]` stay ASCII: a stray `］` never
 * closes a step. Every calculation below was pasted into FileMaker and copied back
 * with its punctuation folded to ASCII. Mirrors agent/scripts/test_hr_fullwidth_parens.py.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { hrToXml, loadCatalog } from '@/converter/hr-to-xml';
import { parseLine, parseScript } from '@/converter/parser';
import { hrBracketDepthDelta } from '@/converter/calc-literal';
import type { StepCatalogEntry } from '@/converter/catalog-types';

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const rawCatalog = JSON.parse(
  readFileSync(path.join(REPO_ROOT, 'agent', 'catalogs', 'step-catalog-en.json'), 'utf-8'),
);
const entries: StepCatalogEntry[] = rawCatalog.steps ?? rawCatalog;
loadCatalog(entries);

const calcs = (xml: string) =>
  [...xml.matchAll(/<!\[CDATA\[([\s\S]*?)\]\]>/g)].map((m) => m[1].replace(/\r/g, '\n'));
const params = (hr: string) => parseLine(hr, 1).params;

describe('fullwidth parentheses and brackets in the HR splitters', () => {
  it('keeps a ; inside fullwidth parentheses in the calculation', () => {
    expect(params('Set Variable [ $b ; Value: Left （ "abc" ; 2 ） ]')).toEqual([
      '$b',
      'Value: Left （ "abc" ; 2 ）',
    ]);
    expect(calcs(hrToXml('If [ Left （ "abc" ; 2 ） = "ab" ]\nEnd If').xml)).toEqual([
      'Left （ "abc" ; 2 ） = "ab"',
    ]);
    expect(params('If [ Left ﹙ "abc" ; 2 ﹚ = "ab" ]')).toEqual(['Left ﹙ "abc" ; 2 ﹚ = "ab"']);
    expect(params('If [ Left （ Middle ( "abcd" ; 1 ; 3 ） ; 2 ) = "ab" ]')).toEqual([
      'Left （ Middle ( "abcd" ; 1 ; 3 ） ; 2 ) = "ab"',
    ]);
  });

  it('leaves the fullwidth semicolon and literals as they were', () => {
    expect(params('Set Variable [ $a ; Value: Left （ "abc" ； 2 ） ]')).toHaveLength(2);
    expect(params('Set Variable [ $f ; Value: "（ ; ）" & Left （ "a;b" ; 1 ） ]')).toEqual([
      '$f',
      'Value: "（ ; ）" & Left （ "a;b" ; 1 ）',
    ]);
    expect(params('Set Variable [ $u ; Value: "（" ; 2 ]')).toHaveLength(3);
    expect(params('Set Variable [ $d ; Value: Left ( "abc" ; 2 ) ]')).toHaveLength(2);
  });

  it('reads calculation brackets in every form, the step bracket in ASCII only', () => {
    expect(params('Set Variable [ $h ; Value: Let ( ［ a = 1 ; b = 2 ] ; a + b ) ]')[1]).toBe(
      'Value: Let ( ［ a = 1 ; b = 2 ] ; a + b )',
    );
    expect(params('Set Variable [ $g ; Value: Let ( [ a = 1 ; b = 2 ］ ; a + b ) ]')[1]).toBe(
      'Value: Let ( [ a = 1 ; b = 2 ］ ; a + b )',
    );
    expect(params('Set Variable [ $k ; Value: "］" & Let ( ［ a = 1 ］ ; a ) ]')[1]).toBe(
      'Value: "］" & Let ( ［ a = 1 ］ ; a )',
    );
    expect(params('Set Variable [ $s ; Value: 1 ］ ]')).toEqual(['$s', 'Value: 1 ］']);
  });

  it('ends a multi-line statement on mixed brackets', () => {
    const lines = parseScript(
      'Set Variable [ $m ; Value: Let ( [\n  a = 1 ］ ; a ) ]\n# after\nSet Variable [ $z ; Value: 2 ]',
    );
    expect(lines).toHaveLength(3);
    expect(lines[0].params[1]).toBe('Value: Let ( [\n  a = 1 ］ ; a )');
    expect(lines[2].params).toEqual(['$z', 'Value: 2']);
  });

  it('keeps a comma inside fullwidth parentheses in one Parameters item', () => {
    const xml = hrToXml(
      'Perform JavaScript in Web Viewer [ Object Name: "wv" ; Function Name: "f" ; ' +
        'Parameters: Left （ "abc" , 2 ）, "x" ]',
    ).xml;
    expect(xml).toContain('<Parameters Count="2">');
    expect(calcs(xml)[2]).toBe('Left （ "abc" , 2 ）');
  });

  it('reads a variable subscript calculation with mixed brackets', () => {
    const xml = hrToXml('Set Variable [ $r[Let ( [ a = 2 ］ ; a )] ; Value: 1 ]').xml;
    expect(calcs(xml)).toEqual(['1', 'Let ( [ a = 2 ］ ; a )']);
    expect(xml).toContain('<Name>$r</Name>');
  });

  it('counts a fullwidth bracket only inside the step bracket', () => {
    expect(hrBracketDepthDelta('[', 0, 0)).toBe(1);
    expect(hrBracketDepthDelta(']', 0, 1)).toBe(-1);
    expect(hrBracketDepthDelta('［', 0, 0)).toBe(0);
    expect(hrBracketDepthDelta('［', 0, 1)).toBe(1);
    expect(hrBracketDepthDelta('］', 0, 1)).toBe(0);
    expect(hrBracketDepthDelta('］', 0, 2)).toBe(-1);
  });
});
