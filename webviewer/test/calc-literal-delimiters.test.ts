/**
 * The converters read all six text-literal delimiters and all three backslash forms
 * FileMaker reads.
 *
 * FileMaker delimits a calculation text literal with any of `"`, `“`, `”`, `„`
 * (U+201E), `‟` (U+201F) and `＂` (U+FF02), pairing them freely, and reads `＼`
 * (U+FF3C) and `﹨` (U+FE68) as the escaping backslash (measured against FileMaker
 * Pro 26.0.2 and 26.0.3: `"x„ & Upper ( „y, z„ ) & ＂w＂` is
 * `"x" & Upper ( "y, z" ) & "w"`, `"a＼"b"` is `a"b`). The splitters knew only the
 * first three delimiters and the ASCII backslash, so
 * `Set Variable [ $x ; Value: „a ; b„ ]` split at the `;` inside the literal and
 * `"a＼"b ; c"` closed early. Mirrors agent/scripts/test_calc_literal_delimiters.py.
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { hrToXml, loadCatalog } from '@/converter/hr-to-xml';
import { parseLine } from '@/converter/parser';
import {
  decodeWholeCalcLiteral,
  hrCalcCommentMayOpenAfter,
  isUnescapedCalcQuote,
  quoteCalcLiteral,
  skipCalcLiteral,
} from '@/converter/calc-literal';
import { groupQuoteValue } from '@/converter/catalog-grammar';
import type { StepCatalogEntry } from '@/converter/catalog-types';

const REPO_ROOT = path.resolve(__dirname, '..', '..');
const rawCatalog = JSON.parse(
  readFileSync(path.join(REPO_ROOT, 'agent', 'catalogs', 'step-catalog-en.json'), 'utf-8'),
);
const entries: StepCatalogEntry[] = rawCatalog.steps ?? rawCatalog;
loadCatalog(entries);

const DELIMS = '"“”„‟＂';
const calcs = (xml: string) => [...xml.matchAll(/<!\[CDATA\[([\s\S]*?)\]\]>/g)].map((m) => m[1]);
const params = (hr: string) => parseLine(hr, 1).params;

describe('calculation literal delimiters and backslash forms', () => {
  it('reads every delimiter pair as one literal', () => {
    for (const o of DELIMS) {
      for (const c of DELIMS) {
        expect(decodeWholeCalcLiteral(`${o}a ; b${c}`)).toBe('a ; b');
        expect(params(`Set Variable [ $x ; Value: ${o}a ; b${c} ]`)).toEqual(['$x', `Value: ${o}a ; b${c}`]);
      }
    }
  });

  it('opens no literal on other quote characters', () => {
    for (const ch of '‚‘’«»「」〝〞〟＇') expect(isUnescapedCalcQuote(`${ch}a${ch}`, 0)).toBe(false);
  });

  it('escapes with every backslash form', () => {
    expect(decodeWholeCalcLiteral('"a＼"b"')).toBe('a"b');
    expect(decodeWholeCalcLiteral('"a﹨"b"')).toBe('a"b');
    expect(decodeWholeCalcLiteral('"a＼＼b"')).toBe('a＼b');
    expect(decodeWholeCalcLiteral('"a\\＼b"')).toBe('a＼b');
    expect(decodeWholeCalcLiteral('"a＼¶b"')).toBe('a¶b');
    expect(decodeWholeCalcLiteral('"a\\„b"')).toBe('a„b');
    expect(decodeWholeCalcLiteral('"a＼nb"')).toBe('a＼nb');
    expect(decodeWholeCalcLiteral('"a"＂b"')).toBe('a＂b');
    for (const bs of '＼﹨') {
      expect(params(`Set Variable [ $x ; Value: "a${bs}"b ; c" ]`)).toEqual(['$x', `Value: "a${bs}"b ; c"`]);
    }
    expect(params('Set Variable [ $x ; Value: "a\\＼" ; 2 ]')).toEqual(['$x', 'Value: "a\\＼"', '2']);
  });

  it('quotes values that decode back exactly', () => {
    for (const v of ['a„b', 'a＂b', 'a‟b', 'a＼', 'a﹨„', 'x＼＼y', 'q\\"', 'plain＼z']) {
      expect(skipCalcLiteral(quoteCalcLiteral(v), 0).decoded).toBe(v);
      const g = groupQuoteValue(v);
      expect(g === v ? v : skipCalcLiteral(g, 0).decoded).toBe(v);
    }
    expect(quoteCalcLiteral('plain＼z')).toBe('“plain＼z”');
  });

  it('opens a comment after the new delimiters', () => {
    for (const q of '„‟＂') expect(hrCalcCommentMayOpenAfter(`${q}a${q}／＊ c ＊／`, 3)).toBe(true);
  });

  it('emits one calculation', () => {
    const calc = '„a ; b„ & ＂x＂ & "a＼"b" ／＊ c ; d ＊／';
    expect(calcs(hrToXml(`Set Variable [ $x ; Value: ${calc} ]`).xml)).toEqual([calc]);
    expect(calcs(hrToXml(`Show Custom Dialog [ Title: ＂T ; 1＂ ; Message: ${calc} ]`).xml).slice(0, 2)).toEqual([
      '＂T ; 1＂',
      calc,
    ]);
  });
});
