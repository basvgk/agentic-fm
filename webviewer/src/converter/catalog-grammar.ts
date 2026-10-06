/**
 * catalog-grammar.ts — the shared catalog grammar engine (TS port).
 *
 * A faithful TypeScript port of agent/scripts/catalog_grammar.py's XML→HR path:
 * one function per param type computes that param's HR fragment, and an
 * orchestrator renders the fragments in hrSlot order with discriminator /
 * visibility / label handling. Kept deliberately parallel to the Python module so
 * a facet added to one port is obviously missing from the other (see the plan's
 * "Python↔TS structural parity" risk).
 *
 * Like the reference converter (and the Python port), this reads directly from the
 * parsed fmxmlsnippet <Step> DOM element rather than through an intermediate
 * struct, so the output is byte-faithful to the proven grammar. Element traversal
 * uses ElementTree-`find` semantics — **direct children only** — never
 * `querySelector` (which would match descendants); see `findChild`/`findChildren`.
 *
 * The reference's per-param HR computation maps here to `computeParamHr` and its
 * whole-step renderer to `renderStepHr`.
 * Control-flow steps are NOT rendered here — they stay hand-coded in
 * steps/control.ts (the sanctioned exception), exactly as snippet_to_hr.py keeps
 * them hand-coded.
 */

import type { StepCatalogEntry } from './catalog-types';

// ---------------------------------------------------------------------------
// DOM helpers — ElementTree `.find` / `.findall` / `.text` semantics over a
// spec-compliant XML DOM (native DOMParser in the browser, linkedom in tests).
// Direct-child navigation only, matching Python's xml.etree.ElementTree.
// ---------------------------------------------------------------------------

/** First direct child element named `name` (ElementTree `parent.find(name)`). */
function findChild(parent: Element | null, name: string): Element | null {
  if (!parent) return null;
  for (const c of Array.from(parent.children)) {
    if (c.tagName === name) return c;
  }
  return null;
}

/** All direct child elements named `name` (ElementTree `parent.findall(name)`). */
function findChildren(parent: Element | null, name: string): Element[] {
  if (!parent) return [];
  return Array.from(parent.children).filter((c) => c.tagName === name);
}

/**
 * First direct child element named `name` whose attribute `attr` equals `value`
 * (ElementTree `parent.find("name[@attr='value']")`). Locates one of several
 * same-element typed children by its discriminator attribute — the typed-child
 * grammar (a <Field type="Messages"> vs <Field type="ToolCalls"> sibling).
 */
function findChildByAttr(
  parent: Element | null,
  name: string,
  attr: string,
  value: string,
): Element | null {
  if (!parent) return null;
  for (const c of Array.from(parent.children)) {
    if (c.tagName === name && (c.getAttribute(attr) ?? '') === value) return c;
  }
  return null;
}

/**
 * Text directly inside `el` (ElementTree `.text`). Every text-bearing element in
 * the catalog grammar (Calculation, Text, Name, UniversalPathList, field text) is
 * a leaf, so `textContent` — which decodes entities and includes CDATA content in
 * both native DOM and linkedom — is equivalent to ElementTree's leading `.text`.
 */
function elemText(el: Element | null): string {
  return el ? (el.textContent ?? '') : '';
}

/** ElementTree `_child_text`: text of the direct child named `name`. */
function childText(parent: Element | null, name: string): string {
  return elemText(findChild(parent, name));
}

/** ElementTree `_child_attr`: attribute `attr` of the direct child named `name`. */
function childAttr(parent: Element | null, name: string, attr: string): string {
  const c = findChild(parent, name);
  return c ? (c.getAttribute(attr) ?? '') : '';
}

/**
 * Find a direct child by its canonical `name`; if absent and the name carries
 * declared aliases, retry each legacy synonym in order (element-alias grammar).
 * Mirrors Python `_aliased_child`.
 */
function aliasedChild(
  parent: Element | null,
  name: string,
  aliases?: Record<string, string[]>,
): Element | null {
  if (parent === null) return null;
  const c = findChild(parent, name);
  if (c !== null) return c;
  for (const syn of aliases?.[name] ?? []) {
    const s = findChild(parent, syn);
    if (s !== null) return s;
  }
  return null;
}

/** Follow a '/'-delimited direct-child path from `step` (ElementTree find path),
 * resolving each segment alias-tolerantly (element-alias grammar). */
function descendPath(
  step: Element | null,
  path: string,
  aliases?: Record<string, string[]>,
): Element | null {
  let n: Element | null = step;
  for (const seg of path.split('/')) {
    if (!seg) continue;
    if (n === null) return null;
    n = aliasedChild(n, seg, aliases);
  }
  return n;
}

// ---------------------------------------------------------------------------
// String helpers
// ---------------------------------------------------------------------------
function ciEquals(a: string, b: string): boolean {
  return a.toLowerCase() === b.toLowerCase();
}

/** G11 'Elem/@attr' notation → [true, 'Elem', 'attr']; else [false, '', '']. */
function splitElementAttr(xmlElement: string): [boolean, string, string] {
  const pos = xmlElement.indexOf('/@');
  if (pos === -1) return [false, '', ''];
  return [true, xmlElement.slice(0, pos), xmlElement.slice(pos + 2)];
}

function joinWithComma(items: string[]): string {
  return items.join(', ');
}

function needsGroupQuote(v: string): boolean {
  if (!v) return false;
  const ws = ' \t\n\r';
  if (ws.includes(v[0]) || ws.includes(v[v.length - 1])) return true;
  return v.includes(',') || v.includes('"');
}

function groupQuoteValue(v: string): string {
  if (!needsGroupQuote(v)) return v;
  return '"' + v.replace(/"/g, '""') + '"';
}

// ---------------------------------------------------------------------------
// Grammar model — mirrors Python catalog_grammar.py's StepParam / CatalogEntry:
// typed fields for the common facets + `raw` for the untyped long tail (bitmask
// tables, attrGroup/repeat field specs, entryElement/childElement, …).
// ---------------------------------------------------------------------------

/** One branch of a `discriminatorValues` map (mirrors DiscriminatorBranch). */
interface DiscriminatorBranch {
  hrToken: string | null;
  labeled: boolean | null;
  reveal: string[];
}

interface VisibleWhenRule {
  param: string;
  values: string[];
}

interface HrLabelRule {
  param: string;
  values: string[];
  hrLabel: string | null;
}

/** Faithful counterpart of Python's StepParam (typed fields + raw dict). */
export interface GrammarParam {
  xmlElement: string;
  type: string;
  hrLabel: string | null;
  required: boolean;
  xmlAttr: string | null;
  wrapperElement: string | null;
  parentElement: string | null;
  defaultValue: string | null;
  hrEnumValues: Record<string, string>;
  hrHiddenValues: string[];
  invertedHr: boolean | null;
  enumStyle: string | null;
  flagStyle: boolean | null;
  hrSlot: number | null;
  hrHidden: boolean | null;
  hrBare: boolean | null;
  // Inverse of hrBare: render a calc/field/script value WITH its hrLabel prefix and
  // match it by that label, even though those types are bare/positional by default.
  // FileMaker labels the same value type per step (Perform Script bare; Configure
  // Region Monitor Script's `Script: "…"`). Generic; needs a non-empty hrLabel.
  hrLabeled: boolean | null;
  omitWhenEmpty: boolean | null;
  discriminator: string | null;
  discriminatorValues: Record<string, DiscriminatorBranch>;
  visibleWhen: VisibleWhenRule | null;
  hrLabelWhen: HrLabelRule[];
  /** The full source object, for the untyped facet tail (matches Python `raw`). */
  raw: Record<string, unknown>;
}

export interface GrammarEntry {
  name: string;
  /** FileMaker's universal step-type id (the `<Step id="N">` constant), 0 if unknown. */
  id: number;
  params: GrammarParam[];
  /** Block role (open/close/middle/inner) for control-flow indentation, or null. */
  blockRole: string | null;
  /**
   * Element-alias grammar (mirrors Python `CatalogEntry.element_aliases`): map a
   * canonical element name (the last path segment) to its declared legacy
   * synonyms, so a drifted step reads either spelling (e.g. FileMaker serializes
   * Configure AI Account's wrapper as the typo'd `<SetLLMAccout>`/`<AccoutName>`
   * while the catalog names them `SetLLMAccount`/`AccountName`). Built at load
   * from each param's `wrapperElementAliases` / `parentElementAliases`.
   */
  elementAliases: Record<string, string[]>;
}

/**
 * Control-flow indentation for a step, derived from its catalog `blockPair` role
 * (replacing the former hard-coded name sets in xml-to-hr.ts):
 *   open   → indent the following lines (openAfter)
 *   close  → outdent this line (closeBefore)
 *   middle → both (Else / Else If)
 *   inner / none → neither (Exit Loop If, Revert Transaction, every data step)
 * This mirrors the (close_before, open_after) tuples snippet_to_hr.py hand-codes,
 * and additionally covers Open/Commit Transaction blocks via the same rule.
 */
export function blockIndent(name: string): { closeBefore: boolean; openAfter: boolean } {
  const role = grammarRegistry.get(name)?.blockRole ?? null;
  return {
    closeBefore: role === 'close' || role === 'middle',
    openAfter: role === 'open' || role === 'middle',
  };
}

/**
 * The param-key rule (matches the reference converter and Python `param_key`): a
 * `namedCalc` param keys off its `wrapperElement`; any other param off its
 * `xmlElement`.
 */
export function paramKey(p: GrammarParam): string {
  if (p.type === 'namedCalc' && p.wrapperElement) return p.wrapperElement;
  return p.xmlElement;
}

function buildDiscriminatorBranch(d: Record<string, unknown>): DiscriminatorBranch {
  return {
    hrToken: (d.hrToken as string) ?? null,
    labeled: (d.labeled as boolean) ?? null,
    reveal: Array.isArray(d.reveal) ? (d.reveal as string[]) : [],
  };
}

function buildParam(d: Record<string, unknown>): GrammarParam {
  const dvRaw = (d.discriminatorValues as Record<string, Record<string, unknown>>) ?? {};
  const discriminatorValues: Record<string, DiscriminatorBranch> = {};
  for (const [k, v] of Object.entries(dvRaw)) {
    discriminatorValues[k] = buildDiscriminatorBranch(v);
  }
  const vw = d.visibleWhen as Record<string, unknown> | undefined;
  const hlw = (d.hrLabelWhen as Record<string, unknown>[]) ?? [];
  // `flagBoolean` is normalized to `boolean` at load, exactly as the reference
  // converter does — the engine only has a `boolean` branch, so without this ~21
  // flag params (Paste, Sort Records, Save as*, …) would render as nothing. The
  // original label survives in `raw.type`. (This was the one real P6.2 port bug.)
  const rawType = (d.type as string) ?? '';
  const type = rawType === 'flagBoolean' ? 'boolean' : rawType;
  return {
    xmlElement: (d.xmlElement as string) ?? '',
    type,
    hrLabel: (d.hrLabel as string) ?? null,
    required: Boolean(d.required),
    xmlAttr: (d.xmlAttr as string) ?? null,
    wrapperElement: (d.wrapperElement as string) ?? null,
    parentElement: (d.parentElement as string) ?? null,
    defaultValue: (d.defaultValue as string) ?? null,
    hrEnumValues: (d.hrEnumValues as Record<string, string>) ?? {},
    hrHiddenValues: (d.hrHiddenValues as string[]) ?? [],
    invertedHr: (d.invertedHr as boolean) ?? null,
    enumStyle: (d.enumStyle as string) ?? null,
    flagStyle: (d.flagStyle as boolean) ?? null,
    hrSlot: typeof d.hrSlot === 'number' ? (d.hrSlot as number) : null,
    hrHidden: (d.hrHidden as boolean) ?? null,
    hrBare: (d.hrBare as boolean) ?? null,
    hrLabeled: (d.hrLabeled as boolean) ?? null,
    omitWhenEmpty: (d.omitWhenEmpty as boolean) ?? null,
    discriminator: (d.discriminator as string) ?? null,
    discriminatorValues,
    visibleWhen: vw ? { param: vw.param as string, values: (vw.values as string[]) ?? [] } : null,
    hrLabelWhen: hlw.map((x) => ({
      param: x.param as string,
      values: (x.values as string[]) ?? [],
      hrLabel: (x.hrLabel as string) ?? null,
    })),
    raw: d,
  };
}

function buildEntry(entry: StepCatalogEntry): GrammarEntry {
  const params = (entry.params as unknown as Record<string, unknown>[]) ?? [];
  // Element-alias grammar: gather each param's wrapper/parent synonyms, keyed by
  // the canonical element's last path segment (mirrors Python `from_dict`).
  const elementAliases: Record<string, string[]> = {};
  for (const p of params) {
    for (const [aliasKey, canonical] of [
      ['wrapperElementAliases', p.wrapperElement],
      ['parentElementAliases', p.parentElement],
    ] as const) {
      const syns = p[aliasKey];
      if (!canonical || !Array.isArray(syns)) continue;
      const seg = String(canonical).split('/').pop() as string;
      const bucket = (elementAliases[seg] ??= []);
      for (const s of syns) {
        if (typeof s === 'string' && !bucket.includes(s)) bucket.push(s);
      }
    }
  }
  return {
    name: entry.name,
    id: entry.id ?? 0,
    params: params.map(buildParam),
    blockRole: entry.blockPair?.role ?? null,
    elementAliases,
  };
}

// ---------------------------------------------------------------------------
// Grammar registry — populated once from the fetched catalog (see loadCatalog in
// hr-to-xml.ts). xmlToHr reads step rules from here.
// ---------------------------------------------------------------------------
const grammarRegistry = new Map<string, GrammarEntry>();

/** Build grammar entries from the catalog and register them (idempotent per call). */
export function initGrammar(catalog: StepCatalogEntry[]): void {
  for (const entry of catalog) {
    grammarRegistry.set(entry.name, buildEntry(entry));
  }
}

export function getGrammarEntry(name: string): GrammarEntry | undefined {
  return grammarRegistry.get(name);
}

/**
 * FileMaker's universal step-type id for `name` (the `<Step id="N">` constant),
 * resolved from the loaded catalog — 0 when the catalog isn't loaded or the name
 * is unknown. Mirrors the reference converter's own step-id lookup; shared so the
 * HR→XML emit path and control-flow hand-coders write the same real id FM does.
 */
export function resolveStepId(name: string): number {
  return grammarRegistry.get(name)?.id ?? 0;
}

// ---------------------------------------------------------------------------
// Discriminator / visibility predicates (mirror the reference + Python port)
// ---------------------------------------------------------------------------
export function isGoverningDiscriminator(param: GrammarParam): boolean {
  return param.type === 'enum' && Object.keys(param.discriminatorValues).length > 0;
}

export function isDrivenDiscriminator(entry: GrammarEntry, param: GrammarParam): boolean {
  if (!param.xmlElement) return false;
  return entry.params.some((q) => q.type === 'layout' && q.discriminator === param.xmlElement);
}

/** Whether governing discriminator `discrim`'s XML `value` reveals companion `elem`. */
export function valueRevealsCompanion(
  discrim: GrammarParam,
  value: string,
  elem: string,
): boolean {
  const branch = discrim.discriminatorValues[value];
  if (branch === undefined) return false;
  return branch.reveal.includes(elem);
}

/**
 * Every label a param's HR token may carry — its base hrLabel plus any
 * `hrLabelWhen` variant labels — longest first (lexicographic tiebreak) with
 * duplicates removed. Ports the reference converter's candidate-label rule; the HR parse
 * matcher tries each so a variant-labeled value round-trips.
 */
export function candidateHrLabels(param: GrammarParam): string[] {
  const labels: string[] = [];
  if (param.hrLabel) labels.push(param.hrLabel);
  for (const v of param.hrLabelWhen) if (v.hrLabel) labels.push(v.hrLabel);
  labels.sort((a, b) => (a.length !== b.length ? b.length - a.length : a < b ? -1 : a > b ? 1 : 0));
  return labels.filter((l, i) => i === 0 || l !== labels[i - 1]);
}

export function governingDiscriminatorFor(
  entry: GrammarEntry,
  companion: GrammarParam,
): GrammarParam | null {
  if (!companion.xmlElement) return null;
  const ck = paramKey(companion);
  for (const p of entry.params) {
    if (p === companion || !isGoverningDiscriminator(p)) continue;
    for (const branch of Object.values(p.discriminatorValues)) {
      if (branch.reveal.includes(ck)) return p;
    }
  }
  return null;
}

function readEnumRawValue(
  step: Element,
  p: GrammarParam,
  aliases?: Record<string, string[]>,
): string {
  const base = !p.parentElement ? step : descendPath(step, p.parentElement, aliases);
  if (p.enumStyle === 'text') return childText(base, p.xmlElement);
  const attr = p.xmlAttr || 'value';
  return childAttr(base, p.xmlElement, attr);
}

function effectiveHrLabel(entry: GrammarEntry, step: Element, param: GrammarParam): string {
  for (const variant of param.hrLabelWhen) {
    for (const q of entry.params) {
      if (paramKey(q) !== variant.param) continue;
      const v = readEnumRawValue(step, q, entry.elementAliases) || (q.defaultValue || '');
      if (variant.values.includes(v)) return variant.hrLabel || '';
      break;
    }
  }
  return param.hrLabel || '';
}

function paramVisible(entry: GrammarEntry, step: Element, param: GrammarParam): boolean {
  const vw = param.visibleWhen;
  if (vw === null || !vw.param) return true;
  for (const q of entry.params) {
    if (paramKey(q) !== vw.param) continue;
    const v = readEnumRawValue(step, q, entry.elementAliases) || (q.defaultValue || '');
    return vw.values.includes(v);
  }
  return true;
}

/** Indices in HR render order — catalog order unless some param sets hrSlot. */
export function hrParamOrder(entry: GrammarEntry): number[] {
  const order = entry.params.map((_, i) => i);
  if (!entry.params.some((p) => p.hrSlot !== null && p.hrSlot >= 0)) return order;
  // Stable sort by hrSlot (falling back to catalog index) — mirrors Python's
  // stable `sorted`; JS Array.sort is stable per spec (ES2019+).
  return order.sort((a, b) => {
    const sa = entry.params[a].hrSlot;
    const sb = entry.params[b].hrSlot;
    const ka = sa !== null && sa >= 0 ? sa : a;
    const kb = sb !== null && sb >= 0 ? sb : b;
    return ka - kb;
  });
}

/**
 * Append FileMaker's `[N]` repetition subscript to a field/variable ref.
 *
 * FileMaker serializes a repetition as `repetition="N"` on the `<Field>`
 * (`<Field table="T" id="1" repetition="2" name="F"/>`, or
 * `<Field repetition="2">$var</Field>`) and writes the attribute only for N > 1;
 * its Script Workspace line shows `T::F[2]` / `$var[2]`. Repetition 1 is the
 * default and carries no subscript.
 */
function withRepetitionSuffix(ref: string, fld: Element): string {
  const rep = parseInt(fld.getAttribute('repetition') ?? '', 10);
  return ref && rep > 1 ? ref + '[' + rep + ']' : ref;
}

// ---------------------------------------------------------------------------
// Group / repeat / list renderers
// ---------------------------------------------------------------------------
function renderGroupElement(node: Element, fields: Record<string, unknown>[]): string {
  const parts: string[] = [];
  for (const f of fields) {
    const kind = (f.kind as string) ?? '';
    const key = (f.key as string) ?? '';
    if (kind === 'attr') {
      const a = node.getAttribute((f.xmlAttr as string) ?? '');
      if (a !== null) parts.push(key + '=' + groupQuoteValue(a));
    } else if (kind === 'text') {
      const child = findChild(node, (f.childElement as string) ?? '');
      if (child !== null) parts.push(key + '=' + groupQuoteValue(elemText(child)));
    } else if (kind === 'calc') {
      const childEl = (f.childElement as string) ?? '';
      if (!childEl) {
        const c = findChild(node, 'Calculation');
        if (c !== null) parts.push(key + '=' + elemText(c));
      } else {
        const child = findChild(node, childEl);
        if (child !== null) parts.push(key + '=' + childText(child, 'Calculation'));
      }
    } else if (kind === 'field') {
      const fld = findChild(node, 'Field');
      if (fld !== null) {
        const table = fld.getAttribute('table') ?? '';
        const name = fld.getAttribute('name') ?? '';
        if (name) parts.push(key + '=' + withRepetitionSuffix(!table ? name : table + '::' + name, fld));
      }
    } else if (kind === 'script') {
      const sc = findChild(node, (f.element as string) ?? '');
      if (sc !== null) {
        const name = sc.getAttribute('name') ?? '';
        if (name) parts.push(key + '=' + groupQuoteValue(name));
      }
    } else if (kind === 'fieldOrVariable') {
      const fld = findChild(node, 'Field');
      if (fld !== null) {
        const text = elemText(fld).trim();
        if (text) {
          parts.push(key + '=' + groupQuoteValue(withRepetitionSuffix(text, fld)));
        } else {
          const table = fld.getAttribute('table') ?? '';
          const name = fld.getAttribute('name') ?? '';
          if (name) {
            const ref = !table ? name : table + '::' + name;
            parts.push(key + '=' + groupQuoteValue(withRepetitionSuffix(ref, fld)));
          }
        }
      }
    } else if (kind === 'group') {
      const sub = findChild(node, (f.element as string) ?? '');
      if (sub !== null) {
        parts.push(
          key + '=(' + renderGroupElement(sub, (f.fields as Record<string, unknown>[]) ?? []) + ')',
        );
      }
    }
  }
  return joinWithComma(parts);
}

function renderRepeatGroup(container: Element, param: GrammarParam): string {
  const entryEl = (param.raw.entryElement as string) ?? '';
  const fields = (param.raw.fields as Record<string, unknown>[]) ?? [];
  const entries = findChildren(container, entryEl).map((e) => renderGroupElement(e, fields));
  return entries.join(' | ');
}

function groupUnquote(v: string): string {
  if (v.length < 2 || v[0] !== '"' || v[v.length - 1] !== '"') return v;
  return v.slice(1, -1).replace(/""/g, '"');
}

/**
 * `hrPositionalKey`: FileMaker's own form for a repeatGroup -- one BARE token per
 * non-empty entry (that entry's positional field), joined ' ; ' (Show Custom
 * Dialog `... ; $a ; Invoices::Number`). `null` when that form would lose
 * information (another entry field off its default, an empty entry before a
 * filled one, or an entry count re-emit would not reproduce), so the caller keeps
 * the labeled body form. Mirrors the reference converter.
 */
function renderRepeatGroupPositional(container: Element, param: GrammarParam): string | null {
  const key = (param.raw.hrPositionalKey as string) ?? '';
  const fields = (param.raw.fields as Record<string, unknown>[]) ?? [];
  const pos = fields.find((f) => f.key === key);
  if (!pos) return null;
  const tokens: string[] = [];
  let count = 0;
  let sawEmpty = false;
  for (const e of findChildren(container, (param.raw.entryElement as string) ?? '')) {
    count++;
    for (const f of fields) {
      if (f === pos) continue;
      const got = renderGroupElement(e, [f]);
      const dflt = f.kind === 'attr'
        ? ((f.key as string) ?? '') + '=' + groupQuoteValue((f.defaultValue as string) ?? '')
        : '';
      if (got !== dflt) return null;
    }
    const body = renderGroupElement(e, [pos]);
    const prefix = key + '=';
    const v = body.startsWith(prefix) ? groupUnquote(body.slice(prefix.length)) : '';
    if (!v.trim()) { sawEmpty = true; continue; }
    if (sawEmpty) return null;
    tokens.push(v);
  }
  if (count === 0) return '';
  if (tokens.length === 0) return null;
  const rc = Number(param.raw.repeatCount ?? 0) || 0;
  const expected = rc > 0 ? Math.max(rc, tokens.length) : tokens.length;
  if (count !== expected) return null;
  return tokens.join(' ; ');
}

function renderFieldList(container: Element, param: GrammarParam): string {
  const entryEl = (param.raw.entryElement as string) ?? '';
  const entryAttr = (param.raw.entryAttr as string) ?? '';
  const fieldWrapper = (param.raw.fieldWrapper as string) ?? '';
  const tokens: string[] = [];

  const emit = (entryNode: Element | null, fieldNode: Element | null): void => {
    if (fieldNode === null) return;
    const table = fieldNode.getAttribute('table') ?? '';
    const name = fieldNode.getAttribute('name') ?? '';
    const fieldref = !name ? '' : !table ? name : table + '::' + name;
    let token = groupQuoteValue(fieldref);
    if (entryAttr) {
      const attrNode = !entryEl ? fieldNode : entryNode;
      if (attrNode !== null) token += '=' + (attrNode.getAttribute(entryAttr) ?? '');
    }
    tokens.push(token);
  };

  if (entryEl) {
    for (const e of findChildren(container, entryEl)) {
      let fld: Element | null;
      if (fieldWrapper) {
        const w = findChild(e, fieldWrapper);
        fld = w !== null ? findChild(w, 'Field') : null;
      } else {
        fld = findChild(e, 'Field');
      }
      emit(e, fld);
    }
  } else {
    for (const fld of findChildren(container, 'Field')) emit(null, fld);
  }
  return tokens.join(', ');
}

// ---------------------------------------------------------------------------
// Bitmask helpers
// ---------------------------------------------------------------------------
function bitmaskStyleByXml(
  param: GrammarParam,
  v: string,
): Record<string, unknown> | null {
  for (const s of (param.raw.bitmaskStyles as Record<string, unknown>[]) ?? []) {
    if (s.xmlValue === v) return s;
  }
  return null;
}

function bitmaskMaskForFlags(param: GrammarParam, labels: string[]): number {
  let m = 0;
  for (const lbl of labels) {
    for (const f of (param.raw.bitmaskFlags as Record<string, unknown>[]) ?? []) {
      if (ciEquals((f.hrLabel as string) ?? '', lbl)) {
        m |= (f.bit as number) ?? 0;
        break;
      }
    }
  }
  return m;
}

// ---------------------------------------------------------------------------
// Per-param HR fragment
// ---------------------------------------------------------------------------
/** Compute one param's HR fragment ('' = no token), as the reference does. */
export function computeParamHr(entry: GrammarEntry, step: Element, param: GrammarParam): string {
  let val = '';
  let base = !param.parentElement ? step : descendPath(step, param.parentElement, entry.elementAliases);
  if (base === null) base = step; // a missing wrapper reads nothing; keep base usable
  const [isElemAttr, g11Elem, g11Attr] = splitElementAttr(param.xmlElement);
  const label = param.hrLabel || '';
  const ptype = param.type;

  if (ptype === 'boolean') {
    const battr = isElemAttr ? g11Attr : param.xmlAttr || 'state';
    const belem = isElemAttr ? g11Elem : param.xmlElement;
    const state = childAttr(base, belem, battr);
    if (state) {
      let stateTrue = state === 'True';
      if (param.invertedHr) stateTrue = !stateTrue;
      if (param.flagStyle) {
        if (stateTrue && label) val = label;
      } else if (Object.keys(param.hrEnumValues).length > 0) {
        val = param.hrEnumValues[state] ?? (stateTrue ? 'On' : 'Off');
        if (label) val = label + ': ' + val;
      } else {
        val = stateTrue ? 'On' : 'Off';
        if (label) val = label + ': ' + val;
      }
    }
  } else if (ptype === 'enum' && isDrivenDiscriminator(entry, param)) {
    // silent companion of a layout param
  } else if (ptype === 'enum') {
    if (param.enumStyle === 'text') {
      val = childText(base, param.xmlElement);
    } else {
      const eattr = isElemAttr ? g11Attr : param.xmlAttr || 'value';
      const eelem = isElemAttr ? g11Elem : param.xmlElement;
      val = childAttr(base, eelem, eattr);
    }
    // P7.2: FileMaker renders no token at all for some of an enum's values -- it
    // shows the companion the value reveals, in that companion's own slot
    // (`Go to Record/Request/Page [ With dialog: Off ; 1 ]` is the ByCalculation
    // form, and `1` is the row calculation, not the location).
    if (param.hrHiddenValues.includes(val || param.defaultValue || '\u0000')) {
      val = '';
    }
    if (!param.flagStyle && Object.keys(param.hrEnumValues).length > 0) {
      const mapped = param.hrEnumValues[val];
      if (mapped) val = mapped;
    }
    if (param.flagStyle) {
      val = val && val !== (param.defaultValue || '') && label ? label : '';
    } else if (val && label) {
      val = label + ': ' + val;
    }
  } else if (ptype === 'calculation') {
    val = childText(base, 'Calculation');
    if (val && param.omitWhenEmpty && label) val = label + ': ' + val;
  } else if (ptype === 'attrGroup') {
    const groupNode = findChild(base, param.xmlElement);
    if (groupNode !== null) {
      const inner = renderGroupElement(groupNode, (param.raw.fields as Record<string, unknown>[]) ?? []);
      val = !label ? inner : label + ': ' + inner;
    }
  } else if (ptype === 'bitmaskGroup') {
    const g = findChild(base, param.xmlElement);
    const styles = (param.raw.bitmaskStyles as Record<string, unknown>[]) ?? [];
    if (g !== null && styles.length > 0) {
      const xmlStyle = g.getAttribute((param.raw.bitmaskStyleAttr as string) ?? '') ?? '';
      const st = bitmaskStyleByXml(param, xmlStyle) ?? styles[0];
      let chrome = 0;
      for (const f of (param.raw.bitmaskFlags as Record<string, unknown>[]) ?? []) {
        const yn = g.getAttribute((f.xmlAttr as string) ?? '') ?? 'No';
        if (ciEquals(yn, 'Yes')) chrome |= (f.bit as number) ?? 0;
      }
      chrome &= bitmaskMaskForFlags(param, (st.legalFlags as string[]) ?? []);
      const parts: string[] = [];
      if (label) parts.push(label + ': ' + ((st.hrToken as string) ?? ''));
      if (chrome !== bitmaskMaskForFlags(param, (st.defaultFlags as string[]) ?? [])) {
        const lst = ((param.raw.bitmaskFlags as Record<string, unknown>[]) ?? [])
          .filter((f) => chrome & ((f.bit as number) ?? 0))
          .map((f) => (f.hrLabel as string) ?? '');
        const controlsLabel = (param.raw.hrControlsLabel as string) ?? '';
        parts.push(controlsLabel + ': ' + (lst.length > 0 ? lst.join(', ') : 'None'));
      }
      val = parts.join(' ; ');
    }
  } else if (ptype === 'repeatGroup') {
    const container = findChild(base, param.xmlElement);
    const positional = container !== null && param.raw.hrPositionalKey
      ? renderRepeatGroupPositional(container, param) : null;
    if (positional !== null) {
      val = positional; // FileMaker's own bare form (lossless here)
    } else if (container !== null) {
      let inner = renderRepeatGroup(container, param);
      // FileMaker's default content prints no token; emit restores it.
      const dflt = (param.raw.hrDefault as string) ?? '';
      if (dflt && inner === dflt) inner = '';
      if (inner) val = !label ? inner : label + ': ' + inner;
    }
  } else if (ptype === 'fieldList') {
    const container = findChild(base, param.xmlElement);
    if (container !== null) {
      const inner = renderFieldList(container, param);
      if (inner) val = !label ? inner : label + ': ' + inner;
    }
  } else if (ptype === 'namedCalc') {
    const wrapper = param.wrapperElement || param.xmlElement;
    // Element-alias grammar: match the wrapper by its canonical name, falling
    // back to any declared legacy synonym (e.g. AccoutName). Mirrors Python.
    const wnode = aliasedChild(base, wrapper, entry.elementAliases);
    val = wnode !== null ? childText(wnode, 'Calculation') : '';
    // hrBare params (Show Custom Dialog's Title/Message) print positionally
    // with no label, mirroring FileMaker; every other namedCalc keeps its label.
    if (val && !param.hrBare) {
      const lbl = effectiveHrLabel(entry, step, param);
      if (lbl) val = lbl + ': ' + val;
    }
  } else if (ptype === 'parametersList') {
    const wrapperName = param.xmlElement || 'Parameters';
    const wrapper = findChild(base, wrapperName);
    if (wrapper !== null) {
      const items = findChildren(wrapper, 'P')
        .map((p) => childText(p, 'Calculation'))
        .filter((t) => t);
      if (items.length > 0) {
        val = joinWithComma(items);
        if (label) val = label + ': ' + val;
      }
    }
  } else if (ptype === 'findRequests') {
    const query = findChild(base, 'Query');
    if (query !== null) {
      const rows: string[] = [];
      for (const rr of findChildren(query, 'RequestRow')) {
        const op = rr.getAttribute('operation') ?? '';
        const crits: string[] = [];
        for (const cr of findChildren(rr, 'Criteria')) {
          const fld = findChild(cr, 'Field');
          const table = fld !== null ? fld.getAttribute('table') ?? '' : '';
          const name = fld !== null ? fld.getAttribute('name') ?? '' : '';
          const text = childText(cr, 'Text');
          let fieldref = '';
          if (name) fieldref = !table ? name : table + '::' + name;
          crits.push(!fieldref ? text : fieldref + ': ' + text);
        }
        let joined = crits.join(' & ');
        if (op === 'Exclude') joined = 'Omit ' + joined;
        rows.push(joined);
      }
      val = rows.join(' | ');
      if (val && label) val = label + ': ' + val;
    }
  } else if (ptype === 'fieldOrVariable') {
    // A typed same-element child (typeAttr/typeValue) is located by its
    // discriminator attribute rather than by position, so two typed <Field>
    // siblings under one wrapper never read each other's node.
    const typeAttr = (param.raw.typeAttr as string) ?? '';
    let fieldNode: Element | null;
    if (typeAttr) {
      fieldNode = findChildByAttr(base, 'Field', typeAttr, (param.raw.typeValue as string) ?? '');
    } else {
      fieldNode = findChild(base, param.xmlElement);
      if (fieldNode === null) fieldNode = findChild(base, 'Field');
    }
    if (fieldNode !== null) {
      const table = fieldNode.getAttribute('table') ?? '';
      const name = fieldNode.getAttribute('name') ?? '';
      const text = elemText(fieldNode);
      if (text && text[0] === '$') val = text;
      else if (name) val = !table ? name : table + '::' + name;
      else if (text) val = text;
      val = withRepetitionSuffix(val, fieldNode);
      if (val && label) val = label + ': ' + val;
    }
  } else if (ptype === 'flagElement') {
    if (findChild(base, param.xmlElement) !== null && label) val = label;
  } else if (ptype === 'calc') {
    val = childText(base, 'Calculation');
    // hrLabeled: FileMaker labels this calc for some steps (inverse of bare).
    if (val && param.hrLabeled && label) val = label + ': ' + val;
  } else if (ptype === 'field') {
    const typeAttr = (param.raw.typeAttr as string) ?? '';
    let fieldNode: Element | null;
    if (typeAttr) {
      fieldNode = findChildByAttr(base, 'Field', typeAttr, (param.raw.typeValue as string) ?? '');
    } else {
      fieldNode = findChild(base, param.xmlElement);
      if (fieldNode === null) fieldNode = findChild(base, 'Field');
    }
    if (fieldNode !== null) {
      const table = fieldNode.getAttribute('table') ?? '';
      const name = fieldNode.getAttribute('name') ?? '';
      val = withRepetitionSuffix(!table ? name : table + '::' + name, fieldNode);
      // hrLabeled: label the field where FileMaker does (inverse of bare).
      if (val && param.hrLabeled && label) val = label + ': ' + val;
    }
  } else if (ptype === 'tableRef' || ptype === 'tableOccurrence') {
    const tableNode = findChild(base, 'Table');
    if (tableNode !== null) {
      const name = tableNode.getAttribute('name') ?? '';
      // Labeled (Go to Related Record's "From table") renders "Label: name";
      // label-less (Fine-Tune Model's positional training table) renders the
      // quoted TO name — the quoted positional spelling FM uses, like `layout`.
      if (name) val = !label ? '"' + name + '"' : label + ': ' + name;
    }
  } else if (ptype === 'fileReference') {
    const frNode = findChild(base, param.xmlElement);
    if (frNode !== null) {
      const path = childText(frNode, 'UniversalPathList');
      if (path) val = !label ? path : label + ': ' + path;
    }
  } else if (ptype === 'reference') {
    const refNode = findChild(base, param.xmlElement);
    if (refNode !== null) {
      const name = refNode.getAttribute('name') ?? '';
      if (name) val = !label ? '"' + name + '"' : label + ': ' + name;
    }
  } else if (ptype === 'layout') {
    const layoutNode = findChild(base, 'Layout');
    if (param.discriminator) {
      const dest = childAttr(base, param.discriminator, 'value');
      if (ciEquals(dest, 'OriginalLayout')) val = 'original layout';
      // FileMaker's own spelling, angle-bracketed (measured 26.0.1).
      else if (ciEquals(dest, 'CurrentLayout')) val = '<Current Layout>';
      // FileMaker prints the calculation bare, with no keyword.
      else if (ciEquals(dest, 'LayoutNameByCalc')) val = childText(layoutNode, 'Calculation');
      // Deliberately NOT FileMaker's spelling: FM renders this exactly like
      // LayoutNameByCalc, so mirroring it would collapse the two destinations.
      else if (ciEquals(dest, 'LayoutNumberByCalc')) val = 'by number: ' + childText(layoutNode, 'Calculation');
      else {
        const name = layoutNode !== null ? layoutNode.getAttribute('name') ?? '' : '';
        val = name ? '"' + name + '"' : '<unknown>';
      }
      // The label belongs to THIS param ("Using layout: <token>"); the sibling
      // discriminator carries none, or the parse reads label plus payload as a
      // literal layout name.
      if (val && label) val = label + ': ' + val;
    } else if (layoutNode !== null || param.required) {
      const name = layoutNode !== null ? layoutNode.getAttribute('name') ?? '' : '';
      let tok = '';
      if (name) tok = '"' + name + '"';
      else if (param.required) tok = '<unknown>';
      if (tok) val = !label ? tok : label + ': ' + tok;
    }
  } else if (ptype === 'script') {
    const scriptNode = findChild(base, 'Script');
    if (scriptNode !== null) {
      const name = scriptNode.getAttribute('name') ?? '';
      if (name) val = '"' + name + '"';
    }
    // hrLabeled: FileMaker labels the script token for some steps (Configure Region
    // Monitor Script's "Script:") while others print it bare (Perform Script).
    if (val && param.hrLabeled && label) val = label + ': ' + val;
  } else if (ptype === 'text' || ptype === 'name') {
    val = childText(base, param.xmlElement);
    if (val && param.parentElement && label) val = label + ': ' + val;
  }

  return val;
}

// ---------------------------------------------------------------------------
// Empty positional slots (HR render). The HR→XML parser hands bare tokens to
// bare-rendering params by POSITION, so a bare param whose value is empty must
// still hold its slot whenever a later positional token is rendered — otherwise
// that token slides into the empty param's slot (Set Next Serial Value with no
// field rendered `[ 100 ]` and read back as `<Field name="100"/>` with an empty
// calculation). A trailing empty slot is still dropped. Mirrors the reference.
// ---------------------------------------------------------------------------

/** Whether a param renders bare (positional) in HR — the pass-2 eligibility test. */
export function rendersBareInHr(param: GrammarParam): boolean {
  if (param.hrBare) return true; // per-param opt-in: FileMaker prints it bare
  if (!param.hrLabel) return true;
  // Inverse of hrBare: a calc/field/script FileMaker renders WITH its label is
  // matched by that label, never positionally.
  if (param.hrLabeled) return false;
  if (param.type === 'calc' || param.type === 'field' || param.type === 'script') return true;
  if (param.type === 'layout') return !param.hrLabel;
  if ((param.type === 'text' || param.type === 'name') && !param.parentElement) return true;
  if (param.type === 'calculation' && !param.omitWhenEmpty) return true;
  return false;
}

/**
 * Whether the HR parser reads `param` by position: pass-2 eligibility minus every
 * param pass 1 resolves without a positional token.
 */
function readsPositionally(entry: GrammarEntry, param: GrammarParam): boolean {
  if (param.hrHidden || param.type === 'complex' || param.type === 'bitmaskGroup') return false;
  if (param.flagStyle || param.type === 'flagElement') return false;
  if (isDrivenDiscriminator(entry, param) || isGoverningDiscriminator(param)) return false;
  return rendersBareInHr(param);
}

/**
 * Whether an EMPTY value of `param` renders as an empty slot when a later
 * positional token follows. A closed-vocabulary enum is excluded: the parser only
 * hands it a token naming one of its values, so an empty token would not fit.
 */
function emptyHoldsSlot(entry: GrammarEntry, param: GrammarParam): boolean {
  if (!readsPositionally(entry, param)) return false;
  const enumValues = (param.raw.enumValues as string[] | undefined) ?? [];
  return !(param.type === 'enum' && enumValues.length > 0);
}

/** A rendered token, tagged with whether the parser reads it by position. */
interface HrToken {
  text: string;
  positional: boolean;
  holdsSlot: boolean;
}

function paramToken(entry: GrammarEntry, param: GrammarParam, val: string): HrToken {
  let positional = readsPositionally(entry, param);
  if (param.type === 'repeatGroup' && param.raw.hrPositionalKey && val) {
    const label = param.hrLabel || '';
    positional = !label || !val.toLowerCase().startsWith((label + ':').toLowerCase());
  }
  return { text: val, positional, holdsSlot: emptyHoldsSlot(entry, param) };
}

/** A governing discriminator's HR tokens. Port of RenderDiscriminatorGroupTokens. */
function renderDiscriminatorGroupTokens(
  entry: GrammarEntry,
  step: Element,
  param: GrammarParam,
): HrToken[] {
  const value = readEnumRawValue(step, param, entry.elementAliases) || (param.defaultValue || '');
  const branch = param.discriminatorValues[value];
  if (branch === undefined) {
    const mapped = param.hrEnumValues[value] || value;
    const label = param.hrLabel || '';
    // Unlabeled, pass 1 cannot claim it, so the parser reads it by position.
    return !label
      ? [{ text: mapped, positional: true, holdsSlot: false }]
      : [{ text: label + ': ' + mapped, positional: false, holdsSlot: false }];
  }
  if (branch.hrToken) return [{ text: branch.hrToken, positional: false, holdsSlot: false }];
  const parts: HrToken[] = [];
  if (branch.labeled && param.hrLabel) {
    const mapped = param.hrEnumValues[value] || value;
    parts.push({ text: param.hrLabel + ': ' + mapped, positional: false, holdsSlot: false });
  }
  // A revealed companion is positional like any bare param, so it keeps its empty
  // slot (the caller drops it unless a later positional follows).
  for (const elem of branch.reveal) {
    for (const c of entry.params) {
      if (paramKey(c) !== elem) continue;
      parts.push(paramToken(entry, c, computeParamHr(entry, step, c)));
      break;
    }
  }
  return parts;
}

/**
 * Render a full step to its HR bracket line, as the reference does.
 * Returns `entry.name` alone when no param contributes a token, else
 * `Name [ tok ; tok ; … ]`. An empty positional slot followed by a later
 * positional token renders as an empty token (`[  ; 100 ]`). Does not handle
 * control-flow steps.
 */
export function renderStepHr(entry: GrammarEntry, step: Element): string {
  const parts: string[] = [];
  let pendingEmpty = 0;
  const add = (tok: HrToken): void => {
    if (!tok.text) {
      if (tok.holdsSlot) pendingEmpty++;
      return;
    }
    if (tok.positional) {
      for (; pendingEmpty > 0; pendingEmpty--) parts.push('');
    }
    parts.push(tok.text);
  };
  for (const pi of hrParamOrder(entry)) {
    const param = entry.params[pi];
    if (param.hrHidden) continue;
    if (governingDiscriminatorFor(entry, param)) continue;
    if (!paramVisible(entry, step, param)) continue;
    if (isGoverningDiscriminator(param)) {
      for (const tok of renderDiscriminatorGroupTokens(entry, step, param)) add(tok);
    } else {
      add(paramToken(entry, param, computeParamHr(entry, step, param)));
    }
  }
  if (parts.length === 0) return entry.name;
  return entry.name + ' [ ' + parts.join(' ; ') + ' ]';
}
