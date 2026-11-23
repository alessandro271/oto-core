"""La description `fod` 1.10.0 : les routes urbanisme et conventions collectives du service
que la description ne disait pas entrent en lecture seule, lues sur le service à a7cb702.

Quartiers prioritaires (QPV, par commune et près d'un point), EPFIF, statistiques
communales INSEE Mélodi (un bloc par appel, les cinq blocs en valeurs fermées), recensement
à l'IRIS, maires et présidents d'EPCI, liste des règlements que FOD détient et texte entier
de l'un d'eux, rendu en fichier texte. Les conventions collectives (KALI) rejoignent `law_`,
comme les codes. Le service répond 500 à une recherche de maires sans commune ni
département : le schéma d'entrée en exige un.
"""
from __future__ import annotations

import copy

import jsonschema
import yaml

from fabrique.descriptions import CONNECTORS, check

FOD = CONNECTORS / "fod" / "connector.yaml"
ROUTES = {
    "urban_list_cached_regulations": ("GET", "/api/reglements"),
    "urban_get_regulation_text": ("GET", "/api/reglements/{idurba}/raw"),
    "urban_list_priority_districts": ("GET", "/api/urba/qpv/{code_insee}"),
    "urban_list_priority_districts_near_point": ("GET", "/api/urba/qpv/near"),
    "urban_get_land_agency_intervention": ("GET", "/api/urba/epfif/{code_insee}"),
    "urban_get_commune_statistics": ("GET", "/api/urba/insee/{code_insee}/{block}"),
    "urban_get_iris_census": ("GET", "/api/urba/iris/by_iris/{code}"),
    "urban_list_commune_iris_census": ("GET", "/api/urba/iris/by_commune/{code}"),
    "urban_list_mayors": ("GET", "/api/urba/elus/maires"),
    "urban_list_epci_presidents": ("GET", "/api/urba/elus/presidents-epci"),
    "law_list_collective_agreements": ("GET", "/api/ccn/conventions"),
    "law_search_collective_agreement_articles": ("GET", "/api/ccn/search"),
    "law_get_collective_agreement_article": ("GET", "/api/ccn/article/{kali_id}"),
}
LOOKUPS = ("urban_get_land_agency_intervention", "urban_get_iris_census", "urban_list_commune_iris_census",
           "law_get_collective_agreement_article")


def _description() -> dict:
    return copy.deepcopy(yaml.safe_load(FOD.read_text(encoding="utf-8")))


def _functions() -> dict[str, dict]:
    return {f["name"]: f for f in _description()["functions"]}


def _accepts(name: str, arguments: dict) -> bool:
    return jsonschema.Draft202012Validator(_functions()[name]["input"]).is_valid(arguments)


def test_the_description_is_version_1_10_0_or_later_and_passes_the_fabrique():
    description = _description()
    major, minor, _ = (int(n) for n in description["connector"]["version"].split("."))
    assert (major, minor) >= (1, 10)
    check(description, FOD)


def test_each_function_is_a_read_on_its_route():
    functions = _functions()
    for name, (method, path) in ROUTES.items():
        function = functions[name]
        assert function["class"] == "read", name
        assert function.get("act", False) is False, name
        assert (function["call"]["method"], function["call"]["path"]) == (method, path), name


def test_every_urbanisme_and_collective_agreement_route_of_the_service_is_described():
    paths = {f["call"]["path"] for f in _functions().values() if "call" in f}
    assert {path for _, path in ROUTES.values()} <= paths


def test_collective_agreements_sit_with_the_law():
    assert all(name.startswith("law_") for name in ROUTES if "collective_agreement" in name)


def test_a_lookup_that_answers_empty_has_a_named_refusal():
    functions = _functions()
    for name in LOOKUPS:
        function = functions[name]
        codes = {r["code"] for r in function["refusals"]}
        assert function["expect"] and {e["refusal"] for e in function["expect"]} <= codes, name


def test_the_statistics_block_is_a_closed_value():
    blocks = _functions()["urban_get_commune_statistics"]["input"]["properties"]["block"]["enum"]
    assert blocks == ["population", "familles", "personnes_seules", "revenus", "logement"]
    assert _accepts("urban_get_commune_statistics", {"code_insee": "13201", "block": "revenus"})
    assert not _accepts("urban_get_commune_statistics", {"code_insee": "13201", "block": "emploi"})


def test_a_mayor_lookup_needs_a_commune_or_a_department():
    assert not _accepts("urban_list_mayors", {})
    assert _accepts("urban_list_mayors", {"code_commune": "33063"})
    assert _accepts("urban_list_mayors", {"departement": "2A"})
    assert not _accepts("urban_list_mayors", {"departement": "33", "limit": 1001})
    assert _accepts("urban_list_epci_presidents", {})


def test_the_qpv_radius_is_bounded():
    point = {"lon": 3.1746, "lat": 50.6942}
    assert _accepts("urban_list_priority_districts_near_point", {**point, "radius_m": 300})
    assert not _accepts("urban_list_priority_districts_near_point", {**point, "radius_m": 0})
    assert not _accepts("urban_list_priority_districts_near_point", {**point, "radius_m": 10001})


def test_an_iris_code_has_nine_characters_and_a_commune_five():
    assert _accepts("urban_get_iris_census", {"code": "2A0040000"})
    assert not _accepts("urban_get_iris_census", {"code": "13201"})
    assert _accepts("urban_list_commune_iris_census", {"code": "75112"})
    assert not _accepts("urban_list_commune_iris_census", {"code": "132010101"})


def test_the_whole_regulation_comes_back_as_a_text_file():
    function = _functions()["urban_get_regulation_text"]
    assert function["output"]["file"]["from"] == "body"
    assert function["output"]["file"]["types"] == {"txt": ["text/plain"]}
    assert {r["code"]: r["when"] for r in function["refusals"]} == {"regulation_not_held": 404}
    assert set(function["input"]["properties"]) == {"idurba"}


def test_the_always_empty_zones_of_the_regulation_list_are_stripped():
    assert _functions()["urban_list_cached_regulations"]["output"]["strip"] == ["reglements.zones"]


def test_collective_agreement_identifiers_are_closed():
    assert not _accepts("law_get_collective_agreement_article", {"kali_id": "KALICONT000005635384"})
    assert not _accepts("law_list_collective_agreements", {"idcc": "148"})
    assert not _accepts("law_search_collective_agreement_articles", {"query": "congés", "sort": "date"})
