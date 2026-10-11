"""Urbanisme client contract (IGN geocoder, API Carto Cadastre and GPU) — no network.

Replays answers recorded on 2026-10-10 for an address in a protected city centre
(geometries trimmed to a few points): geocoding, parcel under the point, the sixteen
GPU layers queried with the parcel outline, grouping of identical features, servitudes
linked to their generators, notes on what an empty answer means, input checks.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from oto.tools.common.errors import UpstreamHTTPError
from oto.tools.urbanisme import LAYERS, UrbanismeClient, UrbanismeNotFound, parse_idu
from oto.tools.urbanisme import client as urba
from oto.tools.urbanisme import projection as proj

FIXTURES = pathlib.Path(__file__).parent / "fixtures" / "urbanisme"
ADDRESS = "12 rue de la Monnaie 35000 Rennes"


def _fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


class _Resp:
    def __init__(self, status_code, body):
        self.status_code = status_code
        self._body = body
        self.content = b"x"
        self.text = json.dumps(body)

    def json(self):
        return self._body


@pytest.fixture()
def api(monkeypatch):
    """Fake upstream: geocoder and cadastre by GET, GPU layers by POST, from fixtures."""
    state = {"gets": [], "posts": [], "overrides": {}}

    def fake_get(self, url, params=None, **kwargs):
        state["gets"].append((url, dict(params or {})))
        if url.endswith("/geocodage/search"):
            return _Resp(200, state["overrides"].get("geocode", _fixture("geocode")))
        if url.endswith("/cadastre/parcelle"):
            return _Resp(200, state["overrides"].get("parcelle", _fixture("parcelle")))
        raise AssertionError(f"unexpected GET {url}")

    def fake_post(self, url, json=None, **kwargs):
        layer = url.rsplit("/", 1)[1]
        state["posts"].append((layer, json))
        if layer in state["overrides"]:
            status, body = state["overrides"][layer]
            return _Resp(status, body)
        return _Resp(200, _fixture(layer))

    monkeypatch.setattr(urba.requests.Session, "get", fake_get)
    monkeypatch.setattr(urba.requests.Session, "post", fake_post)
    return state


def _no_geometry(value, path="$"):
    if isinstance(value, dict):
        assert "coordinates" not in value or path == "$.location.point", path
        for k, v in value.items():
            _no_geometry(v, f"{path}.{k}")
    elif isinstance(value, list):
        for v in value:
            _no_geometry(v, path)


# --- parcel identifiers ------------------------------------------------------

def test_parse_idu_plain_municipality():
    assert parse_idu("35238000AC0680") == {
        "code_insee": "35238", "com_abs": "000", "section": "AC", "numero": "0680"}
    assert parse_idu(" 35238 000 ac 0680 ")["section"] == "AC"


@pytest.mark.parametrize("idu, city, arr", [
    ("75107000BQ0003", "75056", "107"),
    ("69381000AB0012", "69123", "381"),
    ("13201000AB0012", "13055", "201"),
])
def test_parse_idu_arrondissement_maps_to_city_and_arr(idu, city, arr):
    params = parse_idu(idu)
    assert params["code_insee"] == city and params["code_arr"] == arr


def test_parse_idu_corsica_and_invalid():
    assert parse_idu("2A004000AB0012")["code_insee"] == "2A004"
    for bad in ("35238AC0680", "35238000AC680", "", None):
        with pytest.raises(ValueError):
            parse_idu(bad)


# --- report ------------------------------------------------------------------

def test_report_by_address_queries_the_parcel_outline(api):
    r = UrbanismeClient().report(address=ADDRESS)

    loc = r["location"]
    assert loc["queried"] == "parcel" and loc["parcel"]["idu"] == "35238000AC0680"
    assert loc["parcel"]["area_m2"] == 1626 and loc["match_type"] == "housenumber"
    parcel_geom = _fixture("parcelle")["features"][0]["geometry"]
    layers = sorted(layer for layer, _ in api["posts"])
    assert layers == sorted(n for n in LAYERS if n != "acte-sup")
    assert all(body["geom"] == parcel_geom for _, body in api["posts"])

    assert r["municipalities"] == [{"insee": "35238", "name": "RENNES",
                                    "is_rnu": False, "is_deleted": False}]
    doc = r["documents"][0]
    assert doc["du_type"] == "PSMV" and doc["partition"] == "PSMV_35238"
    assert doc["page"].endswith("/document/by-id/" + doc["gpu_doc_id"])
    assert r["zones"][0]["zone_type"] == "U" and r["zones"][0]["count"] == 1
    _no_geometry(r)


def test_report_groups_identical_prescriptions(api):
    r = UrbanismeClient().report(address=ADDRESS)
    surf = len(_fixture("prescription-surf")["features"])
    pct = len(_fixture("prescription-pct")["features"])
    assert sum(p["count"] for p in r["prescriptions"]) == surf + pct
    assert len(r["prescriptions"]) < surf + pct
    assert {p["shape"] for p in r["prescriptions"]} == {"surface", "point"}
    assert all("regulation" in p and "document" in p for p in r["prescriptions"])


def test_report_links_servitude_footprints_and_generators(api):
    sups = UrbanismeClient().report(address=ADDRESS)["servitudes"]
    assert {s["category"] for s in sups} == {"AC1", "AC4"}
    for s in sups:
        assert len(s["footprints"]) == 1 and len(s["generators"]) == 1
        assert s["footprints"][0]["generator_id"] == s["generators"][0]["id"]
        assert s["id"] == s["generators"][0]["id"].rsplit("-", 1)[0]


def test_report_point_when_not_on_parcel(api):
    r = UrbanismeClient().report(address=ADDRESS, on_parcel=False)
    assert r["location"]["queried"] == "point" and "parcel" not in r["location"]
    point = _fixture("geocode")["features"][0]["geometry"]
    assert all(body["geom"] == point for _, body in api["posts"])
    assert not any(url.endswith("/cadastre/parcelle") for url, _ in api["gets"])


def test_report_by_idu_and_unknown_parcel(api):
    r = UrbanismeClient().report(idu="35238000AC0680")
    assert r["location"] == {"source": "parcel", "queried": "parcel",
                             "parcel": r["location"]["parcel"]}
    assert api["gets"][0][1]["section"] == "AC"

    api["overrides"]["parcelle"] = {"type": "FeatureCollection", "features": []}
    with pytest.raises(UrbanismeNotFound):
        UrbanismeClient().report(idu="35238000AC9999")


def test_report_unknown_address(api):
    api["overrides"]["geocode"] = {"type": "FeatureCollection", "features": []}
    with pytest.raises(UrbanismeNotFound):
        UrbanismeClient().report(address="nowhere at all")
    assert api["posts"] == []


def test_report_sup_categories_one_query_per_category(api):
    UrbanismeClient().report(geom={"type": "Point", "coordinates": [-1.68, 48.11]},
                             sup_categories=["ac1", " pm1 "])
    sup = [(layer, body["categorie"]) for layer, body in api["posts"] if "sup" in layer]
    assert len(sup) == 12 and {c for _, c in sup} == {"AC1", "PM1"}
    assert all("categorie" not in body for layer, body in api["posts"] if "sup" not in layer)


def test_report_needs_exactly_one_place(api):
    for kwargs in ({}, {"address": ADDRESS, "idu": "35238000AC0680"}):
        with pytest.raises(ValueError):
            UrbanismeClient().report(**kwargs)
    with pytest.raises(ValueError):
        UrbanismeClient().report(geom={"type": "LineString", "coordinates": [[0, 0], [1, 1]]})
    assert api["posts"] == [] and api["gets"] == []


def test_upstream_400_is_typed(api):
    api["overrides"]["zone-urba"] = (400, {"code": 400, "message": {"geom": {
        "msg": "Parse error on line 1"}}})
    with pytest.raises(UpstreamHTTPError) as exc:
        UrbanismeClient().layer("zone-urba", geom={"type": "Point", "coordinates": [0, 0]})
    assert exc.value.status_code == 400 and "Parse error" in str(exc.value)


# --- layer -------------------------------------------------------------------

def test_layer_refuses_what_the_api_would_widen(api):
    c = UrbanismeClient()
    with pytest.raises(ValueError):
        c.layer("zonage", geom={"type": "Point", "coordinates": [0, 0]})
    with pytest.raises(ValueError):          # unfiltered = the whole national layer
        c.layer("zone-urba")
    with pytest.raises(ValueError):          # categorie is ignored outside SUP layers
        c.layer("zone-urba", partition="DU_35238", categorie="AC1")
    with pytest.raises(ValueError):
        c.layer("document", insee="35238")
    assert api["posts"] == []
    c.layer("municipality", insee="35238")
    c.layer("assiette-sup-s", partition="172014607_SUP_35_AC4", categorie="AC4")
    assert [b for _, b in api["posts"]] == [
        {"insee": "35238"}, {"partition": "172014607_SUP_35_AC4", "categorie": "AC4"}]


# --- projection --------------------------------------------------------------

def test_notes_say_what_an_empty_answer_means():
    not_rnu = [{"insee": "12033", "is_rnu": False}]
    assert "not under the RNU" in proj.notes(not_rnu, [])[0]
    assert "is under the RNU" in proj.notes([{"is_rnu": True}], [])[0]
    assert len(proj.notes(not_rnu, [{"name": "x"}])) == 1


def test_mis_decoded_text_is_repaired():
    fc = {"features": [{"properties": {
        "suptype": "ac1", "nomsuplitt": "HÃ´tel de Bourbon CondÃ© (ancien)",
        "idgen": "AC1-1-2-1", "typeass": "Périmètre des abords"}}]}
    sup = proj.servitudes({"surface": fc}, {})[0]
    assert sup["name"] == "Hôtel de Bourbon Condé (ancien)"
    assert sup["footprints"][0]["type"] == "Périmètre des abords"
