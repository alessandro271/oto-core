"""Tabs and their structure: add, rename, delete, copy, freeze; rows and columns
deleted, inserted, hidden.

Composed into `SheetsClient`, which provides the transport (`_batch`, `sheet_id`,
`_grid_range`, `sheets`). Contract: `../sheets_client.py`.
"""
from typing import Optional

from .._common import (SheetsClientError, _column_index, _column_letters, _count,
                       _tab_title)


class _TabsMixin:
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

    def copy_sheet(self, spreadsheet_id: str, sheet, to_spreadsheet_id: Optional[str] = None,
                   title: Optional[str] = None, index: Optional[int] = None) -> dict:
        """Copy a tab — values, formats, widths, frozen rows, validations, conditional
        formats — into `to_spreadsheet_id` (the same spreadsheet by default).

        The source is only READ (`sheets.copyTo` needs view access on it): a shared
        template stays untouched. Google names the copy `Copy of …` in the account's
        locale; `title` renames it, `index` moves it (0-based)."""
        sid = self.sheet_id(spreadsheet_id, sheet)
        dest = to_spreadsheet_id or spreadsheet_id
        new_title = _tab_title(title) if title is not None else None
        copied = self.sheets.sheets().copyTo(
            spreadsheetId=spreadsheet_id, sheetId=sid,
            body={'destinationSpreadsheetId': dest}).execute()
        props: dict = {'sheetId': copied['sheetId']}
        if new_title is not None:
            props['title'] = new_title
        if index is not None:
            props['index'] = int(index)
        if len(props) > 1:
            fields = ','.join(k for k in ('title', 'index') if k in props)
            self._batch(dest, [{'updateSheetProperties': {'properties': props,
                                                          'fields': fields}}])
        return {'spreadsheet_id': dest, 'id': copied['sheetId'],
                'title': new_title or copied['title'],
                'index': props.get('index', copied.get('index'))}

    def freeze(self, spreadsheet_id: str, sheet, rows: Optional[int] = None,
               cols: Optional[int] = None) -> dict:
        """Freeze the first `rows` rows and/or `cols` columns of a tab (0 unfreezes)."""
        grid: dict = {}
        for key, value in (('frozenRowCount', rows), ('frozenColumnCount', cols)):
            if value is not None:
                if int(value) < 0:
                    raise SheetsClientError(f"freeze: a count >= 0 (got {value!r})")
                grid[key] = int(value)
        if not grid:
            raise SheetsClientError("freeze: give rows and/or cols")
        sid = self.sheet_id(spreadsheet_id, sheet)
        self._batch(spreadsheet_id, [{'updateSheetProperties': {
            'properties': {'sheetId': sid, 'gridProperties': grid},
            'fields': ','.join(f'gridProperties.{k}' for k in grid)}}])
        return {'id': sid, 'frozen_rows': grid.get('frozenRowCount'),
                'frozen_cols': grid.get('frozenColumnCount')}

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

    def delete_columns(self, spreadsheet_id: str, sheet, start_column: str,
                       end_column: str) -> dict:
        """Delete columns `start_column`..`end_column` INCLUSIVE, as letters (`C`, `AB`);
        the columns to the right move left. Irreversible: callers confirm first."""
        start, end = _column_index(start_column), _column_index(end_column)
        if end < start:
            raise SheetsClientError(
                f"columns: end_column at or after start_column (got {start_column}..{end_column})")
        sid = self.sheet_id(spreadsheet_id, sheet)
        self._batch(spreadsheet_id, [{'deleteDimension': {'range': {
            'sheetId': sid, 'dimension': 'COLUMNS', 'startIndex': start, 'endIndex': end + 1}}}])
        return {'id': sid, 'deleted_columns': end - start + 1,
                'from_column': _column_letters(start), 'to_column': _column_letters(end)}

    def insert_rows(self, spreadsheet_id: str, sheet, before_row: int, count: int) -> dict:
        """Insert `count` empty rows before row `before_row` (1-based); they take the
        format of the row above."""
        at, n = int(before_row), _count(count)
        if at < 1:
            raise SheetsClientError(f"start_row: >= 1 (got {before_row!r})")
        sid = self.sheet_id(spreadsheet_id, sheet)
        self._insert(spreadsheet_id, sid, 'ROWS', at - 1, n)
        return {'id': sid, 'inserted_rows': n, 'from_row': at, 'to_row': at + n - 1}

    def insert_columns(self, spreadsheet_id: str, sheet, before_column: str, count: int) -> dict:
        """Insert `count` empty columns before column `before_column` (a letter); they
        take the format of the column to the left."""
        at, n = _column_index(before_column), _count(count)
        sid = self.sheet_id(spreadsheet_id, sheet)
        self._insert(spreadsheet_id, sid, 'COLUMNS', at, n)
        return {'id': sid, 'inserted_columns': n, 'from_column': _column_letters(at),
                'to_column': _column_letters(at + n - 1)}

    def _insert(self, spreadsheet_id: str, sid: int, dimension: str, start: int, n: int):
        self._batch(spreadsheet_id, [{'insertDimension': {
            'range': {'sheetId': sid, 'dimension': dimension,
                      'startIndex': start, 'endIndex': start + n},
            'inheritFromBefore': start > 0}}])

    def set_hidden(self, spreadsheet_id: str, range: str, hidden: bool) -> dict:
        """Hide or show whole rows (`'Tab'!5:9`) or whole columns (`'Tab'!C:E`)."""
        dimension, start, end, grid = self._dimension(spreadsheet_id, range)
        self._batch(spreadsheet_id, [{'updateDimensionProperties': {
            'range': {'sheetId': grid['sheetId'], 'dimension': dimension,
                      'startIndex': start, 'endIndex': end},
            'properties': {'hiddenByUser': bool(hidden)}, 'fields': 'hiddenByUser'}}])
        return {'range': range, dimension.lower(): end - start, 'hidden': bool(hidden)}

    def _dimension(self, spreadsheet_id: str, range: str) -> tuple:
        """Whole rows or whole columns, never a block: hiding `B2:C3` has no meaning."""
        grid = self._grid_range(spreadsheet_id, range)
        cols = 'startColumnIndex' in grid
        rows = 'startRowIndex' in grid
        if cols and not rows:
            return 'COLUMNS', grid['startColumnIndex'], grid['endColumnIndex'], grid
        if rows and not cols:
            return 'ROWS', grid['startRowIndex'], grid['endRowIndex'], grid
        raise SheetsClientError(
            f"range {range!r}: whole rows ('Tab'!5:9) or whole columns ('Tab'!C:E), not a block")
