"""Look of the cells: number formats, styles and borders, widths, drop-downs,
merges, conditional formats.

Composed into `SheetsClient`, which provides the transport (`_batch`, `sheet_id`,
`_grid_range`, `sheets`). Contract: `../sheets_client.py`.
"""
from typing import List

from .._common import SheetsClientError, _column_bounds
from .._style import (_BORDER_KEYS, _NUMBER_FORMAT_TYPES, _STYLE_KEYS, _borders,
                      _cell_format, _conditional_rule)


class _LayoutMixin:
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

    def format(self, spreadsheet_id: str, range: str, style: dict) -> dict:
        """Apply a cell style to every cell of an A1 range. Only the keys given change
        (the others keep their format). Keys: `background`, `color` (`#rrggbb`),
        `bold`, `italic` (bool), `font_size` (points), `wrap` (True = wrap text,
        False = overflow), `align` (left | center | right), `valign` (top | middle |
        bottom), `borders` (all | outer | none) and `border_color` (`#rrggbb`, black
        by default)."""
        if not isinstance(style, dict):
            raise SheetsClientError(f"style: an object with at least one of {', '.join(_STYLE_KEYS)}")
        cell = {k: v for k, v in style.items() if k not in _BORDER_KEYS}
        borders = _borders(style) if set(style) & set(_BORDER_KEYS) else None
        if not cell and borders is None:
            _cell_format(style)   # raises, naming the valid keys
        grid = self._grid_range(spreadsheet_id, range)
        requests = []
        if cell:
            fmt, fields = _cell_format(cell)
            requests.append({'repeatCell': {
                'range': grid, 'cell': {'userEnteredFormat': fmt},
                'fields': ','.join(f'userEnteredFormat.{f}' for f in fields)}})
        if borders is not None:
            requests.append({'updateBorders': {'range': grid, **borders}})
        self._batch(spreadsheet_id, requests)
        return {'range': range, 'applied': sorted(style)}

    def column_width(self, spreadsheet_id: str, range: str, width: int) -> dict:
        """Set the width, in pixels, of the columns of an A1 range (`'Tab'!A:C`)."""
        px = int(width)
        if px < 1:
            raise SheetsClientError(f"width: pixels >= 1 (got {width!r})")
        grid = self._grid_range(spreadsheet_id, range)
        if 'startColumnIndex' not in grid:
            raise SheetsClientError(
                f"range {range!r} names no column: give columns, e.g. 'Tab'!A:C")
        self._batch(spreadsheet_id, [{'updateDimensionProperties': {
            'range': {'sheetId': grid['sheetId'], 'dimension': 'COLUMNS',
                      'startIndex': grid['startColumnIndex'],
                      'endIndex': grid['endColumnIndex']},
            'properties': {'pixelSize': px}, 'fields': 'pixelSize'}}])
        return {'range': range, 'columns': grid['endColumnIndex'] - grid['startColumnIndex'],
                'width': px}

    def auto_fit(self, spreadsheet_id: str, range: str) -> dict:
        """Fit the width of the columns of a range (`'Tab'!A:F`) to their content."""
        grid = self._grid_range(spreadsheet_id, range)
        start, end = _column_bounds(grid, range)
        self._batch(spreadsheet_id, [{'autoResizeDimensions': {'dimensions': {
            'sheetId': grid['sheetId'], 'dimension': 'COLUMNS',
            'startIndex': start, 'endIndex': end}}}])
        return {'range': range, 'columns': end - start}

    def dropdown(self, spreadsheet_id: str, range: str, options: List[str]) -> dict:
        """A drop-down list on every cell of an A1 range: a value outside `options`
        is rejected. An empty `options` REMOVES the validation from the range."""
        values = [str(o) for o in options]
        if any(not v.strip() for v in values):
            raise SheetsClientError("options: no empty choice")
        grid = self._grid_range(spreadsheet_id, range)
        request: dict = {'range': grid}
        if values:
            request['rule'] = {
                'condition': {'type': 'ONE_OF_LIST',
                              'values': [{'userEnteredValue': v} for v in values]},
                'strict': True, 'showCustomUi': True}
        self._batch(spreadsheet_id, [{'setDataValidation': request}])
        return {'range': range, 'options': values, 'removed': not values}

    def merge(self, spreadsheet_id: str, range: str) -> dict:
        """Merge the cells of a range into one (the top-left value is kept)."""
        grid = self._grid_range(spreadsheet_id, range)
        self._batch(spreadsheet_id, [{'mergeCells': {'range': grid, 'mergeType': 'MERGE_ALL'}}])
        return {'range': range, 'merged': True}

    def unmerge(self, spreadsheet_id: str, range: str) -> dict:
        grid = self._grid_range(spreadsheet_id, range)
        self._batch(spreadsheet_id, [{'unmergeCells': {'range': grid}}])
        return {'range': range, 'merged': False}

    def conditional_format(self, spreadsheet_id: str, range: str, rule: dict) -> dict:
        """Colour the cells of a range that meet a condition. `rule`:
        `{"when": "number_less", "values": [0], "style": {"background": "#f4cccc"}}`.
        `when`: number_greater | number_greater_or_equal | number_less |
        number_less_or_equal | number_eq | number_between (2 values) | text_contains |
        text_eq | blank | not_blank (no value) | formula (1 value, e.g. `=$C2>100`).
        `style`: background, color, bold, italic. The new rule goes first."""
        built = _conditional_rule(rule)
        grid = self._grid_range(spreadsheet_id, range)
        built['ranges'] = [grid]
        self._batch(spreadsheet_id, [{'addConditionalFormatRule': {'rule': built, 'index': 0}}])
        return {'range': range, 'when': rule['when']}

    def clear_conditional_formats(self, spreadsheet_id: str, sheet) -> dict:
        """Remove every conditional format rule of a tab. Returns how many went."""
        sid = self.sheet_id(spreadsheet_id, sheet)
        tabs = self.sheets.get(
            spreadsheetId=spreadsheet_id,
            fields='sheets(properties.sheetId,conditionalFormats)').execute().get('sheets', [])
        n = next((len(t.get('conditionalFormats', [])) for t in tabs
                  if t['properties']['sheetId'] == sid), 0)
        if n:
            self._batch(spreadsheet_id, [{'deleteConditionalFormatRule': {'sheetId': sid, 'index': 0}}
                                         for _ in range(n)])
        return {'id': sid, 'removed_rules': n}
