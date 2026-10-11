"""BODACC notices client — the `annonces-commerciales` dataset of the DILA, on OpenDataSoft v2.1.

Open data, no key (Licence Ouverte / Etalab 2.0). Where `BodaccClient` (france-opendata)
reads the notices of known companies, this client reads the BODACC as a whole: every
notice published over a period, filtered by family, department, court, city, notice
type or full text — plus counts grouped by a field, and one notice in full.

Endpoint: `GET {BASE_URL}/records` with `where` (ODSQL), `order_by`, `limit`, `offset`,
`select`, `group_by`.

⚠️ ODSQL pagination is capped: `offset + limit` ≤ 10 000. Beyond, the caller narrows the
filters (a shorter period); `search` refuses the window instead of letting the API
answer an opaque 400.

⚠️ Several fields are JSON documents serialised as strings (`jugement`, `acte`,
`modificationsgenerales`, `depot`, `listepersonnes`…): they are parsed here. One that
does not parse raises `BodaccPayloadError` — never a string handed back as if it were
the document, which would empty every derived column in silence.

⚠️ `registre` of a SALE carries the SIREN of BOTH parties (seller and buyer), and
`commercant` concatenates both names (measured 09/10/2026: 80 sales out of 100). A flat
line therefore never picks one: `siren` is set only when the notice names exactly one
company, and `parties` lists every SIREN with the role the notice makes readable.

Requires: requests
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any, Dict, List, Optional

import requests

from ..common import raise_for_upstream

BASE_URL = "https://bodacc-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/annonces-commerciales"

PAGE_MAX = 100
OFFSET_MAX = 10_000

# The real values of `familleavis`, with their label.
FAMILLES: Dict[str, str] = {
    "collective": "Procédures collectives",
    "conciliation": "Procédures de conciliation",
    "creation": "Créations",
    "divers": "Avis divers",
    "dpc": "Dépôts des comptes",
    "immatriculation": "Immatriculations",
    "modification": "Modifications diverses",
    "radiation": "Radiations",
    "retablissement_professionnel": "Procédures de rétablissement professionnel",
    "vente": "Ventes et cessions",
}

# The real values of `typeavis`.
TYPES_AVIS = ("annonce", "rectificatif", "annulation")

# Fields a count can be grouped by: the caller's name → the dataset's field.
GROUP_FIELDS: Dict[str, str] = {
    "famille": "familleavis",
    "departement": "numerodepartement",
    "region": "region_nom_officiel",
    "tribunal": "tribunal",
    "type_avis": "typeavis",
    "mois": "date_format(dateparution, 'yyyy-MM')",
    "jour": "dateparution",
}

# Fields stored as JSON documents serialised in a string.
_JSON_FIELDS = (
    "listepersonnes", "listeetablissements", "jugement", "acte", "modificationsgenerales",
    "radiationaurcs", "depot", "listeprecedentexploitant", "listeprecedentproprietaire",
    "divers", "parutionavisprecedent",
)

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_DEPARTEMENT = re.compile(r"^(\d{2,3}|2A|2B)$")
_SIREN = re.compile(r"^\d{9}$")


class BodaccQueryError(ValueError):
    """A filter the dataset cannot answer (unknown family, malformed date, window past
    the pagination cap…) — refused before any request."""


class BodaccPayloadError(ValueError):
    """The dataset served a notice this client cannot read (a JSON field that does not
    parse): named, never silently flattened into empty columns."""


# Where a notice names its FORMER holders, and the role each block gives a SIREN.
_ANCIENS: Dict[str, str] = {
    "listeprecedentproprietaire": "ancien_proprietaire",
    "listeprecedentexploitant": "ancien_exploitant",
}


def _quote(value: str) -> str:
    """An ODSQL string literal: double quotes, `\\` and `"` escaped."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _date(name: str, value: Optional[str]) -> Optional[date]:
    """A real calendar date, not just four-two-two digits: `2026-13-45` is refused here,
    not left to the dataset's opaque 400."""
    if value is None:
        return None
    if not _DATE.match(value):
        raise BodaccQueryError(f"{name}: expected a date YYYY-MM-DD, got {value!r}")
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise BodaccQueryError(f"{name}: not a calendar date, got {value!r}") from None


def _parse(value: Any, *, field: str = "?", notice_id: Any = None) -> Any:
    if isinstance(value, str) and value[:1] in "{[":
        try:
            return json.loads(value)
        except ValueError as e:
            raise BodaccPayloadError(
                f"notice {notice_id!r}: field {field!r} is not readable JSON ({e})") from None
    return value


def _parse_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    nid = rec.get("id")
    return {k: _parse(v, field=k, notice_id=nid) for k, v in rec.items()}


def _siren(numero: Any) -> Optional[str]:
    digits = str(numero or "").replace(" ", "")
    return digits if _SIREN.match(digits) else None


def _sirens_of(registre: Any) -> List[str]:
    """`registre` is a list such as ['791195415', '791 195 415'] — and the one of a sale
    carries the SIREN of BOTH parties. Every distinct SIREN, in the dataset's order."""
    if isinstance(registre, str):
        registre = [registre]
    out: List[str] = []
    for item in registre or []:
        s = _siren(item)
        if s and s not in out:
            out.append(s)
    return out


def _personnes(bloc: Any) -> List[Dict[str, Any]]:
    """The `personne` entries of a `liste*` block: one object or a list of them."""
    if not isinstance(bloc, dict):
        return []
    p = bloc.get("personne")
    items = p if isinstance(p, list) else [p]
    return [x for x in items if isinstance(x, dict)]


def _siren_de_personne(p: Dict[str, Any]) -> Optional[str]:
    immat = p.get("numeroImmatriculation") or {}
    return _siren(immat.get("numeroIdentification")) if isinstance(immat, dict) else None


def parties(rec: Dict[str, Any]) -> List[Dict[str, Optional[str]]]:
    """Every SIREN of the notice with the role it makes readable: `ancien_proprietaire`
    or `ancien_exploitant` (named in the `listeprecedent*` blocks), `titulaire` (named
    in `listepersonnes` — the buyer of a sale, the subject otherwise), `indeterminee`
    when the registre carries a SIREN no block names. Never guessed."""
    roles: Dict[str, str] = {}
    for champ, role in _ANCIENS.items():
        for p in _personnes(rec.get(champ)):
            s = _siren_de_personne(p)
            if s:
                roles.setdefault(s, role)
    for p in _personnes(rec.get("listepersonnes")):
        s = _siren_de_personne(p)
        if s:
            roles.setdefault(s, "titulaire")
    out = [{"siren": s, "role": roles.get(s, "indeterminee")} for s in _sirens_of(rec.get("registre"))]
    for s, role in roles.items():
        if all(x["siren"] != s for x in out):
            out.append({"siren": s, "role": role})
    return out


def _adresse(a: Any) -> Optional[str]:
    if not isinstance(a, dict):
        return None
    morceaux = [a.get("numeroVoie"), a.get("typeVoie"), a.get("nomVoie"), a.get("codePostal"),
                a.get("ville")]
    texte = " ".join(str(m) for m in morceaux if m)
    return texte or None


def _first(value: Any) -> Any:
    """Some sub-documents hold one object or a list of them."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _summary(rec: Dict[str, Any]) -> Optional[str]:
    """The notice's own free text, wherever its family puts it."""
    jugement = rec.get("jugement") or {}
    acte = rec.get("acte") or {}
    modif = rec.get("modificationsgenerales") or {}
    radiation = rec.get("radiationaurcs") or {}
    depot = rec.get("depot") or {}
    candidates = [
        jugement.get("complementJugement") if isinstance(jugement, dict) else None,
        jugement.get("nature") if isinstance(jugement, dict) else None,
        modif.get("descriptif") if isinstance(modif, dict) else None,
        acte.get("descriptif") if isinstance(acte, dict) else None,
        radiation.get("commentaire") if isinstance(radiation, dict) else None,
        depot.get("typeDepot") if isinstance(depot, dict) else None,
    ]
    if isinstance(acte, dict):
        for key in ("creation", "vente", "immatriculation"):
            sub = acte.get(key)
            if isinstance(sub, dict):
                candidates.extend(v for k, v in sub.items() if k.startswith("categorie"))
    divers = rec.get("divers")
    if isinstance(divers, dict):
        candidates.append(divers.get("texte"))
    for text in candidates:
        if isinstance(text, str) and text.strip():
            return text.strip()
    return None


def flatten(rec: Dict[str, Any]) -> Dict[str, Any]:
    """A notice as returned by the dataset (JSON fields already parsed) → a flat,
    table-friendly line.

    `siren` is set only when the notice names exactly ONE company; a sale names two
    (seller and buyer) and gets `siren=None` with both in `parties`. The company's own
    fields (`activite`, `forme_juridique`, `capital`, `adresse_siege`) come from
    `listepersonnes.personne` — the block the dataset fills (100/100 insolvency notices
    sampled 09/10/2026) — `activite` falling back on the establishment when the person
    block has none (sales describe the business sold there)."""
    jugement = rec.get("jugement") if isinstance(rec.get("jugement"), dict) else {}
    etab = _first((rec.get("listeetablissements") or {}).get("etablissement")
                  if isinstance(rec.get("listeetablissements"), dict) else None)
    etab = etab if isinstance(etab, dict) else {}
    depot = rec.get("depot") if isinstance(rec.get("depot"), dict) else {}
    personne = next(iter(_personnes(rec.get("listepersonnes"))), {})
    capital = personne.get("capital") if isinstance(personne.get("capital"), dict) else {}
    sirens = _sirens_of(rec.get("registre"))
    return {
        "id": rec.get("id"),
        "date_parution": rec.get("dateparution"),
        "famille": rec.get("familleavis"),
        "famille_lib": rec.get("familleavis_lib"),
        "type_avis": rec.get("typeavis"),
        "siren": sirens[0] if len(sirens) == 1 else None,
        "parties": parties(rec),
        "commercant": rec.get("commercant"),
        "denomination": personne.get("denomination"),
        "forme_juridique": personne.get("formeJuridique"),
        "capital": capital.get("montantCapital"),
        "adresse_siege": _adresse(personne.get("adresseSiegeSocial") or personne.get("adressePP")),
        "ville": rec.get("ville"),
        "cp": rec.get("cp"),
        "departement": rec.get("numerodepartement"),
        "region": rec.get("region_nom_officiel"),
        "tribunal": rec.get("tribunal"),
        "jugement_nature": jugement.get("nature"),
        "jugement_date": jugement.get("date"),
        "date_cloture": depot.get("dateCloture"),
        "activite": personne.get("activite") or etab.get("activite"),
        "resume": _summary(rec),
        "url": rec.get("url_complete"),
    }


class BodaccNoticesClient:
    """Read the whole BODACC: search, count, fetch one notice."""

    def __init__(self, timeout: tuple[float, float] | float = (10, 30)):
        self.timeout = timeout
        self._session = requests.Session()

    # --- transport -----------------------------------------------------------------

    def _records(self, params: Dict[str, Any]) -> Dict[str, Any]:
        resp = self._session.get(f"{BASE_URL}/records", params=params, timeout=self.timeout)
        raise_for_upstream(resp, service="bodacc")
        return resp.json()

    # --- filters -------------------------------------------------------------------

    @staticmethod
    def where(
        q: Optional[str] = None,
        famille: Optional[str] = None,
        departement: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        commercant: Optional[str] = None,
        ville: Optional[str] = None,
        tribunal: Optional[str] = None,
        type_avis: Optional[str] = None,
        siren: Optional[str] = None,
    ) -> Optional[str]:
        """The ODSQL `where` clause of the filters, `None` when there is none.
        Raises `BodaccQueryError` on a value the dataset cannot match."""
        clauses: List[str] = []
        if q:
            clauses.append(f"search({_quote(q)})")
        if famille:
            if famille not in FAMILLES:
                raise BodaccQueryError(
                    f"famille: unknown value {famille!r}; allowed: {', '.join(FAMILLES)}")
            clauses.append(f"familleavis={_quote(famille)}")
        if departement:
            dep = departement.strip().upper()
            if not _DEPARTEMENT.match(dep):
                raise BodaccQueryError(
                    f"departement: expected a department code (e.g. 75, 2A, 974), got {departement!r}")
            clauses.append(f"numerodepartement={_quote(dep)}")
        debut, fin = _date("date_from", date_from), _date("date_to", date_to)
        if debut and fin and debut > fin:
            raise BodaccQueryError(
                f"empty window: date_from {date_from} is after date_to {date_to}")
        if debut:
            clauses.append(f"dateparution>={_quote(date_from)}")
        if fin:
            clauses.append(f"dateparution<={_quote(date_to)}")
        if commercant:
            clauses.append(f"search(commercant, {_quote(commercant)})")
        if ville:
            clauses.append(f"search(ville, {_quote(ville)})")
        if tribunal:
            clauses.append(f"search(tribunal, {_quote(tribunal)})")
        if type_avis:
            if type_avis not in TYPES_AVIS:
                raise BodaccQueryError(
                    f"type_avis: unknown value {type_avis!r}; allowed: {', '.join(TYPES_AVIS)}")
            clauses.append(f"typeavis={_quote(type_avis)}")
        if siren:
            digits = siren.replace(" ", "")
            if not _SIREN.match(digits):
                raise BodaccQueryError(f"siren: expected 9 digits, got {siren!r}")
            clauses.append(f"registre={_quote(digits)}")
        return " AND ".join(clauses) or None

    # --- reads ---------------------------------------------------------------------

    def search(self, *, limit: int = 20, offset: int = 0, order: str = "desc",
               raw: bool = False, **filters: Any) -> Dict[str, Any]:
        """Notices matching `filters` (see `where`), most recent first by default.

        Returns `total_count`, `offset`, `next_offset` (None on the last page or at the
        pagination cap) and `notices`: flat lines (`flatten`), or the full parsed
        notices when `raw`."""
        if not 1 <= limit <= PAGE_MAX:
            raise BodaccQueryError(f"limit: between 1 and {PAGE_MAX}, got {limit}")
        if offset < 0 or offset + limit > OFFSET_MAX:
            raise BodaccQueryError(
                f"offset + limit must stay ≤ {OFFSET_MAX} (dataset pagination cap), got "
                f"{offset} + {limit}; narrow the period instead")
        if order not in ("asc", "desc"):
            raise BodaccQueryError(f"order: 'asc' or 'desc', got {order!r}")
        params: Dict[str, Any] = {
            "limit": limit, "offset": offset, "order_by": f"dateparution {order}",
        }
        clause = self.where(**filters)
        if clause:
            params["where"] = clause
        data = self._records(params)
        rows = [_parse_record(r) for r in data.get("results") or []]
        total = int(data.get("total_count") or 0)
        nxt = offset + len(rows)
        # A `next_offset` is only announced when the NEXT call, at the same `limit`,
        # would be accepted (`offset + limit` ≤ cap) — not one the cap then refuses.
        return {
            "total_count": total,
            "offset": offset,
            "next_offset": nxt if rows and nxt < total and nxt + limit <= OFFSET_MAX else None,
            "notices": rows if raw else [flatten(r) for r in rows],
        }

    def get(self, notice_id: str) -> Optional[Dict[str, Any]]:
        """One notice in full (JSON fields parsed), `None` if the id is unknown."""
        data = self._records({"where": f"id={_quote(notice_id)}", "limit": 1})
        rows = data.get("results") or []
        if not rows:
            return None
        return {k: v for k, v in _parse_record(rows[0]).items() if v is not None}

    def count(self, group_by: str, *, limit: int = 100, **filters: Any) -> Dict[str, Any]:
        """Number of notices matching `filters`, grouped by `group_by` (a key of
        `GROUP_FIELDS`), largest groups first (chronological for `mois` and `jour`).
        `notices_counted` sums the groups returned; `truncated` says the page was full."""
        field = GROUP_FIELDS.get(group_by)
        if field is None:
            raise BodaccQueryError(
                f"group_by: unknown value {group_by!r}; allowed: {', '.join(GROUP_FIELDS)}")
        if not 1 <= limit <= PAGE_MAX:
            raise BodaccQueryError(f"limit: between 1 and {PAGE_MAX}, got {limit}")
        params: Dict[str, Any] = {
            "select": "count(*) as n",
            "group_by": f"{field} as cle",
            "order_by": "cle asc" if group_by in ("mois", "jour") else "n desc",
            "limit": limit,
        }
        clause = self.where(**filters)
        if clause:
            params["where"] = clause
        data = self._records(params)
        groups = [{"key": r.get("cle"), "count": int(r.get("n") or 0)}
                  for r in data.get("results") or []]
        if group_by == "famille":
            for g in groups:
                g["label"] = FAMILLES.get(g["key"])
        return {
            "group_by": group_by,
            "groups": groups,
            # The dataset's `total_count` of a grouped query is the number of groups
            # RETURNED, not of groups existing: a full page may hide more.
            "truncated": len(groups) >= limit,
            "notices_counted": sum(g["count"] for g in groups),
        }
