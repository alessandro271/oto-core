"""Ce qu'une méthode qui PAGINE a coûté chez Serper.

`census_maps` et `reviews_all` enchaînent plusieurs requêtes. Tulina facture au crédit
Serper consommé (0,1 crédit Tulina par crédit Serper, 10/09/2026) : le consommateur a
besoin de la somme des crédits que Serper a DÉDUITS, pas du nombre de pages — une page
Maps à 100 résultats ou un scrape difficile ne coûtent pas un crédit.
"""
from __future__ import annotations

from oto.tools.serper.client import SerperClient
import pytest


def _client() -> SerperClient:
    return SerperClient(api_key="k")


def test_census_sums_the_credits_serper_reported_on_each_page():
    c = _client()
    pages = iter([
        {"places": [{"cid": "a"}, {"cid": "b"}], "credits": 2},
        {"places": [{"cid": "c"}], "credits": 2},
        {"places": [], "credits": 1},
    ])
    c.search_maps = lambda **kw: next(pages)
    out = c.census_maps(query="laverie", ll_anchors=["@45.76,4.83,14z"], max_pages=3)
    assert out["pages_fetched"] == 3
    assert out["credits_used"] == 5
    assert out["count"] == 3


def test_census_falls_back_to_one_credit_per_page_when_serper_says_nothing():
    c = _client()
    pages = iter([{"places": [{"cid": "a"}]}, {"places": []}])
    c.search_maps = lambda **kw: next(pages)
    out = c.census_maps(query="laverie", ll_anchors=["@45.76,4.83,14z"], max_pages=3)
    assert (out["pages_fetched"], out["credits_used"]) == (2, 2)


def test_reviews_all_sums_the_credits_serper_reported_on_each_page():
    c = _client()
    pages = iter([
        {"reviews": [{"id": 1}] * 10, "nextPageToken": "t1", "credits": 1},
        {"reviews": [{"id": 2}] * 10, "nextPageToken": "t2", "credits": 1},
        {"reviews": [{"id": 3}] * 4, "credits": 1},
    ])
    c.search_reviews = lambda **kw: next(pages)
    out = c.reviews_all(cid="123", max_reviews=200)
    assert (out["pages_fetched"], out["credits_used"], out["count"]) == (3, 3, 24)


def test_a_malformed_credits_field_counts_as_one_never_as_zero_or_a_crash():
    for res in ({"credits": None}, {"credits": "2"}, {"credits": True}, {"credits": -1}, "x"):
        assert SerperClient._credits_of(res) == 1
    assert SerperClient._credits_of({"credits": 0}) == 0
    assert SerperClient._credits_of({"credits": 10}) == 10


class _Redirige:
    """Une 3xx vers un autre hôte, dont le `Location` garde la clé en query."""
    status_code = 302
    headers = {"Location": "https://ailleurs.test/v1/x?api_key=SECRET#f"}
    content = b""
    text = ""
    ok = False

    def json(self):
        return {}

    def raise_for_status(self):
        return None


def test_une_redirection_est_refusee_jamais_suivie(monkeypatch):
    """La clé part dans un en-tête maison que `requests` ne retire pas sur un changement
    d'hôte : une 3xx est refusée (`RedirectRefused`), jamais suivie ni retentée, et
    sa cible est réduite à schéma, hôte et chemin — jamais sa query."""
    from oto.tools.http.client import RedirectRefused
    vus = []

    def fake(url, **kw):
        vus.append(kw)
        return _Redirige()

    c = SerperClient(api_key="k")
    c.session.post = fake
    with pytest.raises(RedirectRefused) as e:
        c._post("https://google.serper.dev/search", {"q": "x"}, "search")
    assert vus[0]["allow_redirects"] is False
    assert e.value.location == "https://ailleurs.test/v1/x"
    assert "SECRET" not in str(e.value)
    assert len(vus) == 1
