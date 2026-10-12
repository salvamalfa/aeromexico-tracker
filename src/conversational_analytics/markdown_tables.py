"""Markdown table parsing shared by presentation sanitization."""

from __future__ import annotations

import re

_TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)*\|?\s*$")


def _cells(line: str) -> list[str]:
    """Match the browser table parser's escaped pipe and backslash grammar."""
    cells: list[str] = []
    cell = ""
    escaped = False
    ended_on_delimiter = False
    for char in line.strip():
        ended_on_delimiter = False
        if escaped:
            cell += char if char in {"|", "\\"} else f"\\{char}"
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == "|":
            cells.append(cell)
            cell = ""
            ended_on_delimiter = True
        else:
            cell += char
    if escaped:
        cell += "\\"
    if not ended_on_delimiter:
        cells.append(cell)
    if line.strip().startswith("|"):
        cells.pop(0)
    return [value.strip() for value in cells]


def _next_nonblank(lines: list[str], start: int) -> int:
    while start < len(lines) and not lines[start].strip():
        start += 1
    return start


def remove_numeric_markdown_tables(content: str) -> str:
    """Drop numeric prose tables when the same response has a validated display."""
    lines = content.splitlines(keepends=True)
    output: list[str] = []
    index = 0
    while index < len(lines):
        header = lines[index].strip()
        separator_index = _next_nonblank(lines, index + 1)
        if (
            "|" not in header
            or separator_index >= len(lines)
            or not _TABLE_SEPARATOR.fullmatch(lines[separator_index].strip())
        ):
            output.append(lines[index])
            index += 1
            continue
        width = len(_cells(header))
        row_index = separator_index + 1
        data_rows: list[str] = []
        while True:
            candidate_index = _next_nonblank(lines, row_index)
            if candidate_index >= len(lines):
                row_index = candidate_index
                break
            candidate = lines[candidate_index].strip()
            gap = candidate_index != row_index
            cells = _cells(candidate)
            full_width = len(cells) == width
            is_row = candidate.startswith("|") and (not gap or full_width)
            is_row = is_row or (not gap and "|" in candidate and full_width)
            if not is_row:
                row_index = candidate_index
                break
            after = _next_nonblank(lines, candidate_index + 1)
            after_cells = _cells(lines[after].strip()) if after < len(lines) else []
            if (
                after < len(lines)
                and _TABLE_SEPARATOR.fullmatch(lines[after].strip())
                and len(cells) >= 2
                and len(after_cells) == len(cells)
            ):
                row_index = candidate_index
                break
            data_rows.append(lines[candidate_index])
            row_index = candidate_index + 1
        cells = [cell for row in data_rows for cell in _cells(row)]
        # Any Unicode digit marks numeric content. This intentionally covers
        # scientific notation, attached currency/scale suffixes and period
        # labels without trying to enumerate every human number format.
        if data_rows and any(char.isdigit() for cell in cells for char in cell):
            index = row_index
        else:
            output.extend(lines[index:row_index])
            index = row_index
    return "".join(output)
