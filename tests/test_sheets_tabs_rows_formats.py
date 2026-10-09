"""Onglets, lignes et formats d'un tableur Google : un seul transport, `batchUpdate`.

Signaux oto 1386/1384/1376 : `sheets_create` ne créait qu'un onglet au nom de la
locale (`Feuille 1`), écrire sur `'Prospects'!A1` donnait un 400 (l'onglet n'existait
pas), et rien ne savait ajouter, renommer ou supprimer un onglet, supprimer des lignes
ni poser un format de nombre. Ce que ce fichier verrouille :

1. `create(sheets=[…])` nomme les onglets à la création ;
2. chaque op compose UNE requête `batchUpdate`, avec l'onglet résolu par titre ou id ;
3. un titre absent ou en double est refusé en NOMMANT les onglets ;
4. les lignes sont 1-based et inclusives côté appelant, converties une fois ;
5. une plage A1 devient un GridRange exact, bornes ouvertes laissées ouvertes.
"""
from unittest.mock import MagicMock, patch

import pytest

from oto.tools.google.sheets.lib.sheets_client import (
    SheetsClient, SheetsClientError, _col_row)


def _client(tabs=None):
    with patch("oto.tools.google.sheets.lib.sheets_client.build"):
        client = SheetsClient(credentials=object())
    client.sheets.get.return_value.execute.return_value = {
        "spreadsheetId": "sid", "properties": {"title": "T"},
        "sheets": [{"properties": {"sheetId": i, "title": t}}
                   for i, t in enumerate(tabs or ["Feuille 1"])]}
    batch = client.sheets.batchUpdate
    batch.return_value.execute.return_value = {
        "replies": [{"addSheet": {"properties": {"sheetId": 42, "title": "Prospects",
                                                 "index": 1}}}]}
    return client, batch


def _requests(batch):
    return batch.call_args.kwargs["body"]["requests"]


# --- création avec onglets nommés -------------------------------------------------

def test_create_nomme_les_onglets_et_les_rend():
    client, _ = _client()
    client.sheets.create.return_value.execute.return_value = {
        "spreadsheetId": "sid", "spreadsheetUrl": "u", "properties": {"title": "BP"},
        "sheets": [{"properties": {"title": "Hypothèses"}}, {"properties": {"title": "P&L"}}]}
    out = client.create("BP", sheets=["Hypothèses", "P&L"])
    body = client.sheets.create.call_args.kwargs["body"]
    assert [s["properties"]["title"] for s in body["sheets"]] == ["Hypothèses", "P&L"]
    assert out["sheets"] == ["Hypothèses", "P&L"]


def test_create_sans_onglets_garde_le_corps_minimal():
    client, _ = _client()
    client.sheets.create.return_value.execute.return_value = {
        "spreadsheetId": "sid", "spreadsheetUrl": "u", "properties": {"title": "BP"}}
    client.create("BP")
    assert "sheets" not in client.sheets.create.call_args.kwargs["body"]


@pytest.mark.parametrize("titre", ["", "   ", "x" * 101])
def test_un_titre_d_onglet_vide_ou_trop_long_est_refuse_avant_l_appel(titre):
    client, batch = _client()
    with pytest.raises(SheetsClientError, match="1 to 100"):
        client.add_sheet("sid", titre)
    batch.assert_not_called()


# --- onglets ------------------------------------------------------------------------

def test_add_sheet_compose_une_requete_addSheet():
    client, batch = _client()
    out = client.add_sheet("sid", "Prospects", index=1)
    assert _requests(batch) == [{"addSheet": {"properties": {"title": "Prospects", "index": 1}}}]
    assert out == {"id": 42, "title": "Prospects", "index": 1}


def test_rename_sheet_resout_le_titre_puis_renomme():
    client, batch = _client(["Feuille 1", "Prospects"])
    out = client.rename_sheet("sid", "Prospects", "Leads")
    assert _requests(batch) == [{"updateSheetProperties": {
        "properties": {"sheetId": 1, "title": "Leads"}, "fields": "title"}}]
    assert out == {"id": 1, "title": "Leads"}


def test_delete_sheet_par_id_ne_lit_pas_les_metadonnees():
    client, batch = _client()
    client.delete_sheet("sid", 7)
    assert _requests(batch) == [{"deleteSheet": {"sheetId": 7}}]
    client.sheets.get.assert_not_called()


def test_un_onglet_absent_est_refuse_en_nommant_les_onglets():
    client, batch = _client(["Feuille 1", "Prospects"])
    with pytest.raises(SheetsClientError, match="no tab named 'Leads'.*'Feuille 1'.*'Prospects'"):
        client.delete_sheet("sid", "Leads")
    batch.assert_not_called()


def test_un_titre_en_double_exige_l_id():
    client, batch = _client(["Prospects", "Prospects"])
    with pytest.raises(SheetsClientError, match="2 tabs named 'Prospects'"):
        client.rename_sheet("sid", "Prospects", "Leads")
    batch.assert_not_called()


# --- lignes -------------------------------------------------------------------------

def test_delete_rows_est_1_based_inclusif_cote_appelant():
    client, batch = _client(["Feuille 1", "Prospects"])
    out = client.delete_rows("sid", "Prospects", 5, 9)
    assert _requests(batch) == [{"deleteDimension": {"range": {
        "sheetId": 1, "dimension": "ROWS", "startIndex": 4, "endIndex": 9}}}]
    assert out == {"id": 1, "deleted_rows": 5, "from_row": 5, "to_row": 9}


@pytest.mark.parametrize("start,end", [(0, 3), (5, 4)])
def test_des_bornes_de_lignes_incoherentes_sont_refusees(start, end):
    client, batch = _client()
    with pytest.raises(SheetsClientError, match="start_row >= 1"):
        client.delete_rows("sid", "Feuille 1", start, end)
    batch.assert_not_called()


# --- formats ------------------------------------------------------------------------

def test_number_format_pose_un_repeatCell_sur_la_plage_resolue():
    client, batch = _client(["Feuille 1", "P&L"])
    client.number_format("sid", "'P&L'!B2:D10", "#,##0.00", "NUMBER")
    assert _requests(batch) == [{"repeatCell": {
        "range": {"sheetId": 1, "startColumnIndex": 1, "startRowIndex": 1,
                  "endColumnIndex": 4, "endRowIndex": 10},
        "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "#,##0.00"}}},
        "fields": "userEnteredFormat.numberFormat"}}]


def test_une_plage_ouverte_laisse_les_bornes_ouvertes():
    client, batch = _client(["Feuille 1"])
    client.number_format("sid", "B:B", "0.0%", "percent")
    rng = _requests(batch)[0]["repeatCell"]["range"]
    assert rng == {"sheetId": 0, "startColumnIndex": 1, "endColumnIndex": 2}
    assert _requests(batch)[0]["repeatCell"]["cell"]["userEnteredFormat"]["numberFormat"]["type"] == "PERCENT"


def test_un_type_de_format_inconnu_est_refuse():
    client, batch = _client()
    with pytest.raises(SheetsClientError, match="type: one of"):
        client.number_format("sid", "A1", "0", "MONEY")
    batch.assert_not_called()


@pytest.mark.parametrize("cell,attendu", [
    ("A1", (0, 1)), ("B", (1, None)), ("5", (None, 5)), ("AA10", (26, 10)), ("z", (25, None)),
])
def test_col_row(cell, attendu):
    assert _col_row(cell) == attendu
