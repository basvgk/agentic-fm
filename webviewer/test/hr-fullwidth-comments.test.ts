/**
 * The HR splitters open a calculation comment on every slash/star form FileMaker reads.
 *
 * FileMaker reads `⁄ ∕ ／` as `/` and `∗ ﹡ ＊` as `*` in every comment position: any
 * slash then any star opens a block comment, any two slashes open a line comment, and
 * a paste stores the outer delimiters as ASCII (measured against FileMaker Pro 26.0.2
 * and 26.0.3). The splitters opened a comment on ASCII slash-star and `//` only, so
 * `Set Variable [ $b ; Value: 1 ／＊ c ; d ＊／ + 2 ]` split at the `;` inside the
 * comment and `If [ 1 ／＊ c ; d ＊／ = 1 ]` dropped everything after it. Outside a
 * comment the forms are the division and multiplication operators (`6 ／ 3` is 2) and
 * open nothing. Every calculation below was pasted into FileMaker and copied back with
 * its comment delimiters folded to ASCII. Mirrors agent/scripts/test_hr_fullwidth_comments.py.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { hrToXml, loadCatalog } from '@/converter/hr-to-xml';
import { parseLine } from '@/converter/parser';
import {
  calcBlockCommentOpenLen,
  calcCommentLen,
  calcLineCommentOpenLen,
  hrCalcCommentSpanAt,
  hrNeedsLineBreakAfter,
  hrUnterminatedCalcCommentAt,
} from '@/converter/calc-literal';
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

describe('fullwidth comment markers in the HR splitters', () => {
  it('keeps a ; inside a block comment in every form', () => {
    for (const calc of [
      '1 ／＊ c ; d ＊／ + 2',
      '1 ⁄∗ c ; d ∗⁄ + 2',
      '1 /﹡ c ; d ﹡/ + 2',
      '1 /＊ c ; d ＊/ + 2',
      '1 ∕﹡ a ⁄＊ b ＊⁄ c ∗∕ + 2',
      '1　／＊　c ; d　＊／　+ 2',
      'Left （／＊ c ; ＊／ "abc" ; 1 ）',
    ]) {
      expect(calcs(hrToXml(`Set Variable [ $b ; Value: ${calc} ]`).xml)).toEqual([calc]);
    }
    expect(calcs(hrToXml('If [ 1 ／＊ c ; d ＊／ = 1 ]\nEnd If').xml)).toEqual(['1 ／＊ c ; d ＊／ = 1']);
  });

  it('runs a line comment to the line break', () => {
    expect(calcs(hrToXml('Set Variable [ $b ; Value: 1 ／／ c ; d\n+ 2 ]').xml)).toEqual([
      '1 ／／ c ; d\n+ 2',
    ]);
    // On the last line it ends before the `;`, exactly as the ASCII one-line form.
    expect(params('Set Variable [ $b ; Value: 1 ／／ c ; d ]')).toHaveLength(
      params('Set Variable [ $b ; Value: 1 // c ; d ]').length,
    );
    expect(calcs(hrToXml('Set Variable [ $x ; Value: $y ／／ note ]').xml)).toEqual(['$y ／／ note']);
    expect(hrNeedsLineBreakAfter('"T" ／／ a ; b', ' ; ')).toBe(true);
    expect(hrNeedsLineBreakAfter('400 ／／ Pixels', ' ; ')).toBe(false);
  });

  it('keeps a comma inside a comment in a Parameters list', () => {
    const xml = hrToXml(
      'Perform JavaScript in Web Viewer [ Object Name: "wv" ; Function Name: "f" ; ' +
        'Parameters: 1 ／＊ a , b ＊／ , 2 ]',
    ).xml;
    expect(xml).toContain('<Parameters Count="2">');
    expect(calcs(xml)).toContain('1 ／＊ a , b ＊／');
  });

  it('keeps a ] inside a comment in a variable subscript', () => {
    expect(calcs(hrToXml('Set Variable [ $r[1 ／＊ ] ＊／ + 1] ; Value: 1 ]').xml)).toEqual([
      '1',
      '1 ／＊ ] ＊／ + 1',
    ]);
  });

  it('opens nothing for operators, literals and glued forms', () => {
    expect(params('If [ 6 ／ 3 ; 4 ]')).toHaveLength(2);
    expect(params('If [ 6 ／ 3 ＊ 2 ]')).toEqual(['6 ／ 3 ＊ 2']);
    expect(params('Set Variable [ $b ; Value: "／＊" ; 2 ]')).toHaveLength(3);
    expect(params('Set Variable [ $b ; Value: Let ( x = 1 ； x + 1 ) ／＊ c ; d ＊／ ]')).toEqual([
      '$b',
      'Value: Let ( x = 1 ； x + 1 ) ／＊ c ; d ＊／',
    ]);
    expect(params('Set Variable [ $b ; Value: $y／＊ ; 2 ]')).toHaveLength(3);
  });

  it('reports an unterminated opener and exposes the opener helpers', () => {
    expect(hrUnterminatedCalcCommentAt('1 ⁄∗ x', 2)).toBe(true);
    expect(hrUnterminatedCalcCommentAt('1 ／／ x', 2)).toBe(false);
    expect(hrCalcCommentSpanAt('／＊ ; ＊／', 0)).toBe(7);
    expect(calcCommentLen('∕∗ a ⁄﹡ b ﹡∕ c ＊⁄ + 2', 0)).toEqual({ len: 17, closed: true });
    expect(calcLineCommentOpenLen('／⁄', 0)).toBe(2);
    expect(calcLineCommentOpenLen('/*', 0)).toBe(0);
    expect(calcBlockCommentOpenLen('∕﹡', 0)).toBe(2);
    expect(calcBlockCommentOpenLen('／ ', 0)).toBe(0);
  });
});
