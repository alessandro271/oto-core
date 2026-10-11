"""Contrat du client des annonces BODACC — sans réseau.

Mocke `requests.Session.get` : la clause ODSQL composée (et l'échappement des
guillemets), les refus avant tout appel, le plafond de pagination, l'aplatissement
d'une annonce par famille, le regroupement et ses alias, l'annonce introuvable.
"""
from __future__ import annotations

import json

import pytest

from oto.tools.bodacc import notices as bodacc
from oto.tools.bodacc import BodaccNoticesClient, BodaccPayloadError, BodaccQueryError
from oto.tools.common.errors import UpstreamHTTPError


class _Resp:
    def __init__(self, status_code: int, body):
        self.status_code = status_code
        self._body = body
        self.content = b"x"
        self.text = str(body)

    def json(self):
        return self._body


_COLLECTIVE = {
    "id": "A1", "dateparution": "2026-10-09", "familleavis": "collective",
    "familleavis_lib": "Procédures collectives", "typeavis": "annonce",
    "registre": ["811 038 504", "811038504"], "commercant": "ACME",
    "ville": "Paris", "cp": "75001", "numerodepartement": "75",
    "tribunal": "TAE de Paris", "url_complete": "https://example.invalid/A1",
    "jugement": json.dumps({"nature": "Jugement d'ouverture", "date": "2026-09-23",
                            "complementJugement": "Liquidation judiciaire."}),
    "acte": None,
}

_DPC = {
    "id": "C2", "dateparution": "2026-10-08", "familleavis": "dpc",
    "registre": ["123456789"],
    "depot": json.dumps({"dateCloture": "2025-12-31", "typeDepot": "Comptes annuels"}),
}

_VENTE = {
    # Une vente : le registre porte le cédant ET l'acquéreur (80 ventes sur 100 mesurées
    # le 09/10/2026), et `commercant` concatène les deux noms.
    "id": "B3", "familleavis": "vente", "registre": ["109223321", "109 223 321",
                                                     "799641303", "799 641 303"],
    "commercant": "HANUMAAN, FORMIDABLE", "region_nom_officiel": "Provence-Alpes-Côte d'Azur",
    "acte": json.dumps({"vente": {"categorieVente": "Achat d'un fonds"}}),
    "listepersonnes": json.dumps({"personne": {
        "typePersonne": "pm", "denomination": "HANUMAAN",
        "numeroImmatriculation": {"numeroIdentification": "109 223 321"},
        "formeJuridique": "Société par actions simplifiée",
        "capital": {"montantCapital": "5000.00", "devise": "EUR"},
        "adresseSiegeSocial": {"numeroVoie": "30", "typeVoie": "Rue", "nomVoie": "Pertinax",
                               "codePostal": "06000", "ville": "Nice"}}}),
    "listeprecedentproprietaire": json.dumps({"personne": {
        "typePersonne": "pm", "denomination": "FORMIDABLE",
        "numeroImmatriculation": {"numeroIdentification": "799 641 303"}}}),
    "listeetablissements": json.dumps({"etablissement": [{"activite": "boulangerie"}]}),
}

_COLLECTIVE_PP = {
    # Une procédure collective d'une personne physique : l'activité est dans
    # `listepersonnes.personne`, jamais dans `listeetablissements` (vide, 100/100).
    "id": "D4", "familleavis": "collective", "registre": None,
    "commercant": "DAVID, Alexandre (EI)",
    "listepersonnes": json.dumps({"personne": {
        "typePersonne": "pp", "nom": "DAVID", "prenom": "Alexandre",
        "activite": "Travaux de maçonnerie générale",
        "adressePP": {"numeroVoie": "30", "typeVoie": "rue", "nomVoie": "d'Ourscamp",
                      "codePostal": "02290", "ville": "Saint-Christophe-à-Berry"}}}),
    "listeetablissements": None,
}


@pytest.fixture()
def api(monkeypatch):
    state = {"calls": [], "body": {"total_count": 0, "results": []}, "http": 200}

    def fake_get(self, url, **kwargs):
        state["calls"].append({"url": url, "params": kwargs["params"]})
        return _Resp(state["http"], state["body"])

    monkeypatch.setattr(bodacc.requests.Session, "get", fake_get)
    return state


def test_where_compose_tous_les_filtres():
    clause = BodaccNoticesClient.where(
        q="liquidation", famille="collective", departement="2a",
        date_from="2026-10-01", date_to="2026-10-09", commercant="ACME",
        ville="Lyon", tribunal="Paris", type_avis="annonce", siren="811 038 504")
    assert clause == (
        'search("liquidation") AND familleavis="collective" AND numerodepartement="2A" '
        'AND dateparution>="2026-10-01" AND dateparution<="2026-10-09" '
        'AND search(commercant, "ACME") AND search(ville, "Lyon") '
        'AND search(tribunal, "Paris") AND typeavis="annonce" AND registre="811038504"')


def test_where_sans_filtre_rend_none():
    assert BodaccNoticesClient.where() is None


def test_guillemets_et_antislash_echappes():
    clause = BodaccNoticesClient.where(commercant='A"B\\C')
    assert clause == 'search(commercant, "A\\"B\\\\C")'


@pytest.mark.parametrize("kwargs", [
    {"famille": "procedure_collective"},
    {"departement": "7"},
    {"date_from": "09/10/2026"},
    {"date_from": "2026-13-45"},                              # la forme passe, pas le calendrier
    {"date_from": "2026-10-09", "date_to": "2026-10-01"},     # fenêtre vide
    {"type_avis": "initial"},
    {"siren": "12345"},
])
def test_valeur_inconnue_refusee_avant_appel(api, kwargs):
    with pytest.raises(BodaccQueryError):
        BodaccNoticesClient().search(**kwargs)
    assert api["calls"] == []


def test_plafond_de_pagination_refuse(api):
    with pytest.raises(BodaccQueryError, match="10000"):
        BodaccNoticesClient().search(limit=100, offset=9950)
    with pytest.raises(BodaccQueryError):
        BodaccNoticesClient().search(limit=101)
    assert api["calls"] == []


def test_next_offset_n_annonce_jamais_une_page_que_le_plafond_refuse(api):
    api["body"] = {"total_count": 20_000, "results": [_COLLECTIVE] * 50}
    # 9 920 + 50 = 9 970 : l'appel suivant (9 970 + 50 > 10 000) serait refusé → None.
    assert BodaccNoticesClient().search(limit=50, offset=9920)["next_offset"] is None
    # 9 900 + 50 = 9 950 : l'appel suivant tient dans le plafond → annoncé.
    assert BodaccNoticesClient().search(limit=50, offset=9900)["next_offset"] == 9950


def test_search_aplatit_et_pagine(api):
    api["body"] = {"total_count": 3, "results": [_COLLECTIVE, _DPC]}
    out = BodaccNoticesClient().search(famille="collective", limit=2)
    call = api["calls"][0]
    assert call["url"].endswith("/annonces-commerciales/records")
    assert call["params"] == {"limit": 2, "offset": 0, "order_by": "dateparution desc",
                              "where": 'familleavis="collective"'}
    assert out["total_count"] == 3 and out["next_offset"] == 2
    first, second = out["notices"]
    assert first["siren"] == "811038504"
    assert first["parties"] == [{"siren": "811038504", "role": "indeterminee"}]
    assert first["jugement_nature"] == "Jugement d'ouverture"
    assert first["resume"] == "Liquidation judiciaire."
    assert second["date_cloture"] == "2025-12-31"
    assert second["resume"] == "Comptes annuels"


def test_derniere_page_sans_next_offset(api):
    api["body"] = {"total_count": 2, "results": [_COLLECTIVE, _DPC]}
    assert BodaccNoticesClient().search(limit=2)["next_offset"] is None


def test_une_vente_ne_choisit_pas_un_siren_au_hasard(api):
    api["body"] = {"total_count": 1, "results": [_VENTE]}
    line = BodaccNoticesClient().search()["notices"][0]
    assert line["siren"] is None                       # deux parties : jamais l'une au hasard
    assert line["parties"] == [{"siren": "109223321", "role": "titulaire"},
                               {"siren": "799641303", "role": "ancien_proprietaire"}]
    assert line["resume"] == "Achat d'un fonds"
    assert line["activite"] == "boulangerie"           # l'établissement, faute de personne.activite
    assert line["denomination"] == "HANUMAAN"
    assert line["forme_juridique"] == "Société par actions simplifiée"
    assert line["capital"] == "5000.00"
    assert line["adresse_siege"] == "30 Rue Pertinax 06000 Nice"
    assert line["region"] == "Provence-Alpes-Côte d'Azur"


def test_un_siren_du_registre_hors_de_tout_bloc_est_indetermine(api):
    rec = dict(_VENTE, listeprecedentproprietaire=None)
    api["body"] = {"total_count": 1, "results": [rec]}
    line = BodaccNoticesClient().search()["notices"][0]
    assert line["parties"][1] == {"siren": "799641303", "role": "indeterminee"}


def test_l_activite_vient_de_la_personne_pas_de_l_etablissement(api):
    api["body"] = {"total_count": 1, "results": [_COLLECTIVE_PP]}
    line = BodaccNoticesClient().search()["notices"][0]
    assert line["activite"] == "Travaux de maçonnerie générale"
    assert line["adresse_siege"] == "30 rue d'Ourscamp 02290 Saint-Christophe-à-Berry"
    assert line["siren"] is None and line["parties"] == []


def test_un_champ_json_illisible_leve_au_lieu_de_vider_les_colonnes(api):
    api["body"] = {"total_count": 1, "results": [dict(_COLLECTIVE, jugement="{pas du json")]}
    with pytest.raises(BodaccPayloadError, match="A1.*jugement"):
        BodaccNoticesClient().search()
    with pytest.raises(BodaccPayloadError):
        BodaccNoticesClient().get("A1")


def test_raw_rend_les_champs_json_parses(api):
    api["body"] = {"total_count": 1, "results": [_COLLECTIVE]}
    notice = BodaccNoticesClient().search(raw=True)["notices"][0]
    assert notice["jugement"]["date"] == "2026-09-23"


def test_get_introuvable_rend_none(api):
    assert BodaccNoticesClient().get("NOPE") is None
    assert api["calls"][0]["params"] == {"where": 'id="NOPE"', "limit": 1}


def test_get_retire_les_champs_nuls(api):
    api["body"] = {"total_count": 1, "results": [_COLLECTIVE]}
    notice = BodaccNoticesClient().get("A1")
    assert "acte" not in notice and notice["jugement"]["nature"] == "Jugement d'ouverture"


def test_count_groupe_par_alias(api):
    api["body"] = {"total_count": 2, "results": [{"cle": "dpc", "n": 10},
                                                 {"cle": "collective", "n": 3}]}
    out = BodaccNoticesClient().count("famille", limit=2, date_from="2026-10-01")
    params = api["calls"][0]["params"]
    assert params["select"] == "count(*) as n"
    assert params["group_by"] == "familleavis as cle"
    assert params["order_by"] == "n desc"
    assert out["groups"][1] == {"key": "collective", "count": 3,
                                "label": "Procédures collectives"}
    assert out["notices_counted"] == 13 and out["truncated"] is True


def test_count_par_mois_chronologique(api):
    BodaccNoticesClient().count("mois")
    params = api["calls"][0]["params"]
    assert params["group_by"] == "date_format(dateparution, 'yyyy-MM') as cle"
    assert params["order_by"] == "cle asc"


def test_count_regroupement_inconnu_refuse(api):
    with pytest.raises(BodaccQueryError, match="group_by"):
        BodaccNoticesClient().count("naf")
    assert api["calls"] == []


def test_refus_amont_type(api):
    api["http"] = 400
    api["body"] = {"error_code": "ODSQLSyntaxError", "message": "bad"}
    with pytest.raises(UpstreamHTTPError):
        BodaccNoticesClient().search()
