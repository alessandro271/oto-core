"""Shared pieces of the Sheets client: its error, A1 ranges, columns, tab titles."""
import re


#: A bare A1 range (`A:R`, `B5:D`, `5:9`), as opposed to a bare sheet name.
_A1 = re.compile(r'[A-Za-z]{0,3}\d*(:[A-Za-z]{0,3}\d*)?')


class SheetsClientError(Exception):
    pass


def _tab_title(title: str) -> str:
    """A tab title, checked before it goes out: Google refuses an empty one or one
    over 100 characters with a bare 400."""
    t = str(title or '').strip()
    if not t or len(t) > 100:
        raise SheetsClientError("a tab title is 1 to 100 characters")
    return t


def _col_row(cell: str) -> tuple:
    """`B5` → (1, 5) ; `B` → (1, None) ; `5` → (None, 5). 0-based column."""
    letters = ''.join(c for c in cell if c.isalpha()).upper()
    digits = ''.join(c for c in cell if c.isdigit())
    col = None
    if letters:
        col = 0
        for ch in letters:
            col = col * 26 + (ord(ch) - 64)
        col -= 1
    return col, (int(digits) if digits else None)


def _split_range(range: str) -> tuple:
    """`'Sheet'!A1:B2` → (`'Sheet'!`, `A1:B2`) ; a bare sheet name has no cells."""
    sheet, bang, cells = range.rpartition('!')
    if bang:
        return sheet + '!', cells
    if _A1.fullmatch(range):
        return '', range
    return range + '!', ''


def _column_index(letters) -> int:
    """`A` → 0, `AB` → 27. Anything but letters is refused."""
    text = str(letters or '').strip().upper()
    if not re.fullmatch(r'[A-Z]{1,3}', text):
        raise SheetsClientError(f"column: letters, e.g. C or AB (got {letters!r})")
    return _col_row(text)[0]


def _column_letters(index: int) -> str:
    """0 → `A`, 27 → `AB`."""
    out, n = '', index + 1
    while n:
        n, r = divmod(n - 1, 26)
        out = chr(65 + r) + out
    return out


def _column_bounds(grid: dict, range: str) -> tuple:
    if 'startColumnIndex' not in grid:
        raise SheetsClientError(f"range {range!r} names no column: give columns, e.g. 'Tab'!A:F")
    return grid['startColumnIndex'], grid['endColumnIndex']


def _count(count) -> int:
    n = int(count)
    if not 1 <= n <= 10000:
        raise SheetsClientError(f"count: 1 to 10000 (got {count!r})")
    return n


def _choice(table: dict, value, key: str) -> str:
    found = table.get(str(value).strip().lower())
    if found is None:
        raise SheetsClientError(f"style.{key}: one of {' | '.join(table)} (got {value!r})")
    return found
