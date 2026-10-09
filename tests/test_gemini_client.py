"""Client Gemini : la clé voyage dans l'URL (`?key=`) et ne suit jamais une redirection.

Aucun réseau : le transport est doublé."""
from __future__ import annotations

import pytest

from oto.tools.gemini import client as mod

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
    """La clé part dans un paramètre de requête que `requests` ne retire pas sur un changement
    d'hôte : une 3xx est refusée (`RedirectRefused`), jamais suivie ni retentée, et
    sa cible est réduite à schéma, hôte et chemin — jamais sa query."""
    from oto.tools.http.client import RedirectRefused
    vus = []

    def fake(url, **kw):
        vus.append(kw)
        return _Redirige()

    c = mod.GeminiClient(api_key="k")
    monkeypatch.setattr(mod.requests, "post", fake)
    with pytest.raises(RedirectRefused) as e:
        c._post(c._url("m", "generateContent"), {}, 60)
    assert vus[0]["allow_redirects"] is False
    assert e.value.location == "https://ailleurs.test/v1/x"
    assert "SECRET" not in str(e.value)
    assert len(vus) == 1


def test_tout_post_passe_par_le_transport_unique():
    """Trois appels, un seul `requests.post` : la parade vit à un endroit."""
    import inspect
    assert inspect.getsource(mod).count("requests.post(") == 1
