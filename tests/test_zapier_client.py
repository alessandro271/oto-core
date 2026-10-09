"""Client Zapier : la clé `x-api-key` ne suit jamais une redirection.

Aucun réseau : le transport est doublé."""
from __future__ import annotations

import pytest

from oto.tools.zapier import client as mod

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

    def fake(method, url, **kw):
        vus.append(kw)
        return _Redirige()

    c = mod.ZapierClient(api_key="k")
    c.session.request = fake
    with pytest.raises(RedirectRefused) as e:
        c.list_actions()
    assert vus[0]["allow_redirects"] is False
    assert e.value.location == "https://ailleurs.test/v1/x"
    assert "SECRET" not in str(e.value)
    assert len(vus) == 1
