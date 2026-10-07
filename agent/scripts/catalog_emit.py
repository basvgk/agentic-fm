#!/usr/bin/env python3
"""catalog_emit.py — the shared catalog grammar engine, values→XML direction (P6.4).

A faithful Python port of the reference converter's HR→fmxmlsnippet emit path (its
HR-param matcher, its step orchestrator and every per-type emit helper), and a
line-for-line counterpart of the shipped TS ``webviewer/src/converter/catalog-emit.ts``
(P6.3). Both are kept deliberately parallel so a facet added to one port is obviously
missing from the other (the plan's "Python↔TS structural parity" risk).

**Caveat to that parallelism — ``convert_step_with_catalog`` has TWO callers here and
one in the reference.** The reference converter's function is HR→XML only; this one is
also the emitter for the SaXML→snippet path (``saxml_read.read_saxml_step`` builds
``values[]`` from a SaXML ``<Step>`` and feeds it straight in). So a facet ported from
the reference inherits a question the reference never has to answer: *is this rule
derived from HR semantics that the SaXML input never went through?* Where it is, the
rule must only fill a slot the caller left EMPTY, never override one. The
governed-visibility derive below is written that way — an unconditional override would
discard the gate value a SaXML decoder had read from the source (Export Records seeds
its own ``Restore``).

Two public entry points:

  * ``match_param_values(entry, hr_params)`` — parse an HR bracket line's params into
    the per-catalog-param ``values[]`` token array (two-phase: pass 1 flags/labels,
    pass 2 positional). Used to *gate* the emitter against the committed
    ``hr-to-xml.json`` reference fixtures (the same 213/213 oracle the TS port uses),
    since the reference converter has no SaXML direction to grade against.
  * ``convert_step_with_catalog(entry, disabled, values, resolver)`` — emit the step's
    fmxmlsnippet XML in **catalog param order** from a ``values[]`` array (one token per
    catalog param). This is the shared emitter the P6.4 SaXML reader feeds directly
    (SaXML → values[] → this), so the same proven emit grammar serves both the
    HR→XML gate and SaXML→snippet conversion.

The ``values[]`` array *is* the OSS's made-explicit form of the reference's inline
value threading (the reference threads values inline with no struct; this names
them). Object
references resolve through an injected ``IdResolver`` — an empty resolver yields the
``id="0"`` name-only refs the fixtures use, while the SaXML path seeds the resolver from
the source's own IDs so real IDs are preserved.

Stdlib only; no venv. Reads the untyped facet tail from ``StepParam.raw`` (same design
as ``catalog_grammar.py``). Control-flow steps are NOT emitted here — they stay
hand-coded in the SaXML converter (the sanctioned exception).
"""

from __future__ import annotations

from typing import Any, Protocol

from calc_literal import calc_literal_span_at, decode_whole_calc_literal
from catalog_grammar import (
    CatalogEntry,
    StepParam,
    _group_quote_value,
    _group_unquote_value,
    candidate_hr_labels,
    governing_discriminator_for,
    hr_param_order,
    is_driven_discriminator,
    is_governing_discriminator,
    param_key,
    renders_bare_in_hr,
    value_reveals_companion,
)

# The unit-separator used to pack a bitmaskGroup's two HR tokens (style + controls)
# into one values[] slot, mirroring the TS port's '\x1e'.
_US = "\x1e"


# ---------------------------------------------------------------------------
# Reference resolver interface (mirror of the TS IdResolver)
# ---------------------------------------------------------------------------
class IdResolver(Protocol):
    """Resolve object-reference names to (id, name) — the emit injection point.

    ``resolve_field`` takes a ``Table::Field`` (or bare) string and returns
    ``(table, field_id, field_name)``. An empty-context resolver returns id 0 with
    the name passed through (matching how the reference fixtures were generated); the
    SaXML path supplies a resolver seeded from the source's own IDs.
    """

    def resolve_layout(self, name: str) -> tuple[int, str]: ...
    def resolve_field(self, table_field: str) -> tuple[str, int, str]: ...
    def resolve_script(self, name: str) -> tuple[int, str]: ...


class EmptyResolver:
    """id=0 name-only resolver — the offline / no-context behaviour the fixtures use."""

    def resolve_layout(self, name: str) -> tuple[int, str]:
        return 0, name

    def resolve_field(self, table_field: str) -> tuple[str, int, str]:
        sep = table_field.find("::")
        if sep < 0:
            return "", 0, table_field
        return table_field[:sep].strip(), 0, table_field[sep + 2 :].strip()

    def resolve_script(self, name: str) -> tuple[int, str]:
        return 0, name


# ---------------------------------------------------------------------------
# String helpers — ported to match the reference exactly (trim strips only
# spaces/tabs, not newlines, so multi-line calcs survive).
# ---------------------------------------------------------------------------
def _trim(s: str) -> str:
    return s.strip(" \t")


def _ci_equals(a: str, b: str) -> bool:
    return a.lower() == b.lower()


def _starts_with_ci(s: str, prefix: str) -> bool:
    return s[: len(prefix)].lower() == prefix.lower()


def _split_element_attr(xml_element: str) -> tuple[bool, str, str]:
    """G11 'Elem/@attr' notation → (True, 'Elem', 'attr'); else (False, '', '')."""
    pos = xml_element.find("/@")
    if pos == -1:
        return False, "", ""
    return True, xml_element[:pos], xml_element[pos + 2 :]


def esc_xml(s: str) -> str:
    return (
        s.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def esc_xml_attr(s: str) -> str:
    """Like esc_xml but numeric-refs whitespace (FM serializes tabs as ``&#9;``)."""
    out = []
    for c in s:
        if c == "&":
            out.append("&amp;")
        elif c == "<":
            out.append("&lt;")
        elif c == ">":
            out.append("&gt;")
        elif c == '"':
            out.append("&quot;")
        elif c == "\t":
            out.append("&#9;")
        elif c == "\n":
            out.append("&#10;")
        elif c == "\r":
            out.append("&#13;")
        else:
            out.append(c)
    return "".join(out)


def cdata(s: str) -> str:
    return "<![CDATA[" + s + "]]>"


def _split_top_level_commas(s: str) -> list[str]:
    """Split on top-level commas, respecting paren/bracket/brace depth + text literals.

    Used by the parametersList grammar and the attrGroup/repeatGroup body parser,
    whose quoted values are written as calculation literals (``_group_quote_value``).
    A literal is stepped over whole with the calculation literal grammar
    (``calc_literal``), so a comma inside ``"a\\", b"`` or ``“c, d”`` is content.
    """
    out: list[str] = []
    if not s:
        return out
    cur = ""
    paren = bracket = brace = 0
    i = 0
    n = len(s)
    while i < n:
        lit = calc_literal_span_at(s, i)
        if lit:
            cur += s[i : i + lit]
            i += lit
            continue
        c = s[i]
        if c == "(":
            paren += 1
        elif c == ")":
            if paren > 0:
                paren -= 1
        elif c == "[":
            bracket += 1
        elif c == "]":
            if bracket > 0:
                bracket -= 1
        elif c == "{":
            brace += 1
        elif c == "}" and brace > 0:
            brace -= 1
        if c == "," and paren == 0 and bracket == 0 and brace == 0:
            item = _trim(cur)
            if item:
                out.append(item)
            cur = ""
            i += 1
            continue
        cur += c
        i += 1
    tail = _trim(cur)
    if tail:
        out.append(tail)
    return out


def _split_on_delim(s: str, delim: str, calc_literals: bool) -> list[str]:
    """Split ``s`` on every top-level occurrence of multi-char ``delim``.

    A delimiter inside a quoted region is kept. With ``calc_literals`` the region is a
    calculation text literal (the repeatGroup entries, whose values are calculations
    or ``_group_quote_value``-quoted text); without it a straight ``"`` toggles a
    find-request phrase (the findRequests rows and criteria: find text is not a
    calculation, and ``"`` is FileMaker's match-phrase operator there).
    """
    out: list[str] = []
    if not delim:
        out.append(s)
        return out
    start = 0
    in_quote = False
    i = 0
    dn = len(delim)
    n = len(s)
    while i + dn <= n:
        if calc_literals:
            lit = calc_literal_span_at(s, i)
            if lit:
                i += lit
                continue
        elif s[i] == '"':
            in_quote = not in_quote
            i += 1
            continue
        if not in_quote and s[i : i + dn] == delim:
            piece = _trim(s[start:i])
            if piece:
                out.append(piece)
            i += dn
            start = i
            continue
        i += 1
    tail = _trim(s[start:])
    if tail:
        out.append(tail)
    return out


def _split_list_entries(s: str) -> list[str]:
    """Split a fieldList body on top-level commas, PRESERVING empty entries.

    Text literals are stepped over whole, as in ``_split_top_level_commas``.
    """
    out: list[str] = []
    if not _trim(s):
        return out
    cur = ""
    paren = bracket = brace = 0
    i = 0
    n = len(s)
    while i < n:
        lit = calc_literal_span_at(s, i)
        if lit:
            cur += s[i : i + lit]
            i += lit
            continue
        c = s[i]
        if c == "(":
            paren += 1
        elif c == ")":
            if paren > 0:
                paren -= 1
        elif c == "[":
            bracket += 1
        elif c == "]":
            if bracket > 0:
                bracket -= 1
        elif c == "{":
            brace += 1
        elif c == "}" and brace > 0:
            brace -= 1
        if c == "," and paren == 0 and bracket == 0 and brace == 0:
            out.append(_trim(cur))
            cur = ""
            i += 1
            continue
        cur += c
        i += 1
    out.append(_trim(cur))
    return out


def _split_path(path: str) -> list[str]:
    return [seg for seg in (path or "").split("/") if seg]


def _unquote(s: str) -> str:
    if len(s) >= 2 and s.startswith('"') and s.endswith('"'):
        return s[1:-1]
    return s


def _lower_key(k: str) -> str:
    return k.lower()


def _strip_parens(s: str) -> str:
    t = _trim(s)
    if len(t) >= 2 and t.startswith("(") and t.endswith(")"):
        return _trim(t[1:-1])
    return t


def _is_variable(s: str) -> bool:
    t = s.lstrip(" \t")
    return len(t) > 0 and t[0] == "$"


def _parse_field_repetition(ref: str) -> tuple[str, int]:
    """Split a trailing ``[N]`` repetition subscript off a field/variable ref.

    ``Invoices::Notes[2]`` -> (``Invoices::Notes``, 2); ``$rep[3]`` -> (``$rep``, 3).
    Only a positive integer subscript at the very end counts, with something
    before it; anything else (no subscript, ``[]``, ``[0]``, ``[$i]``) returns the
    ref unchanged and 0. FileMaker repetitions are 1-based.
    """
    if len(ref) < 3 or ref[-1] != "]":
        return ref, 0
    open_idx = ref.rfind("[")
    if open_idx <= 0 or open_idx + 1 == len(ref) - 1:
        return ref, 0
    digits = ref[open_idx + 1 : -1]
    if not digits.isascii() or not digits.isdigit() or len(digits) > 7:
        return ref, 0
    rep = int(digits)
    if rep < 1 or rep > 1000000:
        return ref, 0
    return ref[:open_idx], rep


def _repetition_attr(rep: int) -> str:
    """FileMaker's ``repetition="N"`` attribute, written only for N > 1."""
    return ' repetition="' + str(rep) + '"' if rep > 1 else ""


def _field_ref_xml(resolver: "IdResolver", ref: str, extra_attrs: str = "") -> str:
    """``<Field table id [repetition] name/>`` for a ``Table::Field[N]`` ref, in
    FileMaker's attribute order. The subscript is stripped before name resolution."""
    bare, rep = _parse_field_repetition(_trim(ref))
    table, fid, fname = resolver.resolve_field(bare)
    return (
        "<Field"
        + extra_attrs
        + ' table="'
        + esc_xml(table)
        + '" id="'
        + str(fid)
        + '"'
        + _repetition_attr(rep)
        + ' name="'
        + esc_xml(fname)
        + '"/>'
    )


def _variable_field_xml(var: str, extra_attrs: str = "") -> str:
    """``<Field [repetition]>$var</Field>`` for a ``$var[N]`` target."""
    bare, rep = _parse_field_repetition(_trim(var))
    return "<Field" + extra_attrs + _repetition_attr(rep) + ">" + esc_xml(bare) + "</Field>"


def _unquote_text_value(s: str) -> str:
    """Strip one surrounding quote pair from a free-text HR value: straight
    ``"…"``, curly ``“…”`` or curly single ``‘…’``. A no-op on bare text."""
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    if len(s) >= 2 and ((s[0] == "“" and s[-1] == "”") or (s[0] == "‘" and s[-1] == "’")):
        return s[1:-1]
    return s


def _text_param_value(param, hr_value: str) -> str:
    """The raw XML body for a ``text``/``name`` param's HR token.

    An ``hr_quoted`` param was rendered as one escaped text literal: decode it. A
    token that is not exactly one literal is FileMaker's own unescaped display
    (``“He said “hi”``) or bare text: strip one outer quote pair (a no-op on bare
    text). Any other text param is taken as written, except that a quoted lone
    variable used as a path/target unquotes to the bare ``$`` reference.
    """
    if param.hr_quoted:
        t = _trim(hr_value)
        decoded = decode_whole_calc_literal(t)
        return decoded if decoded is not None else _unquote_text_value(t)
    quoted, bare = _is_quoted_lone_variable(hr_value)
    return bare if quoted else hr_value


def _is_quoted_lone_variable(v: str) -> tuple[bool, str]:
    """True when ``v`` (trimmed, one layer of matching quotes stripped) is a single
    variable token; returns the bare variable as the tuple's second element."""
    t = _trim(v)
    lq, rq = "“", "”"
    if len(t) >= 2 and (
        (t.startswith('"') and t.endswith('"')) or (t.startswith(lq) and t.endswith(rq))
    ):
        t = t[1:-1]
    else:
        return False, ""
    if not t or t[0] != "$":
        return False, ""
    if any(ch in " \t\"" for ch in t):
        return False, ""
    return True, t


def _parse_group_kv(body: str) -> dict[str, str]:
    """Parse one group body ("k1=v1, k2=(…)") into a lower-cased key→raw-value map."""
    kv: dict[str, str] = {}
    for item in _split_top_level_commas(body):
        eq = item.find("=")
        if eq == -1:
            kv[_lower_key(_trim(item))] = ""
            continue
        kv[_lower_key(_trim(item[:eq]))] = _trim(item[eq + 1 :])
    return kv


# ---------------------------------------------------------------------------
# Raw-facet accessors (the untyped tail on StepParam.raw)
# ---------------------------------------------------------------------------
def _raw_str(r: dict[str, Any], k: str) -> str:
    v = r.get(k)
    return v if isinstance(v, str) else ""


def _raw_bool(r: dict[str, Any], k: str) -> bool:
    return r.get(k) is True


def _raw_num(r: dict[str, Any], k: str) -> int:
    v = r.get(k)
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def _raw_arr(r: dict[str, Any], k: str) -> list[dict[str, Any]]:
    v = r.get(k)
    return v if isinstance(v, list) else []


def _raw_str_arr(r: dict[str, Any], k: str) -> list[str]:
    v = r.get(k)
    return [x for x in v if isinstance(x, str)] if isinstance(v, list) else []


# ---------------------------------------------------------------------------
# Table resolution — the resolver has no resolve_table; offline a name resolves to
# id 0 name-passthrough, matching the reference's empty-context behaviour.
# ---------------------------------------------------------------------------
def _resolve_table(name: str) -> tuple[int, str]:
    return 0, name


# ---------------------------------------------------------------------------
# Value resolvers (HR token → XML value)
# ---------------------------------------------------------------------------
def _resolve_enum_xml_value(param: StepParam, hr_value: str) -> str:
    enum_values = _raw_str_arr(param.raw, "enumValues")
    if param.flag_style:
        flagged = hr_value == "True" or (
            hr_value != "" and bool(param.hr_label) and _ci_equals(hr_value, param.hr_label)
        )
        if flagged:
            for v in enum_values:
                if v != (param.default_value or ""):
                    return v
        return param.default_value or ""
    # Reverse the hrEnumValues map (FM-friendly HR token → raw XML value). std::map
    # iterates keys ascending; sort to match on a (rare) shared-label collision.
    if param.hr_enum_values and hr_value != "":
        for k in sorted(param.hr_enum_values.keys()):
            label = param.hr_enum_values[k]
            if label and _ci_equals(label, hr_value):
                return k
    return (param.default_value or "") if hr_value == "" else hr_value


def _param_visible_hr(entry: CatalogEntry, values: list[str], param: StepParam) -> bool:
    """HR->XML counterpart of catalog_grammar.param_visible: whether ``param`` passes
    its ``visibleWhen`` gate given the sibling param's resolved value from the parsed
    HR ``values``. An enum sibling's HR token is resolved to its FM XML value
    (so "Custom" -> "Other" is compared against the value the gate lists); any other
    sibling uses its raw HR value; empty falls back to the sibling's default. An
    unresolved gate reference is inert (visible), so a catalog typo degrades to
    always-emit. Symmetric with param_visible so both directions agree."""
    vw = param.visible_when
    if vw is None or not vw.param:
        return True
    for i, q in enumerate(entry.params):
        if param_key(q) != vw.param:
            continue
        raw = values[i] if i < len(values) else ""
        v = _resolve_enum_xml_value(q, raw) if q.type == "enum" else raw
        if v == "":
            v = q.default_value or ""
        return v in vw.values
    return True


def _resolve_bool_state(param: StepParam, hr_value: str) -> str:
    state = param.default_value if param.default_value else "False"
    if hr_value != "":
        lower = hr_value.lower()
        if lower in ("on", "true", "yes"):
            hr_means_true = True
        elif lower in ("off", "false", "no"):
            hr_means_true = False
        else:
            hr_means_true = state == "True"
            for xml_state in sorted(param.hr_enum_values.keys()):
                if param.hr_enum_values[xml_state].lower() == lower:
                    hr_means_true = xml_state == "True"
                    break
        if param.inverted_hr:
            hr_means_true = not hr_means_true
        state = "True" if hr_means_true else "False"
    return state


# ---------------------------------------------------------------------------
# Layout token (self-describing) → LayoutDestination value + <Layout> child XML
# ---------------------------------------------------------------------------
def _strip_resolved_layout_decoration(tok: str) -> tuple[bool, str]:
    """Strip FileMaker's display decoration from a resolved-layout token.

    FM wraps a resolved layout NAME in curly quotes and appends the table
    occurrence: ``“Dashboard” (Admin)``. It renders calculation source text with
    whatever straight quotes the calc itself contains, so a curly-quoted token is
    FM's unambiguous marker for "this is a layout reference". Returns
    ``(was_curly, stripped)``.
    """
    if not tok.startswith("“"):
        return False, tok
    close = tok.rfind("”")
    if close < 1:
        return False, tok
    return True, tok[1:close]


def _looks_like_layout_calculation(tok: str) -> bool:
    """Whether a bare layout token is calculation source text, not a name.

    FileMaker never renders a layout name bare — resolved is curly-quoted,
    unresolved is ``<unknown>`` — so every bare token it emits here is a
    calculation. An agent may reasonably write a bare layout name though, and
    reading that as a calculation would emit a step that evaluates the name. So
    only tokens that cannot be a name are taken as calculations.
    """
    if not tok:
        return False
    if _is_variable(tok):
        return True
    if tok.isdigit():
        return True
    return "(" in tok or "&" in tok


def _resolve_layout_token(hr_value: str, resolver: IdResolver) -> tuple[str, str]:
    tok = _trim(hr_value)
    if _ci_equals(tok, "original layout") or _ci_equals(tok, "<original layout>"):
        return "OriginalLayout", ""
    if _ci_equals(tok, "current layout") or _ci_equals(tok, "<current layout>"):
        return "CurrentLayout", ""
    # FM's rendering of a SelectedLayout whose <Layout> is the empty default.
    if _ci_equals(tok, "<unknown>"):
        return "SelectedLayout", '    <Layout id="0" name=""/>'

    def by_calc(kw: str, dest: str) -> tuple[str, str] | None:
        if _starts_with_ci(tok, kw):
            calc = _trim(tok[len(kw) :])
            return (
                dest,
                "    <Layout>\n      <Calculation>"
                + cdata(calc)
                + "</Calculation>\n    </Layout>",
            )
        return None

    r = by_calc("by name:", "LayoutNameByCalc")
    if r:
        return r
    r = by_calc("by number:", "LayoutNumberByCalc")
    if r:
        return r
    quoted, lone_var = _is_quoted_lone_variable(tok)
    calc = ""
    if quoted:
        calc = lone_var
    elif _is_variable(tok):
        calc = tok
    if calc:
        return (
            "LayoutNameByCalc",
            "    <Layout>\n      <Calculation>"
            + cdata(calc)
            + "</Calculation>\n    </Layout>",
        )
    # Curly quotes mark a layout REFERENCE; strip them (and the trailing table
    # occurrence) before resolving. Checked before the bare-calculation test so a
    # name carrying calculation-looking punctuation is never mistaken for a calc.
    was_resolved_form, tok = _strip_resolved_layout_decoration(tok)
    if not was_resolved_form and _looks_like_layout_calculation(tok):
        return (
            "LayoutNameByCalc",
            "    <Layout>\n      <Calculation>"
            + cdata(tok)
            + "</Calculation>\n    </Layout>",
        )
    rid, rname = resolver.resolve_layout(_unquote(tok))
    if rid == 0 and rname:
        piece = '    <Layout name="' + esc_xml(rname) + '"/>'
    else:
        piece = '    <Layout id="' + str(rid) + '" name="' + esc_xml(rname) + '"/>'
    return "SelectedLayout", piece


# ---------------------------------------------------------------------------
# Two-phase HR-param matching (parse-HR): pass 1 flags/labels, pass 2 positional.
# ---------------------------------------------------------------------------
def match_param_values(entry: CatalogEntry, hr_params: list[str]) -> list[str]:
    """Parse HR bracket params into the per-catalog-param values[] token array."""
    values = [""] * len(entry.params)
    resolved = [False] * len(entry.params)
    consumed = [False] * len(hr_params)
    # Which params claimed an HR token, by label or by position -- distinct from
    # "has a non-empty value": an empty slot is still evidence for the P7.2 derive.
    got_token = [False] * len(entry.params)

    for pi, param in enumerate(entry.params):
        if param.hr_hidden:
            resolved[pi] = True
            continue
        if param.type == "complex":
            resolved[pi] = True
            continue
        if is_driven_discriminator(entry, param):
            resolved[pi] = True
            continue

        if param.type == "bitmaskGroup":
            resolved[pi] = True
            style_val = ""
            controls_val = ""
            style_found = False
            ctrl_present = False
            controls_label = _raw_str(param.raw, "hrControlsLabel")
            sp = (param.hr_label or "") + ":"
            cp = controls_label + ":"
            for i in range(len(hr_params)):
                if consumed[i]:
                    continue
                t = _trim(hr_params[i])
                if not style_found and param.hr_label and _starts_with_ci(t, sp):
                    style_val = _trim(t[len(sp) :])
                    style_found = True
                    consumed[i] = True
                elif not ctrl_present and controls_label and _starts_with_ci(t, cp):
                    controls_val = _trim(t[len(cp) :])
                    ctrl_present = True
                    consumed[i] = True
            values[pi] = style_val
            if ctrl_present:
                values[pi] += _US + controls_val
            continue

        if is_governing_discriminator(param):
            resolved[pi] = True
            i = 0
            while i < len(hr_params) and values[pi] == "":
                if consumed[i]:
                    i += 1
                    continue
                t = _trim(hr_params[i])
                for value, spec in param.discriminator_values.items():
                    if spec.hr_token and _ci_equals(t, spec.hr_token):
                        consumed[i] = True
                        values[pi] = value
                        break
                i += 1
            # Claim the enum's own "hrLabel: value" token (Set Web Viewer "Action: …").
            if values[pi] == "" and param.hr_label:
                prefix = param.hr_label + ":"
                for i in range(len(hr_params)):
                    if consumed[i]:
                        continue
                    t = _trim(hr_params[i])
                    if _starts_with_ci(t, prefix):
                        consumed[i] = True
                        values[pi] = _resolve_enum_xml_value(param, _trim(t[len(prefix) :]))
                        break
            continue

        is_flag = (param.flag_style or param.type == "flagElement") and bool(param.hr_label)
        if is_flag:
            resolved[pi] = True
            for i in range(len(hr_params)):
                if consumed[i]:
                    continue
                if _ci_equals(_trim(hr_params[i]), param.hr_label):
                    consumed[i] = True
                    values[pi] = "True"
                    got_token[pi] = True
                    break
            continue

        if param.hr_label:
            for label in candidate_hr_labels(param):
                prefix = label + ":"
                for i in range(len(hr_params)):
                    if consumed[i]:
                        continue
                    t = _trim(hr_params[i])
                    if _starts_with_ci(t, prefix):
                        consumed[i] = True
                        values[pi] = _trim(t[len(prefix) :])
                        got_token[pi] = True
                        resolved[pi] = True
                        break
                if resolved[pi]:
                    break

    # Pass 2 — positional for the remaining bare-rendering params, in HR order.
    pos = 0
    for pi in hr_param_order(entry):
        if resolved[pi]:
            continue
        if not renders_bare_in_hr(entry.params[pi]):
            continue
        gov = governing_discriminator_for(entry, entry.params[pi])
        if gov is not None:
            gi = entry.params.index(gov)
            gval = (gov.default_value or "") if values[gi] == "" else values[gi]
            if not value_reveals_companion(gov, gval, param_key(entry.params[pi])):
                continue
        while pos < len(hr_params) and consumed[pos]:
            pos += 1
        if pos < len(hr_params):
            consumed[pos] = True
            values[pi] = _trim(hr_params[pos])
            got_token[pi] = True
            resolved[pi] = True
            pos += 1

    # hrPositionalKey repeatGroup: FileMaker prints each non-empty entry's
    # positional field bare after the step's own bare params (Show Custom Dialog
    # `[ "T" ; "M" ; $a ; Invoices::Number ]`), so the bare tokens left after
    # pass 2 are those entries, in order -- capped at repeatCount, and only a
    # token that can BE a target (a `$variable` or a `Table::Field` reference);
    # anything else stays unconsumed and is reported dropped. Mirrors the
    # reference converter.
    for pi, param in enumerate(entry.params):
        key = _raw_str(param.raw, "hrPositionalKey")
        if param.type != "repeatGroup" or not key or resolved[pi]:
            continue
        pos_field = next((f for f in _raw_arr(param.raw, "fields") if _raw_str(f, "key") == key), None)
        if pos_field is None:
            continue
        kind = _raw_str(pos_field, "kind")
        cap = int(param.raw.get("repeatCount", 0) or 0)

        def fits(tok: str) -> bool:
            if kind not in ("fieldOrVariable", "field"):
                return True
            if not tok or tok[0] == '"':
                return False
            if kind == "fieldOrVariable" and tok[0] == "$":
                return True
            return "::" in tok

        parts: list[str] = []
        for i in range(len(hr_params)):
            if consumed[i]:
                continue
            tok = _trim(hr_params[i])
            if not tok:
                continue
            if cap > 0 and len(parts) >= cap:
                break
            if not fits(tok):
                break
            consumed[i] = True
            parts.append(key + "=" + _group_quote_value(tok))
        if parts:
            values[pi] = " | ".join(parts)
            got_token[pi] = True
            resolved[pi] = True

    # P7.2 governed-visibility ENUM: a ``visibleWhen`` gate names a sibling enum
    # and the values of it under which this param is shown. FileMaker renders a
    # gate value that reveals a companion as the COMPANION ALONE, with no token of
    # its own, so the gate cannot be read back from the HR -- it falls through to
    # its catalog default instead, and FileMaker obeys the default and discards
    # the companion. Derive it from the gated params that claimed a token ("a
    # token was present", not "the value was non-empty": an empty slot is still
    # evidence). Refused when two gate values would explain the same companions
    # equally well. Mirrors the reference converter.
    for gi, gate in enumerate(entry.params):
        if gate.type != "enum" or values[gi] != "":
            continue
        gate_key = param_key(gate)
        chosen = ""
        ambiguous = False
        for qi, gated in enumerate(entry.params):
            if ambiguous:
                break
            vw = gated.visible_when
            if vw is None or vw.param != gate_key or not vw.values:
                continue
            if not got_token[qi]:
                continue
            for v in vw.values:
                if chosen == "":
                    chosen = v
                elif chosen != v:
                    ambiguous = True
                    break
        if not ambiguous and chosen:
            values[gi] = chosen

    return values


# ---------------------------------------------------------------------------
# Emit helpers
# ---------------------------------------------------------------------------
def _emit_boolean(param: StepParam, hr_value: str) -> str:
    state = _resolve_bool_state(param, hr_value)
    attr = param.xml_attr or "state"
    return "    <" + param.xml_element + " " + attr + '="' + state + '"/>'


def _emit_enum(param: StepParam, hr_value: str) -> str:
    value = _resolve_enum_xml_value(param, hr_value)
    if param.enum_style == "text":
        return "    <" + param.xml_element + ">" + esc_xml(value) + "</" + param.xml_element + ">"
    attr = param.xml_attr or "value"
    return "    <" + param.xml_element + " " + attr + '="' + esc_xml(value) + '"/>'


def _emit_named_calc(param: StepParam, hr_value: str) -> str:
    wrapper = param.wrapper_element or param.xml_element
    wa = _raw_str(param.raw, "wrapperAttr")
    open_attr = " " + wa if wa else ""
    return (
        "    <"
        + wrapper
        + open_attr
        + ">\n      <Calculation>"
        + cdata(hr_value)
        + "</Calculation>\n    </"
        + wrapper
        + ">"
    )


def _emit_parameters_list(param: StepParam, hr_value: str) -> str:
    if not _trim(hr_value):
        return ""
    items = _split_top_level_commas(hr_value)
    if not items:
        return ""
    wrapper = param.xml_element or "Parameters"
    out = "    <" + wrapper + ' Count="' + str(len(items)) + '">\n'
    for item in items:
        out += "      <P>\n"
        out += "        <Calculation>" + cdata(item) + "</Calculation>\n"
        out += "      </P>\n"
    out += "    </" + wrapper + ">"
    return out


def _emit_find_requests(hr_value: str, resolver: IdResolver) -> str:
    v = _trim(hr_value)
    if not v:
        return ""
    rows = _split_on_delim(v, " | ", calc_literals=False)
    if not rows:
        return ""
    out = "    <Query>\n"
    for row in rows:
        r = _trim(row)
        op = "Include"
        if _starts_with_ci(r, "Omit "):
            op = "Exclude"
            r = _trim(r[5:])
        elif _starts_with_ci(r, "Include "):
            r = _trim(r[8:])
        out += '      <RequestRow operation="' + op + '">\n'
        crits = _split_on_delim(r, " & ", calc_literals=False)
        if not crits:
            crits = [""]
        for crit in crits:
            c = _trim(crit)
            field = ""
            text = ""
            colon = c.find(": ")
            if colon != -1:
                field = _trim(c[:colon])
                text = _trim(c[colon + 2 :])
            else:
                text = c
            out += "        <Criteria>\n"
            if not field:
                out += '          <Field table="" id="0" name=""/>\n'
            else:
                table, fid, fname = resolver.resolve_field(field)
                out += (
                    '          <Field table="'
                    + esc_xml(table)
                    + '" id="'
                    + str(fid)
                    + '" name="'
                    + esc_xml(fname)
                    + '"/>\n'
                )
            out += "          <Text>" + esc_xml(text) + "</Text>\n"
            out += "        </Criteria>\n"
        out += "      </RequestRow>\n"
    out += "    </Query>"
    return out


def _emit_field_or_variable(
    param: StepParam, hr_value: str, resolver: IdResolver, preceded_by_text_element: bool
) -> str:
    if not hr_value:
        if _raw_bool(param.raw, "emitEmptyDefault"):
            return '    <Field table="" id="0" name=""/>'
        return ""
    # A typed same-element child (typeAttr/typeValue) carries its fixed
    # discriminator attribute on the <Field …> open tag — FM's variable-only
    # <Field type="Messages">/<Field type="ToolCalls"> children of one wrapper.
    # Generic, driven entirely by the catalog. Mirrors the C++ converter.
    type_attr = param.raw.get("typeAttr") or ""
    type_attr_str = (
        ' ' + type_attr + '="' + esc_xml(param.raw.get("typeValue") or "") + '"'
        if type_attr
        else ""
    )
    if _is_variable(hr_value):
        out = ""
        if not preceded_by_text_element:
            out += "    <Text/>\n"
        out += "    " + _variable_field_xml(hr_value, type_attr_str)
        return out
    out = ""
    if _raw_bool(param.raw, "textMarker") and not preceded_by_text_element:
        out += "    <Text/>\n"
    out += "    " + _field_ref_xml(resolver, hr_value, type_attr_str)
    return out


# ── attrGroup / repeatGroup ──────────────────────────────────────────────────
def _emit_group_element(
    element: str,
    fields: list[dict[str, Any]],
    kv: dict[str, str],
    indent: str,
    resolver: IdResolver,
) -> str:
    attrs = ""
    children = ""
    ci = indent + "  "
    for f in fields:
        kind = _raw_str(f, "kind")
        key = _raw_str(f, "key")
        it = kv.get(_lower_key(key))
        present = it is not None and it != ""
        if kind == "attr":
            if _raw_bool(f, "optional") and not present:
                continue
            v = _group_unquote_value(it) if present else _raw_str(f, "defaultValue")
            attrs += " " + _raw_str(f, "xmlAttr") + '="' + esc_xml_attr(v) + '"'
        elif kind == "text":
            if present:
                el = _raw_str(f, "childElement")
                children += ci + "<" + el + ">" + esc_xml(_group_unquote_value(it)) + "</" + el + ">\n"
        elif kind == "calc":
            require_attr = _raw_str(f, "requireAttr")
            if require_attr:
                attrs += " " + require_attr + '="' + ("True" if present else "False") + '"'
            if present:
                child_element = _raw_str(f, "childElement")
                if not child_element:
                    children += ci + "<Calculation>" + cdata(it) + "</Calculation>\n"
                else:
                    children += ci + "<" + child_element + ">\n"
                    children += ci + "  <Calculation>" + cdata(it) + "</Calculation>\n"
                    children += ci + "</" + child_element + ">\n"
        elif kind == "field":
            if present:
                children += ci + _field_ref_xml(resolver, it) + "\n"
        elif kind == "script":
            if present:
                sid, sname = resolver.resolve_script(_group_unquote_value(it))
                children += (
                    ci
                    + "<"
                    + _raw_str(f, "element")
                    + ' id="'
                    + str(sid)
                    + '" name="'
                    + esc_xml(sname)
                    + '"/>\n'
                )
        elif kind == "fieldOrVariable":
            v = _group_unquote_value(it) if present else ""
            if v and _is_variable(v):
                children += ci + _variable_field_xml(v) + "\n"
            elif v:
                children += ci + _field_ref_xml(resolver, v) + "\n"
            else:
                children += ci + '<Field table="" id="0" name=""/>\n'
        elif kind == "group":
            if present:
                children += (
                    _emit_group_element(
                        _raw_str(f, "element"),
                        _raw_arr(f, "fields"),
                        _parse_group_kv(_strip_parens(it)),
                        ci,
                        resolver,
                    )
                    + "\n"
                )
    open_tag = indent + "<" + element + attrs
    if not children:
        return open_tag + "/>"
    return open_tag + ">\n" + children + indent + "</" + element + ">"


def _emit_repeat_group(param: StepParam, hr_value: str, resolver: IdResolver) -> str:
    # hrDefault: no token means FileMaker's default content (its HR line omits
    # it); repeatCount: FileMaker always serializes that many entries, padded.
    if not _trim(hr_value):
        hr_value = _raw_str(param.raw, "hrDefault")
    if not _trim(hr_value):
        return ""
    entries = _split_on_delim(hr_value, " | ", calc_literals=True)
    cap = int(param.raw.get("repeatCount", 0) or 0)
    while cap > 0 and len(entries) < cap:
        entries.append("")
    out = "    <" + param.xml_element + ">\n"
    for e in entries:
        out += (
            _emit_group_element(
                _raw_str(param.raw, "entryElement"),
                _raw_arr(param.raw, "fields"),
                _parse_group_kv(_trim(e)),
                "      ",
                resolver,
            )
            + "\n"
        )
    out += "    </" + param.xml_element + ">"
    return out


def _emit_attr_group(param: StepParam, hr_value: str, resolver: IdResolver) -> str:
    if not _trim(hr_value) and not param.hr_hidden:
        return ""
    return _emit_group_element(
        param.xml_element, _raw_arr(param.raw, "fields"), _parse_group_kv(hr_value), "    ", resolver
    )


# ── bitmaskGroup ─────────────────────────────────────────────────────────────
def _bitmask_style_by_hr(param: StepParam, tok: str) -> dict[str, Any] | None:
    for s in _raw_arr(param.raw, "bitmaskStyles"):
        if _ci_equals(tok, _raw_str(s, "hrToken")):
            return s
        for a in _raw_str_arr(s, "aliases"):
            if _ci_equals(tok, a):
                return s
    return None


def _bitmask_mask_for_flags(param: StepParam, labels: list[str]) -> int:
    m = 0
    for lbl in labels:
        for f in _raw_arr(param.raw, "bitmaskFlags"):
            if _ci_equals(_raw_str(f, "hrLabel"), lbl):
                m |= _raw_num(f, "bit")
                break
    return m


def _bitmask_bit_for_flag(param: StepParam, label: str) -> int:
    if not label:
        return 0
    for f in _raw_arr(param.raw, "bitmaskFlags"):
        if _ci_equals(_raw_str(f, "hrLabel"), label):
            return _raw_num(f, "bit")
    return 0


def _compute_bitmask_integer(param: StepParam, style: dict[str, Any], chrome: int) -> int:
    v = _raw_num(param.raw, "bitmaskBase") | _raw_num(style, "baseBit") | chrome
    resize_bit = _bitmask_bit_for_flag(param, _raw_str(param.raw, "bitmaskResizeFlag"))
    user_resizable = _raw_bool(style, "docResizable") and (chrome & resize_bit) != 0
    if not user_resizable:
        v |= _raw_num(param.raw, "bitmaskFixedBit")
    return v & 0xFFFFFFFF


def _parse_controls_mask(param: StepParam, lst: str) -> int:
    v = _trim(lst)
    if not v or _ci_equals(v, "None"):
        return 0
    m = 0
    for tok in _split_top_level_commas(v):
        t = _trim(tok)
        for f in _raw_arr(param.raw, "bitmaskFlags"):
            if _ci_equals(t, _raw_str(f, "hrLabel")):
                m |= _raw_num(f, "bit")
                break
    return m


def _emit_bitmask_group(param: StepParam, packed: str) -> str:
    styles = _raw_arr(param.raw, "bitmaskStyles")
    if not styles:
        return ""
    style_tok = packed
    controls_tok = ""
    ctrl_present = False
    sep = packed.find(_US)
    if sep != -1:
        style_tok = packed[:sep]
        controls_tok = packed[sep + 1 :]
        ctrl_present = True
    style_tok = _trim(style_tok)
    st = styles[0] if style_tok == "" else (_bitmask_style_by_hr(param, style_tok) or styles[0])
    legal = _bitmask_mask_for_flags(param, _raw_str_arr(st, "legalFlags"))
    if ctrl_present:
        chrome = _parse_controls_mask(param, controls_tok)
    else:
        chrome = _bitmask_mask_for_flags(param, _raw_str_arr(st, "defaultFlags"))
    chrome &= legal
    integer = _compute_bitmask_integer(param, st, chrome)
    style_attr = _raw_str(param.raw, "bitmaskStyleAttr")
    value_attr = _raw_str(param.raw, "bitmaskValueAttr")
    out = "    <" + param.xml_element
    for attr in _raw_str_arr(param.raw, "bitmaskAttrOrder"):
        if attr == style_attr:
            out += " " + attr + '="' + esc_xml_attr(_raw_str(st, "xmlValue")) + '"'
        elif attr == value_attr:
            out += " " + attr + '="' + str(integer) + '"'
        else:
            on = False
            for f in _raw_arr(param.raw, "bitmaskFlags"):
                if _raw_str(f, "xmlAttr") == attr:
                    on = (chrome & _raw_num(f, "bit")) != 0
                    break
            out += " " + attr + '="' + ("Yes" if on else "No") + '"'
    out += "/>"
    return out


# ── fieldList ────────────────────────────────────────────────────────────────
def _emit_field_list(param: StepParam, hr_value: str, resolver: IdResolver) -> str:
    cattrs = ""
    for f in _raw_arr(param.raw, "fields"):
        cattrs += " " + _raw_str(f, "xmlAttr") + '="' + esc_xml_attr(_raw_str(f, "defaultValue")) + '"'
    entry_element = _raw_str(param.raw, "entryElement")
    field_wrapper = _raw_str(param.raw, "fieldWrapper")
    entry_attr = _raw_str(param.raw, "entryAttr")
    entry_attr_default = _raw_str(param.raw, "entryAttrDefault")
    field_fixed_attrs = _raw_arr(param.raw, "fieldFixedAttrs")
    children = ""
    for raw in _split_list_entries(hr_value):
        entry_str = _trim(raw)
        fieldref = entry_str
        attrval = entry_attr_default
        eq = entry_str.find("=")
        if eq != -1:
            fieldref = _trim(entry_str[:eq])
            attrval = _trim(entry_str[eq + 1 :])
        table, fid, fname = resolver.resolve_field(_group_unquote_value(fieldref))
        fattrs = ""
        for ff in field_fixed_attrs:
            fattrs += " " + _raw_str(ff, "xmlAttr") + '="' + esc_xml_attr(_raw_str(ff, "defaultValue")) + '"'
        if entry_attr and not entry_element:
            fattrs += " " + entry_attr + '="' + esc_xml_attr(attrval) + '"'
        node = (
            "<Field"
            + fattrs
            + ' table="'
            + esc_xml(table)
            + '" id="'
            + str(fid)
            + '" name="'
            + esc_xml(fname)
            + '"/>'
        )
        if field_wrapper:
            node = "<" + field_wrapper + ">" + node + "</" + field_wrapper + ">"
        if entry_element:
            eattr = " " + entry_attr + '="' + esc_xml_attr(attrval) + '"' if entry_attr else ""
            node = "<" + entry_element + eattr + ">" + node + "</" + entry_element + ">"
        children += "      " + node + "\n"
    out = "    <" + param.xml_element + cattrs
    if not children:
        return out + "/>"
    return out + ">\n" + children + "    </" + param.xml_element + ">"


# ---------------------------------------------------------------------------
# The orchestrator: values[] → emit-XML in catalog param order.
# ---------------------------------------------------------------------------
def convert_step_with_catalog(
    entry: CatalogEntry, disabled: bool, values: list[str], resolver: IdResolver
) -> str:
    """Emit one step's fmxmlsnippet XML from its per-param ``values[]`` token array."""
    params = entry.params
    step_id = entry.id if entry.id is not None else 0
    xml = (
        '  <Step enable="'
        + ("False" if disabled else "True")
        + '" id="'
        + str(step_id)
        + '" name="'
        + esc_xml(entry.name)
        + '">\n'
    )

    skip_param = [False] * len(params)

    # G10 attribute-bearing wrapper: a wrapper element may carry an enum value as an
    # attribute (FM serializes <Action value="Queue"> holding children).
    wrapper_attr: dict[str, str] = {}
    # G10 non-default standalone survival: a wrapper whose enum resolves to a
    # NON-default value but whose lazy-open group never fires (no child emits)
    # would otherwise drop the pre-resolved attribute entirely, leaving the step
    # with no discriminator (FM re-fills the default on paste, losing the authored
    # value). Remember these in param order and emit them as self-closing
    # <Wrapper attr="v"/> after the loop if the wrapper never opened. Default-valued
    # wrappers are intentionally NOT queued: a bare default emits nothing and FM
    # re-fills the same default on paste, matching FM's own render.
    g10_standalone: list[tuple[str, str]] = []
    is_wrapper: set[str] = set()
    for p in params:
        segs = _split_path(p.parent_element or "")
        if segs:
            is_wrapper.add(segs[0])
    for pi, p in enumerate(params):
        if p.type == "enum" and not p.parent_element and p.xml_element in is_wrapper:
            v = (p.default_value or "") if values[pi] == "" else values[pi]
            if v == "":
                continue
            attr = p.xml_attr or "value"
            attr_str = " " + attr + '="' + esc_xml(v) + '"'
            wrapper_attr[p.xml_element] = attr_str
            if v != (p.default_value or ""):
                g10_standalone.append((p.xml_element, attr_str))
            skip_param[pi] = True

    # G11 attribute-on-element: an enum/boolean param whose xmlElement uses "Elem/@attr"
    # contributes the attribute to the body element emitted by a sibling text/name param.
    element_attr: dict[str, str] = {}
    for pi, p in enumerate(params):
        is_ea, elem, attr = _split_element_attr(p.xml_element)
        if not is_ea:
            continue
        if p.type == "enum":
            v = _resolve_enum_xml_value(p, values[pi])
        elif p.type == "boolean":
            v = _resolve_bool_state(p, values[pi])
        else:
            continue
        if v == "":
            skip_param[pi] = True
            continue
        element_attr[elem] = element_attr.get(elem, "") + " " + attr + '="' + esc_xml(v) + '"'
        skip_param[pi] = True

    # Discriminator-driven layout: pre-resolve destination + <Layout> piece.
    discrim_value: dict[str, str] = {}
    layout_piece: dict[int, str] = {}
    for pi, p in enumerate(params):
        if p.type != "layout" or not p.discriminator:
            continue
        dest, piece = _resolve_layout_token(values[pi], resolver)
        discrim_value[p.discriminator] = dest
        layout_piece[pi] = piece

    # Governing-discriminator pre-pass: resolve each governing enum's XML value.
    gov_discrim_value: dict[str, str] = {}
    for pi, p in enumerate(params):
        if not is_governing_discriminator(p):
            continue
        gov_discrim_value[p.xml_element] = (p.default_value or "") if values[pi] == "" else values[pi]

    # Governed-visibility boolean: an ``hrHidden`` boolean that some sibling's
    # ``visibleWhen`` gates on carries NO HR token of its own — FileMaker's HR shows
    # none either — so it cannot be read back from HR the way a flag-style boolean
    # can. Its state is instead DERIVED on emit from whether any gated sibling
    # contributed a token, which is exactly how FileMaker's own HR encodes it:
    # Import Records shows Table/method/charset only under Restore=True, and
    # FileMaker discards the stored import order when the flag is off.
    #
    # Without this the flag falls through to its catalog ``defaultValue`` (True for
    # both Restore params), so HR that says "no stored import order" would serialize
    # as "restore the stored order".
    #
    # The ``values[gi] == ""`` guard is what keeps the SaXML reader whole: on the HR
    # path a hidden param is excluded from matching so its slot is always empty, but
    # a SaXML decoder may have read the gate's real value from the source (Export
    # Records sets its own Restore), and that reading wins.
    implied_bool: dict[int, str] = {}
    for gi, gate in enumerate(params):
        if not gate.hr_hidden or gate.type != "boolean" or values[gi] != "":
            continue
        gate_key = param_key(gate)
        on_value = ""  # the gate value that REVEALS a companion
        gates = False
        any_content = False
        for pi, p in enumerate(params):
            vw = p.visible_when
            if vw is None or vw.param != gate_key or not vw.values:
                continue
            gates = True
            if on_value == "":
                on_value = vw.values[0]
            if _trim(values[pi]) != "":
                any_content = True
        if not gates:
            continue  # hrHidden but nothing gates on it: default emit
        off_value = "False" if on_value == "True" else "True"
        implied_bool[gi] = on_value if any_content else off_value

    prev_was_text_element = False
    open_groups: list[str] = []
    # Wrappers actually opened by an emitting child during the loop, so the
    # post-loop G10 standalone pass only injects for wrappers that never opened.
    wrapper_opened: set[str] = set()

    for pi, param in enumerate(params):
        hr_value = values[pi]
        if skip_param[pi]:
            continue

        is_text_element = (
            param.type in ("text", "name") and param.xml_element == "Text"
        )

        piece = ""
        gov = governing_discriminator_for(entry, param)
        gov_handled = False
        if gov is not None:
            dval = gov_discrim_value.get(gov.xml_element, gov.default_value or "")
            revealed = value_reveals_companion(gov, dval, param_key(param))
            if param.type == "boolean" and not revealed and param.omit_when_empty:
                gov_handled = True
            elif param.type == "boolean":
                attr = param.xml_attr or "state"
                if not revealed:
                    st = param.default_value if param.default_value else "False"
                else:
                    st = _resolve_bool_state(param, "Off" if hr_value == "" else hr_value)
                piece = "    <" + param.xml_element + " " + attr + '="' + st + '"/>'
                gov_handled = True
            elif not revealed:
                gov_handled = True

        if gov_handled:
            pass  # piece already decided (a value or intentionally empty)
        elif (
            param.type == "boolean"
            and param.visible_when is not None
            and param.visible_when.param
            and param.omit_when_empty
        ):
            # P7.3 governed-visibility boolean: a boolean whose PRESENCE (not just
            # value) is governed by a sibling enum's value declares a ``visibleWhen``
            # gate — the generic "governed by another param's enum value" primitive,
            # symmetric with the XML->HR param_visible skip and the discriminator-
            # revealed omit. When the gate value is not met FileMaker omits the
            # element ENTIRELY (confirmed live: Configure AI Account drops
            # <VerifySSLCertificates> for every LLMType except "Other"); when met it
            # emits with the normal flag-style presence semantics. Opt-in via
            # omitWhenEmpty. Benefits any step of this shape, not just #212.
            if _param_visible_hr(entry, values, param):
                piece = _emit_boolean(param, hr_value)
            # else: gate not met -> omit entirely (piece stays "")
        elif param.type == "boolean":
            if pi in implied_bool:
                attr = param.xml_attr or "state"
                piece = "    <" + param.xml_element + " " + attr + '="' + implied_bool[pi] + '"/>'
            else:
                piece = _emit_boolean(param, hr_value)
        elif param.type == "enum":
            if param.xml_element in discrim_value:
                attr = param.xml_attr or "value"
                piece = "    <" + param.xml_element + " " + attr + '="' + esc_xml(discrim_value[param.xml_element]) + '"/>'
            elif is_governing_discriminator(param):
                v = gov_discrim_value.get(param.xml_element, param.default_value or "")
                if param.enum_style == "text":
                    piece = "    <" + param.xml_element + ">" + esc_xml(v) + "</" + param.xml_element + ">"
                else:
                    attr = param.xml_attr or "value"
                    piece = "    <" + param.xml_element + " " + attr + '="' + esc_xml(v) + '"/>'
            elif param.omit_when_empty and not _trim(hr_value):
                pass  # present-driven enum omitted when unset
            else:
                piece = _emit_enum(param, hr_value)
        elif param.type in ("calculation", "calc"):
            if not param.omit_when_empty or _trim(hr_value):
                piece = "    <Calculation>" + cdata(hr_value) + "</Calculation>"
        elif param.type == "attrGroup":
            piece = _emit_attr_group(param, hr_value, resolver)
        elif param.type == "bitmaskGroup":
            piece = _emit_bitmask_group(param, hr_value)
        elif param.type == "repeatGroup":
            piece = _emit_repeat_group(param, hr_value, resolver)
        elif param.type == "fieldList":
            if _trim(hr_value):
                piece = _emit_field_list(param, hr_value, resolver)
        elif param.type == "namedCalc":
            if hr_value != "" or param.required:
                piece = _emit_named_calc(param, hr_value)
        elif param.type == "parametersList":
            piece = _emit_parameters_list(param, hr_value)
        elif param.type == "findRequests":
            piece = _emit_find_requests(hr_value, resolver)
        elif param.type == "fieldOrVariable":
            piece = _emit_field_or_variable(param, hr_value, resolver, prev_was_text_element)
        elif param.type == "flagElement":
            if hr_value != "":
                piece = "    <" + param.xml_element + "/>"
        elif param.type == "field":
            if not param.omit_when_empty or _trim(hr_value):
                piece = "    " + _field_ref_xml(resolver, hr_value)
        elif param.type == "tableRef":
            if not _trim(hr_value):
                # A present-driven, gated table (Fine-Tune Model's training
                # <Table>, revealed only in the DataTable branch) opts into
                # omit_when_empty and emits nothing when unset.
                if not param.omit_when_empty:
                    piece = '    <Table id="" name=""/>'
            else:
                tid, tname = _resolve_table(_unquote(hr_value))
                piece = '    <Table id="' + str(tid) + '" name="' + esc_xml(tname) + '"/>'
        elif param.type == "tableOccurrence":
            # An unset present-driven TO (omit_when_empty) emits no <Table> —
            # matching FM's TrainingFile form; otherwise the TO always serializes.
            if _trim(hr_value) or not param.omit_when_empty:
                tid, tname = _resolve_table(_unquote(hr_value))
                piece = '    <Table id="' + str(tid) + '" name="' + esc_xml(tname) + '"/>'
        elif param.type == "fileReference":
            if _trim(hr_value):
                quoted, bare = _is_quoted_lone_variable(hr_value)
                emit_value = bare if quoted else hr_value
                piece = (
                    "    <"
                    + param.xml_element
                    + ' id="0" name="">\n      <UniversalPathList>'
                    + esc_xml(emit_value)
                    + "</UniversalPathList>\n    </"
                    + param.xml_element
                    + ">"
                )
        elif param.type == "reference":
            name = _unquote(hr_value)
            if name != "" or param.required:
                wa = _raw_str(param.raw, "wrapperAttr")
                extra = " " + wa if wa else ""
                piece = "    <" + param.xml_element + ' name="' + esc_xml(name) + '"' + extra + "/>"
        elif param.type == "layout":
            if param.discriminator:
                if pi in layout_piece:
                    piece = layout_piece[pi]
            else:
                layout_name = _unquote(hr_value)
                if layout_name == "" or _ci_equals(layout_name, "<unknown>"):
                    piece = '    <Layout id="0" name=""/>'
                else:
                    rid, rname = resolver.resolve_layout(layout_name)
                    if rid == 0 and rname:
                        piece = '    <Layout name="' + esc_xml(rname) + '"/>'
                    else:
                        piece = '    <Layout id="' + str(rid) + '" name="' + esc_xml(rname) + '"/>'
        elif param.type == "script":
            if not param.omit_when_empty or _trim(hr_value):
                # Cross-file reference (Perform Script id 1): FM renders a call into
                # another file as the positional token `"NAME" from file: "FILE"`.
                # When the catalog opts this script param into the from-file grammar
                # (``fromFileElement`` set), split that infix clause into a
                # <FileReference name="FILE"> sibling emitted BEFORE the <Script>,
                # carrying a <UniversalPathList>file:FILE</> child, and emit the
                # <Script> NAME-ONLY. FM binds the reference by the external-data-
                # source NAME when one of that name exists in the destination — the
                # path is then ignored (even a wrong path binds, no dialog), so an
                # in-solution cross-file call never regresses. When the destination
                # does NOT yet reference FILE, the child preserves the file name
                # (`from file: "FILE"`) and lets FM raise its normal locate prompt
                # (fail-loud) instead of a name-only reference's silent `from file:
                # ""` drop. The path uses the display NAME — the only value available
                # offline; name-binding makes the real filename moot for resolvable
                # references. The <Script> stays name-only: its binding id lives in
                # the OTHER file (absent from the current-file context), so resolving
                # it would bind the WRONG same-file script of the same name; FM shows
                # it <unknown> until rebound while the file + name survive intact.
                from_file_element = _raw_str(param.raw, "fromFileElement")
                file_name = ""
                script_token = hr_value
                if from_file_element:
                    marker = " from file: "
                    fp = hr_value.find(marker)
                    if fp != -1:
                        script_token = _trim(hr_value[:fp])
                        file_name = _unquote(_trim(hr_value[fp + len(marker):]))
                script_name = _unquote(script_token)
                if file_name:
                    script_xml = '    <Script name="' + esc_xml(script_name) + '"/>'
                    piece = (
                        "    <" + from_file_element + ' name="' + esc_xml(file_name) + '">\n'
                        + "      <UniversalPathList>file:" + esc_xml(file_name)
                        + "</UniversalPathList>\n    </" + from_file_element + ">\n"
                        + script_xml
                    )
                else:
                    sid, sname = resolver.resolve_script(script_name)
                    piece = '    <Script id="' + str(sid) + '" name="' + esc_xml(sname) + '"/>'
        elif param.type in ("text", "name") and (not param.omit_when_empty or _trim(hr_value)):
            emit_value = _text_param_value(param, hr_value)
            attrs = element_attr.get(param.xml_element, "")
            piece = "    <" + param.xml_element + attrs + ">" + esc_xml(emit_value) + "</" + param.xml_element + ">"
        # complex + unhandled types yield no piece.

        if piece == "":
            continue

        # Reconcile the open-wrapper stack with this param's parentElement path.
        want = _split_path(param.parent_element or "")
        common = 0
        while common < len(open_groups) and common < len(want) and open_groups[common] == want[common]:
            common += 1
        for k in range(len(open_groups), common, -1):
            xml += "    </" + open_groups[k - 1] + ">\n"
        del open_groups[common:]
        for k in range(common, len(want)):
            wa = wrapper_attr.get(want[k], "")
            xml += "    <" + want[k] + wa + ">\n"
            open_groups.append(want[k])
            wrapper_opened.add(want[k])

        xml += piece + "\n"
        prev_was_text_element = is_text_element

    for k in range(len(open_groups), 0, -1):
        xml += "    </" + open_groups[k - 1] + ">\n"

    # G10 non-default standalone survival: any G10 wrapper whose enum carried a
    # non-default value but whose lazy-open group never fired (no child emitted)
    # would otherwise drop its pre-resolved attribute. Emit the self-closing
    # <Wrapper attr="v"/> so the authored value survives the round-trip; the
    # default-valued case is never queued, so a bare default still emits nothing.
    for wrapper, attr_str in g10_standalone:
        if wrapper not in wrapper_opened:
            xml += "    <" + wrapper + attr_str + "/>\n"

    xml += "  </Step>"
    return xml
