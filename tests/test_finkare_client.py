"""La clé Finkare porte son environnement — et c'est ce qui protège les vraies créances.

Finkare préfixe ses clés : `fk_test_…` pour la sandbox, `fk_live_…` pour la production.
Le client en DÉRIVE son URL de base au lieu de la recevoir en paramètre, et ce fichier
garde cette dérivation.

⚠️ **Ce qu'on évite n'est pas une erreur de configuration, c'est une relance envoyée à
un vrai débiteur depuis un essai.** Si l'adresse et la clé étaient deux réglages
indépendants, un couple (clé de test, URL de prod) serait refusé par le serveur — mais
le couple inverse (clé live, URL sandbox) ne l'est pas forcément, et surtout rien
n'empêcherait une clé live d'être posée pendant qu'on croit travailler sur la sandbox.

⚠️ **Un préfixe inconnu vaut PRODUCTION.** C'est délibéré : se replier sur la sandbox
sur une clé qu'on ne reconnaît pas ferait travailler dans le vide un appelant persuadé
d'agir — l'échec silencieux le plus coûteux de cette API, puisque rien n'échoue.
"""
import pytest

from oto.tools.finkare import FinkareClient
from oto.tools.finkare import client as fk_mod

SANDBOX = "https://api-sandbox.finkare.io/api/v1"
PROD = "https://api.finkare.io/api/v1"


def test_une_cle_de_test_vise_la_sandbox():
    c = FinkareClient(api_key="fk_test_abc123")
    assert c.base_url == SANDBOX
    assert c.is_sandbox is True


def test_une_cle_live_vise_la_production():
    c = FinkareClient(api_key="fk_live_abc123")
    assert c.base_url == PROD
    assert c.is_sandbox is False


@pytest.mark.parametrize("cle", ["abc123", "sk_test_abc", "FK_TEST_ABC", ""])
def test_un_prefixe_inconnu_vaut_PRODUCTION(cle):
    """Y compris la casse : `FK_TEST_` n'est pas `fk_test_`. Le repli vers la sandbox
    ferait croire à un travail effectué qui n'a touché personne."""
    assert FinkareClient(api_key=cle or "x").base_url == PROD


def test_l_adresse_ne_se_passe_PAS_en_parametre():
    """Contre-test de conception : si un jour quelqu'un rajoute un `base_url=` au
    constructeur, la garde ci-dessus devient contournable et ce test le dit."""
    import inspect

    params = inspect.signature(FinkareClient.__init__).parameters
    assert "base_url" not in params, (
        "l'adresse doit rester DÉRIVÉE de la clé : un paramètre rouvrirait le couple "
        "(clé live, URL sandbox) et l'inverse")


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

    c = FinkareClient(api_key="fk_test_x")
    monkeypatch.setattr(fk_mod.requests, "request", fake)
    with pytest.raises(RedirectRefused) as e:
        c.list_invoices()
    assert vus[0]["allow_redirects"] is False
    assert e.value.location == "https://ailleurs.test/v1/x"
    assert "SECRET" not in str(e.value)
    assert len(vus) == 1
