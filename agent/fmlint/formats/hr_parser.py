"""Human-readable script parser for FMLint.

Parses HR format lines like:
  # comment text
  // Disabled Step [ params ]
  Set Variable [ $name ; expression ]
  If [ condition ]
"""

from ..literals import hr_opaque_span_at, is_double_delimiter, literal_span_at
from ..types import ParsedHRLine

# Every scanner below steps over calculation text literals and comments whole with
# the shared grammar in ``..literals``: ``"``, ``“`` and ``”`` are one
# interchangeable delimiter, a delimiter after an odd backslash run is content, and
# outside a literal ``/* … */`` (nesting) and ``// …`` (to the end of the line) are
# comments, so a ``;``, ``[``, ``]`` or quote inside ``"a\" ; b"``, ``“c ; d”`` or
# ``/* e ; ] */`` is content, not structure.

# How a ``//`` line comment ends while looking for a step's closing ``]``:
# AT_LINE_END -- the calculation grammar, tried first: a ``]`` inside the comment is
# comment text. YIELDS_TO_FINAL_BRACKET -- the fallback for a line written with the
# step's own ``]`` after a trailing comment (``Set Variable [ $x ; Value: $y // note ]``,
# FileMaker's own line): when the comment's line ends with ``]``, that ``]`` closes
# the step. Used only when AT_LINE_END never closes the statement, so
# ``… // a ; ]`` followed by a continuation line keeps its ``]`` as comment text.
AT_LINE_END, YIELDS_TO_FINAL_BRACKET = 0, 1


def _step_over_opaque(text: str, i: int, mode: int) -> int:
    """Offset just past the literal or comment opening at *i* (*i* when none)."""
    span = hr_opaque_span_at(text, i)
    if not span:
        return i
    end = i + span
    if mode == YIELDS_TO_FINAL_BRACKET and not literal_span_at(text, i) and text[i + 1] == "/":
        k = end
        while k > i + 2 and text[k - 1] in " \t":
            k -= 1
        if k > i + 2 and text[k - 1] == "]":
            end = k - 1
    return end


def parse_hr(text: str) -> list:
    """Parse HR script text into a list of ParsedHRLine objects."""
    raw_lines = text.split("\n")
    merged = _merge_multiline(raw_lines)
    return [_parse_line(m_text, m_line) for m_text, m_line in merged]


class _OpenScanTrace:
    """An AT_LINE_END statement scan that reached the end of the text with its bracket
    still open: per line (indexed from ``first``) the depth carried into it, whether it
    was entered outside every literal and comment, and the lowest depth at any later
    line end. A later statement starting on a cleanly entered line is answered from it
    without rescanning, which keeps a script of ``… // note ]`` lines linear."""

    def __init__(self, first: int):
        self.first = first
        self.valid = False
        self.start_depth: list = []
        self.clean_start: list = []
        self.end_min: list = []

    def known_open_from(self, k: int) -> bool:
        if not self.valid or k <= self.first or k - self.first >= len(self.clean_start):
            return False
        r = k - self.first
        return bool(self.clean_start[r]) and self.end_min[r] > self.start_depth[r]


_INF = float("inf")


def _statement_end_line(text: str, line_start: list, first: int, mode: int, trace) -> int:
    """Index of the line on which the statement starting at line *first* ends: the
    first line end, reached outside every literal and comment, at which its bracket
    depth is back to <= 0; -1 when the text ends first (recorded in *trace*)."""
    n_lines = len(line_start)
    line_end_depth: list = []

    def reach(to: int) -> None:
        if trace is None:
            return
        while len(line_end_depth) <= to - first:
            trace.start_depth.append(0)
            trace.clean_start.append(0)
            line_end_depth.append(_INF)

    reach(first)
    i = line_start[first]
    n = len(text)
    while i < n and text[i] in " \t":
        i += 1
    if text.startswith("//", i):
        i += 2  # disabled-step prefix, not a comment
    depth = 0
    line = first
    while i < n:
        ch = text[i]
        if ch == "\n":
            if depth <= 0:
                return line
            if trace is not None:
                reach(line + 1)
                line_end_depth[line - first] = depth
                trace.start_depth[line + 1 - first] = depth
                trace.clean_start[line + 1 - first] = 1
            line += 1
            i += 1
            continue
        if depth > 0:
            past = _step_over_opaque(text, i, mode)
            if past != i:
                line += text.count("\n", i, past)
                i = past
                continue
        elif is_double_delimiter(text, i):
            # A quote before any ``[`` keeps the historical per-line toggle.
            past = i + literal_span_at(text, i)
            eol = text.find("\n", i)
            if eol != -1 and past > eol:
                past = eol
            i = past
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
        i += 1
    if depth <= 0:
        return n_lines - 1
    if trace is not None:
        reach(n_lines - 1)
        line_end_depth[n_lines - 1 - first] = depth
        trace.end_min = [_INF] * (len(line_end_depth) + 1)
        for r in range(len(line_end_depth) - 1, -1, -1):
            trace.end_min[r] = min(trace.end_min[r + 1], line_end_depth[r])
        trace.valid = True
    return -1


def _merge_multiline(lines: list) -> list:
    """Merge continuation lines when brackets span multiple lines."""
    result = []
    if not lines:
        return result
    line_start = []
    pos = 0
    for line in lines:
        line_start.append(pos)
        pos += len(line) + 1
    text = "\n".join(lines)

    trace = _OpenScanTrace(0)
    k = 0
    while k < len(lines):
        trimmed = lines[k].strip()
        if trimmed.startswith("#") or trimmed == "":
            result.append((lines[k], k + 1))
            k += 1
            continue
        last = -1
        if not trace.known_open_from(k):
            fresh = _OpenScanTrace(k)
            last = _statement_end_line(text, line_start, k, AT_LINE_END, fresh)
            if fresh.valid:
                trace = fresh
        if last < 0:
            last = _statement_end_line(text, line_start, k, YIELDS_TO_FINAL_BRACKET, None)
        if last < 0:
            last = len(lines) - 1  # unclosed: the rest, as before
        result.append(("\n".join(lines[k : last + 1]), k + 1))
        k = last + 1
    return result


def _parse_line(raw: str, line_number: int) -> ParsedHRLine:
    """Parse a single HR script line."""
    trimmed = raw.lstrip()
    indent = len(raw) - len(trimmed)

    # Empty line
    if not trimmed:
        return ParsedHRLine(raw=raw, line_number=line_number, indent=indent)

    # Comment: # ...
    if trimmed.startswith("#"):
        comment_text = trimmed[1:].strip()
        return ParsedHRLine(
            raw=raw, line_number=line_number, is_comment=True,
            comment_text=comment_text, step_name="# (comment)", indent=indent,
        )

    # Disabled step: // ...
    disabled = False
    work_text = trimmed
    if trimmed.startswith("//"):
        disabled = True
        work_text = trimmed[2:].strip()

    # Extract step name and bracket content
    bracket_idx = _find_top_level_bracket(work_text)

    if bracket_idx >= 0:
        step_name = work_text[:bracket_idx].strip()
        close_bracket = _find_matching_bracket(work_text, bracket_idx)
        # Split the untrimmed content: a line break before the closing ``]`` ends a
        # ``//`` comment (XML->HR writes one after a comment that holds a ``;``), and
        # trimming it would hand that comment to the one-line reading.
        if close_bracket >= 0:
            content = work_text[bracket_idx + 1:close_bracket]
        else:
            content = work_text[bracket_idx + 1:]
        bracket_content = content.strip()
        params = _split_params(content)
    else:
        step_name = work_text.strip()
        bracket_content = ""
        params = []

    return ParsedHRLine(
        raw=raw, line_number=line_number, disabled=disabled,
        step_name=step_name, bracket_content=bracket_content,
        params=params, indent=indent,
    )


def _find_top_level_bracket(text: str) -> int:
    """Find the first top-level '[' not inside a text literal."""
    in_quote = False
    for i, ch in enumerate(text):
        if is_double_delimiter(text, i):
            in_quote = not in_quote
        if not in_quote and ch == "[":
            return i
    return -1


def _find_matching_bracket_in(text: str, open_idx: int, mode: int) -> int:
    depth = 0
    i = open_idx
    while i < len(text):
        past = _step_over_opaque(text, i, mode)
        if past != i:
            i = past
            continue
        ch = text[i]
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _find_matching_bracket(text: str, open_idx: int) -> int:
    """Find the matching ']' for an opening '[' (literals and comments are content)."""
    idx = _find_matching_bracket_in(text, open_idx, AT_LINE_END)
    if idx >= 0:
        return idx
    return _find_matching_bracket_in(text, open_idx, YIELDS_TO_FINAL_BRACKET)


def _split_params(content: str) -> list:
    """Split bracket content by semicolons, respecting literals, comments and nesting."""
    params = []
    current = ""
    paren_depth = 0
    bracket_depth = 0

    i = 0
    while i < len(content):
        # On the last line a ``//`` comment ends before the next ``;`` (the one-line
        # form FileMaker's Script Workspace shows).
        span = hr_opaque_span_at(content, i, ";")
        if span:
            current += content[i : i + span]
            i += span
            continue
        ch = content[i]
        if ch == "(":
            paren_depth += 1
        elif ch == ")":
            paren_depth -= 1
        elif ch == "[":
            bracket_depth += 1
        elif ch == "]":
            bracket_depth -= 1

        if ch == ";" and paren_depth == 0 and bracket_depth == 0:
            params.append(current.strip())
            current = ""
            i += 1
            continue

        current += ch
        i += 1

    if current.strip():
        params.append(current.strip())

    return params


def extract_calculation_from_params(params: list) -> str:
    """Extract the calculation expression from HR step parameters.

    For most steps, the calculation is the last parameter.
    For Set Variable, it's the second parameter (Value).
    For Set Field, it's the second parameter.
    """
    if len(params) >= 2:
        return params[-1].strip()
    if len(params) == 1:
        return params[0].strip()
    return ""
