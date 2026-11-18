"""Charts embedded in a spreadsheet: list, create from a range, delete.

Composed into `SheetsClient`, which provides the transport (`_batch`, `sheet_id`,
`_grid_range`, `sheets`). Contract: `../sheets_client.py`.
"""
import builtins
from typing import Optional

from .._common import SheetsClientError, _col_row, _column_bounds, _split_range

#: Chart types offered → Google's `BasicChartType` (`pie` has its own spec).
_TYPES = {'column': 'COLUMN', 'bar': 'BAR', 'line': 'LINE', 'area': 'AREA',
          'scatter': 'SCATTER', 'pie': None}


class _ChartsMixin:
    def list_charts(self, spreadsheet_id: str) -> list:
        """Every chart of the spreadsheet: id, title, type, the tab it sits on."""
        tabs = self.sheets.get(
            spreadsheetId=spreadsheet_id,
            fields='sheets(properties(sheetId,title),charts(chartId,spec(title,'
                   'basicChart/chartType,pieChart/legendPosition)))').execute().get('sheets', [])
        out = []
        for tab in tabs:
            for chart in tab.get('charts', []):
                spec = chart.get('spec', {})
                kind = ('pie' if 'pieChart' in spec
                        else spec.get('basicChart', {}).get('chartType', '').lower() or None)
                out.append({'id': chart['chartId'], 'title': spec.get('title', ''),
                            'type': kind, 'sheet': tab['properties']['title']})
        return out

    def add_chart(self, spreadsheet_id: str, range: str, type: str = 'column',
                  title: Optional[str] = None, anchor: Optional[str] = None,
                  new_sheet: bool = False) -> dict:
        """A chart drawn from a range whose FIRST ROW holds the headers and FIRST COLUMN
        the categories (x axis, or the slices of a pie); every other column is a
        series (a pie takes one). `type`: column | bar | line | area | scatter | pie.

        Placed over the cell `anchor` (`'Tab'!H2`), or on a tab of its own with
        `new_sheet=True`; by default, beside the data on the data's tab."""
        kind = str(type).strip().lower()
        if kind not in _TYPES:
            raise SheetsClientError(f"type: one of {' | '.join(_TYPES)} (got {type!r})")
        if anchor and new_sheet:
            raise SheetsClientError("anchor or new_sheet, not both")
        grid = self._grid_range(spreadsheet_id, range)
        start, end = _column_bounds(grid, range)
        if end - start < 2:
            raise SheetsClientError(
                f"range {range!r}: at least two columns — the categories, then a series")
        if kind == 'pie' and end - start != 2:
            raise SheetsClientError(f"range {range!r}: a pie takes exactly two columns")
        column = lambda c: {'sourceRange': {'sources': [{**grid, 'startColumnIndex': c,
                                                         'endColumnIndex': c + 1}]}}
        if kind == 'pie':
            spec = {'pieChart': {'domain': column(start), 'series': column(start + 1),
                                 'legendPosition': 'RIGHT_LEGEND'}}
        else:
            spec = {'basicChart': {
                'chartType': _TYPES[kind], 'legendPosition': 'BOTTOM_LEGEND', 'headerCount': 1,
                'domains': [{'domain': column(start)}],
                'series': [{'series': column(c), 'targetAxis': 'LEFT_AXIS'}
                           for c in builtins.range(start + 1, end)]}}
        if title:
            spec['title'] = title
        if new_sheet:
            position = {'newSheet': True}
        else:
            at = (self._anchor(spreadsheet_id, anchor) if anchor else
                  {'sheetId': grid['sheetId'], 'rowIndex': grid.get('startRowIndex', 0),
                   'columnIndex': end + 1})
            position = {'overlayPosition': {'anchorCell': at}}
        reply = self._batch(spreadsheet_id, [{'addChart': {'chart': {
            'spec': spec, 'position': position}}}])['replies'][0]['addChart']['chart']
        return {'id': reply['chartId'], 'type': kind, 'title': title or '', 'range': range}

    def delete_chart(self, spreadsheet_id: str, chart_id: int) -> dict:
        """Delete a chart (its data stays). Irreversible: callers confirm first."""
        self._batch(spreadsheet_id, [{'deleteEmbeddedObject': {'objectId': int(chart_id)}}])
        return {'id': int(chart_id), 'deleted': True}

    def _anchor(self, spreadsheet_id: str, anchor: str) -> dict:
        """`'Tab'!H2` → the cell a chart's top-left corner sits on."""
        sheet, cell = _split_range(anchor)
        col, row = _col_row(cell)
        if not sheet or col is None or row is None or ':' in cell:
            raise SheetsClientError(f"anchor: one cell with its tab, e.g. 'Tab'!H2 (got {anchor!r})")
        sid = self.sheet_id(spreadsheet_id, sheet[:-1].strip("'").replace("''", "'"))
        return {'sheetId': sid, 'rowIndex': row - 1, 'columnIndex': col}
