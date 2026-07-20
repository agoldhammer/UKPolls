"""Parse UK Wikipedia's national voting-intention poll tables into CSV.

Reads raw wikitext for "Opinion polling for the next United Kingdom general
election" and extracts every poll row from the "National poll results"
section (one wikitable per year), writing one CSV row per poll.

Usage: python3 parse_polls.py <input.wiki> <output.csv>
"""

import csv
import re
import sys
from datetime import date, timedelta

# Master party-column order for the output CSV. Restore Britain (RB) only
# exists in the 2026 table; earlier years simply leave that column blank.
PARTIES = ["Lab", "Con", "Ref", "LD", "Grn", "SNP", "PC", "RB"]

MONTHS = {}
for i, names in enumerate(
    [
        ("jan", "january"),
        ("feb", "february"),
        ("mar", "march"),
        ("apr", "april"),
        ("may",),
        ("jun", "june"),
        ("jul", "july"),
        ("aug", "august"),
        ("sep", "sept", "september"),
        ("oct", "october"),
        ("nov", "november"),
        ("dec", "december"),
    ],
    start=1,
):
    for name in names:
        MONTHS[name] = i


def get_attr_int(s, name):
    m = re.search(rf'{name}\s*=\s*"?(\d+)"?', s)
    return int(m.group(1)) if m else None


def strip_attrs(s):
    """Strip a leading wikitable cell attribute segment (rowspan=.. style=.. |),
    respecting {{ }} / [[ ]] nesting, returning the remaining cell content."""
    s = s.strip()
    depth = 0
    i = 0
    while i < len(s):
        if s[i : i + 2] in ("{{", "[["):
            depth += 1
            i += 2
            continue
        if s[i : i + 2] in ("}}", "]]"):
            depth -= 1
            i += 2
            continue
        if s[i] == "|" and depth == 0:
            return s[i + 1 :].strip()
        i += 1
    return s


def unwrap_hidden(s):
    """Replace each {{Hidden|header|content|...}} template with its first
    (header) parameter -- e.g. an Others cell of {{Hidden|1%|...breakdown...}}
    becomes just "1%". Splits parameters at top-level pipes only, since the
    collapsible content routinely nests {{Nowrap|..}} and [[..|..]]."""
    while True:
        m = re.search(r"\{\{\s*[Hh]idden\s*\|", s)
        if not m:
            return s
        start = m.start()
        i = m.end()
        depth = 0
        param_end = None
        while i < len(s):
            if s[i : i + 2] in ("{{", "[["):
                depth += 1
                i += 2
                continue
            if s[i : i + 2] == "]]":
                depth -= 1
                i += 2
                continue
            if s[i : i + 2] == "}}":
                if depth == 0:
                    break
                depth -= 1
                i += 2
                continue
            if s[i] == "|" and depth == 0 and param_end is None:
                param_end = i
            i += 1
        if i >= len(s):  # unbalanced template; leave as-is
            return s
        header = s[m.end() : param_end if param_end is not None else i]
        s = s[:start] + header.strip() + s[i + 2 :]


def clean_text(s):
    s = unwrap_hidden(s)
    s = re.sub(r"<!--.*?-->", "", s, flags=re.DOTALL)
    s = re.sub(r"<ref[^>]*>.*?</ref>", "", s, flags=re.DOTALL)
    s = re.sub(r"<ref[^>]*/>", "", s)
    s = re.sub(r"\{\{efn[^}]*\}\}", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\{\{sdash\}\}", "–", s)
    s = re.sub(r"\{\{blanc\|([^}]*)\}\}", r"\1", s)
    s = re.sub(r"'''(.*?)'''", r"\1", s)
    s = re.sub(r"''(.*?)''", r"\1", s)
    s = re.sub(r"<small>|</small>", "", s)
    s = re.sub(r"<br\s*/?>", " ", s)
    s = re.sub(r"\{\{formatnum[:|]([^}]*)\}\}", r"\1", s, flags=re.IGNORECASE)
    s = re.sub(r"\[\[[^|\]]*\|([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[\[([^\]]*)\]\]", r"\1", s)
    s = re.sub(r"\[https?://\S+\s+([^\]]+)\]", r"\1", s)
    s = re.sub(r"\[https?://\S+\]", "", s)
    return s.strip()


REF_OPEN = re.compile(r"<ref\b[^>]*?(/)?>", re.IGNORECASE)


def cells_from_block(block, marker):
    """Split a row block into raw cell strings. A new cell starts at a line
    beginning with `marker`, or at `marker*2` on the same line -- but only
    outside {{ }} / [[ ]] / <ref>...</ref> nesting, since citation templates
    routinely span multiple lines and contain bare pipes of their own that
    must not be mistaken for cell separators."""
    cells = []
    current = []
    depth = 0
    at_line_start = True
    i, n = 0, len(block)
    while i < n:
        m = REF_OPEN.match(block, i)
        if m:
            current.append(m.group(0))
            if not m.group(1):
                depth += 1
            i = m.end()
            at_line_start = False
            continue
        if block[i : i + 6].lower() == "</ref>":
            current.append(block[i : i + 6])
            depth = max(0, depth - 1)
            i += 6
            at_line_start = False
            continue
        two = block[i : i + 2]
        if two in ("{{", "[["):
            depth += 1
            current.append(two)
            i += 2
            at_line_start = False
            continue
        if two in ("}}", "]]"):
            depth = max(0, depth - 1)
            current.append(two)
            i += 2
            at_line_start = False
            continue
        ch = block[i]
        if depth == 0 and at_line_start and ch == marker:
            if "".join(current).strip():
                cells.append("".join(current))
            current = []
            i += 1
            at_line_start = False
            continue
        if depth == 0 and two == marker * 2:
            if "".join(current).strip():
                cells.append("".join(current))
            current = []
            i += 2
            at_line_start = False
            continue
        at_line_start = ch == "\n"
        current.append(ch)
        i += 1
    if "".join(current).strip():
        cells.append("".join(current))
    return [c for c in cells if c.strip() and c.strip() != "|}"]


def header_columns(header_block):
    cells = cells_from_block(header_block, "!")
    return [clean_text(strip_attrs(c)) for c in cells]


def parse_date_cell(raw, fallback_year):
    m = re.search(r"\{\{opdrts\|(.*?)\}\}", raw)
    if not m:
        return None, None
    params = m.group(1).split("|")
    nums_or_months = [p for p in params if p == "" or p.strip().lower() in MONTHS or p.strip().isdigit()]
    if len(nums_or_months) < 4:
        return None, None
    d1_raw, d2_raw, month_raw, year_raw = nums_or_months[:4]
    month = MONTHS.get(month_raw.strip().lower())
    if month is None or not year_raw.strip().isdigit():
        return None, None
    year = int(year_raw)
    d2 = int(d2_raw)
    end = date(year, month, d2)
    if d1_raw.strip() == "":
        return end, end
    d1 = int(d1_raw)
    if d1 <= d2:
        start = date(year, month, d1)
    else:
        prev_last_day = date(year, month, 1) - timedelta(days=1)
        start = date(prev_last_day.year, prev_last_day.month, d1)
    return start, end


def parse_percent(raw):
    content = clean_text(strip_attrs(raw))
    if content.endswith("%"):
        content = content[:-1]
    content = content.strip()
    if content in ("", "-", "–", "—") or "did not exist" in content.lower():
        return None
    try:
        return float(content.replace(",", "."))
    except ValueError:
        return None


def is_event_row(raw_cells, total_cols):
    """A full-width annotation row (e.g. a leadership change), rather than a
    poll: the date cell is followed by one cell spanning nearly all the
    remaining columns."""
    return any((get_attr_int(c, "colspan") or 1) >= total_cols - 2 for c in raw_cells)


def reconstruct_row(raw_cells, pending, total_cols):
    """Expand a row's raw cells to `total_cols` values, inserting content
    from rowspan cells opened by earlier rows (`pending`) at the right
    column position, and registering any new rowspans this row opens."""
    values = [None] * total_cols
    col = 0
    ci = 0
    while col < total_cols:
        if col in pending:
            remaining, content = pending[col]
            values[col] = content
            if remaining > 1:
                pending[col] = (remaining - 1, content)
            else:
                del pending[col]
            col += 1
            continue
        if ci >= len(raw_cells):
            break
        raw = raw_cells[ci]
        ci += 1
        colspan = get_attr_int(raw, "colspan") or 1
        rowspan = get_attr_int(raw, "rowspan") or 1
        for k in range(colspan):
            if col + k >= total_cols:
                break
            values[col + k] = raw
            if rowspan > 1:
                pending[col + k] = (rowspan - 1, raw)
        col += colspan
    return values


def parse_table(table_text):
    table_text = table_text.split("\n", 1)[1]  # drop the leading '{| ...' markup line
    blocks = re.split(r"(?m)^\|-.*$", table_text)
    blocks = [b for b in blocks if b.strip()]

    header_cells = None
    data_blocks = []
    for block in blocks:
        if block.lstrip("\n").startswith("!"):
            if header_cells is None:
                header_cells = header_columns(block)
            continue
        data_blocks.append(block)

    total_cols = len(header_cells)
    if header_cells[-1].lower() != "lead":
        print(f"warning: expected last header column 'Lead', got {header_cells[-1]!r}", file=sys.stderr)
    if header_cells[-2].lower() != "others":
        print(f"warning: expected second-to-last header column 'Others', got {header_cells[-2]!r}", file=sys.stderr)
    party_codes = header_cells[5 : total_cols - 2]

    rows = []
    pending = {}
    for block in data_blocks:
        raw_cells = cells_from_block(block, "|")
        if is_event_row(raw_cells, total_cols):
            continue
        values = reconstruct_row(raw_cells, pending, total_cols)
        if values[0] is None:
            continue
        start, end = parse_date_cell(values[0], None)
        if end is None:
            continue
        row = {
            "date": end.isoformat(),
            "survey_start": start.isoformat(),
            "pollster": clean_text(strip_attrs(values[1])) if values[1] else "",
            "client": clean_text(strip_attrs(values[2])) if values[2] else "",
            "area": clean_text(strip_attrs(values[3])) if values[3] else "",
        }
        sample_raw = clean_text(strip_attrs(values[4])) if values[4] else ""
        sample_raw = sample_raw.replace(",", "").replace(" ", "")
        row["sample_size"] = sample_raw if sample_raw.isdigit() else ""
        for code in PARTIES:
            row[code] = ""
        for code, raw in zip(party_codes, values[5 : total_cols - 2]):
            if raw is None:
                continue
            val = parse_percent(raw)
            if val is not None:
                row[code] = val
        others_raw = values[total_cols - 2]
        row["Others"] = parse_percent(others_raw) if others_raw is not None else ""
        rows.append(row)
    return rows


def parse_national_polls(wikitext):
    section = re.search(
        r"== National poll results ==\n(.*?)\n== [^=]", wikitext, re.DOTALL
    )
    if not section:
        raise ValueError("could not find 'National poll results' section")
    body = section.group(1)

    rows = []
    year_sections = re.split(r"(?m)^=== (\d{4}) ===$", body)
    # year_sections = [prelude, year1, text1, year2, text2, ...]
    for i in range(1, len(year_sections), 2):
        text = year_sections[i + 1]
        table_match = re.search(r"\{\|.*?\n\|\}", text, re.DOTALL)
        if not table_match:
            continue
        rows.extend(parse_table(table_match.group(0)))
    return rows


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as f:
        text = f.read()
    polls = parse_national_polls(text)
    fieldnames = ["date", "pollster", "client", "area", "sample_size"] + PARTIES + ["Others", "survey_start"]
    with open(sys.argv[2], "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for p in polls:
            w.writerow(p)
    print(f"Parsed {len(polls)} polls")
