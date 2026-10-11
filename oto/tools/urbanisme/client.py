"""Urbanisme client — French planning rules that apply to a place (open data, no key).

Three public services of the IGN, chained client-side as their documentation asks:

- **Géoplateforme geocoder** (`data.geopf.fr/geocodage/search`): address → point (BAN).
- **API Carto, Cadastre module** (`/api/cadastre/parcelle`): parcel by identifier or by
  geometry → its outline (MultiPolygon, WGS84).
- **API Carto, Urbanisme module** (`/api/gpu/<layer>`): the Géoportail de l'Urbanisme
  (GPU) objects that intersect a GeoJSON geometry (Point, Polygon, MultiPolygon, WGS84):
  municipality (under the RNU?), planning document (PLU, PLUi, CC, PSMV, POS), zoning,
  prescriptions, information perimeters, public-utility servitudes (SUP: footprints
  « assiettes » and generators).

Every GPU answer is a GeoJSON `FeatureCollection`; a malformed request is an HTTP 400
with the reason in `message`. An empty answer does NOT prove absence: the GPU does not
hold every document and servitude yet (see `projection.notes`).

Requires: requests
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Sequence

import requests

from ..common import raise_for_upstream
from . import projection as proj

LAYERS = (
    "municipality", "document", "zone-urba", "secteur-cc",
    "prescription-surf", "prescription-lin", "prescription-pct",
    "info-surf", "info-lin", "info-pct", "acte-sup",
    "assiette-sup-s", "assiette-sup-l", "assiette-sup-p",
    "generateur-sup-s", "generateur-sup-l", "generateur-sup-p",
)
_SUP_LAYERS = {"assiette-sup-s", "assiette-sup-l", "assiette-sup-p",
               "generateur-sup-s", "generateur-sup-l", "generateur-sup-p"}
_SHAPES = {"s": "surface", "l": "line", "p": "point",
           "surf": "surface", "lin": "line", "pct": "point"}
_GEOM_TYPES = {"Point", "Polygon", "MultiPolygon"}

# Paris, Lyon and Marseille: the cadastre files a parcel under the city code plus an
# arrondissement code, while its identifier (IDU) starts with the arrondissement's own
# INSEE code (75107…, 69381…, 13201…).
_PLM = (("751", "75056"), ("693", "69123"), ("132", "13055"))

_IDU = re.compile(r"^((?:\d{2}|2[AB])\d{3})(\d{3})([0-9A-Z]{2})(\d{4})$")


def _idu_key(idu: str) -> str:
    """The IDU as the cadastre writes it (upper case, no space)."""
    return re.sub(r"\s+", "", str(idu or "")).upper()


class UrbanismeNotFound(LookupError):
    """The address, the parcel or the place could not be resolved (nothing invented)."""


def parse_idu(idu: str) -> Dict[str, str]:
    """Cadastral parcel identifier (IDU, 14 characters) → cadastre query parameters.

    `35238000AC0680` → `{"code_insee": "35238", "com_abs": "000", "section": "AC",
    "numero": "0680"}`; an arrondissement of Paris, Lyon or Marseille (`75107000BQ0003`)
    → the city code plus `code_arr` (`75056`, `107`). Raises `ValueError` otherwise.
    """
    m = _IDU.fullmatch(_idu_key(idu))
    if not m:
        raise ValueError(f"invalid parcel identifier: {idu!r} — expected 14 characters, "
                         "INSEE (5) + absorbed municipality (3) + section (2) + number (4), "
                         "e.g. '35238000AC0680'")
    insee, com_abs, section, numero = m.groups()
    params = {"code_insee": insee, "com_abs": com_abs, "section": section, "numero": numero}
    for prefix, city in _PLM:
        if insee.startswith(prefix) and insee != city:
            params.update(code_insee=city, code_arr=insee[2:])
    return params


def _check_geom(geom: Any) -> Dict[str, Any]:
    if isinstance(geom, str):
        try:
            geom = json.loads(geom)
        except ValueError as exc:
            raise ValueError(f"geom is not valid JSON: {exc}") from exc
    if not isinstance(geom, dict) or geom.get("type") not in _GEOM_TYPES \
            or "coordinates" not in geom:
        raise ValueError("geom must be a GeoJSON geometry of type Point, Polygon or "
                         "MultiPolygon, in WGS84 (longitude, latitude)")
    return geom


class UrbanismeClient:
    """Client of the IGN planning services (API Carto GPU and Cadastre, geocoder)."""

    APICARTO_URL = "https://apicarto.ign.fr/api"
    GEOCODER_URL = "https://data.geopf.fr/geocodage"

    def __init__(self, timeout: int = 60):
        self.timeout = timeout
        self.session = requests.Session()

    # --- transport ----------------------------------------------------------

    def _get(self, url: str, params: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.session.get(url, params=params, timeout=(10, self.timeout))
        raise_for_upstream(resp, service="urbanisme")
        return resp.json()

    def _post(self, url: str, body: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.session.post(url, json=body, timeout=(10, self.timeout))
        raise_for_upstream(resp, service="urbanisme")
        return resp.json()

    # --- location -----------------------------------------------------------

    def geocode(self, address: str) -> Dict[str, Any]:
        """Address → best match: `label`, `type` (housenumber, street, locality,
        municipality), `score` (0–1), `citycode` (INSEE), `city`, `point` (GeoJSON).

        Raises `UrbanismeNotFound` when the geocoder finds nothing.
        """
        if not str(address or "").strip():
            raise ValueError("address is empty")
        fc = self._get(f"{self.GEOCODER_URL}/search",
                       {"q": address, "index": "address", "limit": 1})
        features = fc.get("features") or []
        if not features:
            raise UrbanismeNotFound(f"address not found: {address!r}")
        p = features[0].get("properties") or {}
        return {"label": p.get("label"), "type": p.get("type"), "score": p.get("score"),
                "citycode": p.get("citycode"), "city": p.get("city"),
                "point": features[0].get("geometry")}

    def parcels(self, *, idu: Optional[str] = None, geom: Any = None,
                limit: int = 20) -> List[Dict[str, Any]]:
        """Cadastral parcels by identifier (`idu`) or intersecting `geom` — raw
        features (properties: `idu`, `code_insee`, `section`, `numero`, `contenance`
        in m², …; geometry: outline in WGS84)."""
        if (idu is None) == (geom is None):
            raise ValueError("give exactly one of idu or geom")
        if idu is not None:
            params: Dict[str, Any] = parse_idu(idu)
        else:
            params = {"geom": json.dumps(_check_geom(geom))}
        params["_limit"] = limit
        fc = self._get(f"{self.APICARTO_URL}/cadastre/parcelle", params)
        return fc.get("features") or []

    def parcel(self, idu: str) -> Dict[str, Any]:
        """One parcel by identifier; `UrbanismeNotFound` if the cadastre has none."""
        found = [f for f in self.parcels(idu=idu)
                 if (f.get("properties") or {}).get("idu") == _idu_key(idu)]
        if not found:
            raise UrbanismeNotFound(f"parcel not found in the cadastre: {idu!r}")
        return found[0]

    # --- GPU ----------------------------------------------------------------

    def layer(self, name: str, *, geom: Any = None, partition: Optional[str] = None,
              categorie: Optional[str] = None, insee: Optional[str] = None) -> Dict[str, Any]:
        """One GPU layer, raw `FeatureCollection` (geometries included).

        Args:
            name: one of `LAYERS`.
            geom: GeoJSON geometry (Point, Polygon, MultiPolygon, WGS84).
            partition: GPU partition, e.g. `DU_35238`, `PSMV_35238`, `DU_243500139`
                (PLUi, SIREN), `172014607_SUP_35_AC4` (servitude).
            categorie: SUP category (`AC1`, `PM1`…), servitude layers only.
            insee: municipality code, `municipality` layer only.
        """
        if name not in LAYERS:
            raise ValueError(f"unknown GPU layer: {name!r} — one of {', '.join(LAYERS)}")
        body: Dict[str, Any] = {}
        if geom is not None:
            body["geom"] = _check_geom(geom)
        if partition:
            body["partition"] = partition
        if insee:
            if name != "municipality":
                raise ValueError("insee only filters the municipality layer")
            body["insee"] = insee
        if categorie:
            if name not in _SUP_LAYERS:
                raise ValueError("categorie only filters the servitude layers "
                                 "(assiette-sup-*, generateur-sup-*)")
            body["categorie"] = categorie
        if not body or set(body) == {"categorie"}:
            # The API answers an unfiltered query with the whole national layer.
            raise ValueError("give geom, partition or (municipality) insee")
        return self._post(f"{self.APICARTO_URL}/gpu/{name}", body)

    def report(self, *, address: Optional[str] = None, idu: Optional[str] = None,
               geom: Any = None, on_parcel: bool = True,
               sup_categories: Optional[Sequence[str]] = None) -> Dict[str, Any]:
        """What applies to a place: municipality, planning documents, zoning,
        prescriptions, information perimeters, servitudes — without geometries.

        Exactly one of:
            address: geocoded; with `on_parcel` (default), the query uses the outline
                of the parcel under the address point, else the point itself.
            idu: cadastral parcel identifier (14 characters).
            geom: GeoJSON geometry (Point, Polygon, MultiPolygon, WGS84).

        `sup_categories` restricts the servitudes to some categories (`AC1`, `PM1`…).
        Returns `{"location", "municipalities", "documents", "zones", "cc_sectors",
        "prescriptions", "informations", "servitudes", "notes"}`; identical features
        are grouped with a `count`.
        """
        if sum(x is not None for x in (address, idu, geom)) != 1:
            raise ValueError("give exactly one of address, idu or geom")
        location: Dict[str, Any]
        if address is not None:
            found = self.geocode(address)
            location = {"source": "address", "label": found["label"],
                        "match_type": found["type"], "score": found["score"],
                        "citycode": found["citycode"], "point": found["point"]}
            query = found["point"]
            if on_parcel:
                under = self.parcels(geom=found["point"], limit=2)
                if len(under) == 1:
                    location["parcel"] = _parcel_summary(under[0])
                    query = under[0]["geometry"]
            location["queried"] = "parcel" if "parcel" in location else "point"
        elif idu is not None:
            feature = self.parcel(idu)
            location = {"source": "parcel", "parcel": _parcel_summary(feature),
                        "queried": "parcel"}
            query = feature["geometry"]
        else:
            query = _check_geom(geom)
            location = {"source": "geom", "queried": query["type"]}

        raw = self._layers(query, sup_categories)
        munis = proj.municipalities(raw["municipality"])
        docs = proj.documents(raw["document"])
        shapes = lambda prefix: {_SHAPES[n.rsplit("-", 1)[1]]: fc  # noqa: E731
                                 for n, fc in raw.items() if n.startswith(prefix)}
        return {
            "location": location,
            "municipalities": munis,
            "documents": docs,
            "zones": proj.zones(raw["zone-urba"]),
            "cc_sectors": proj.cc_sectors(raw["secteur-cc"]),
            "prescriptions": proj.prescriptions(shapes("prescription-")),
            "informations": proj.informations(shapes("info-")),
            "servitudes": proj.servitudes(shapes("assiette-sup-"), shapes("generateur-sup-")),
            "notes": proj.notes(munis, docs),
        }

    def _layers(self, geom: Dict[str, Any],
                sup_categories: Optional[Sequence[str]]) -> Dict[str, Dict[str, Any]]:
        """Every layer of the report for one geometry, fetched in parallel.

        With `sup_categories`, one servitude query per category and layer, merged.
        """
        plain = [n for n in LAYERS if n not in _SUP_LAYERS and n != "acte-sup"]
        jobs = [(n, None) for n in plain]
        cats = [c.strip().upper() for c in sup_categories or [] if c and c.strip()]
        jobs += [(n, c) for n in sorted(_SUP_LAYERS) for c in (cats or [None])]
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(
                lambda job: self.layer(job[0], geom=geom, categorie=job[1]), jobs))
        out: Dict[str, Dict[str, Any]] = {}
        for (name, _), fc in zip(jobs, results):
            merged = out.setdefault(name, {"type": "FeatureCollection", "features": []})
            merged["features"] += fc.get("features") or []
        return out


def _parcel_summary(feature: Dict[str, Any]) -> Dict[str, Any]:
    p = feature.get("properties") or {}
    return {"idu": p.get("idu"), "code_insee": p.get("code_insee"),
            "municipality": p.get("nom_com"), "section": p.get("section"),
            "numero": p.get("numero"), "area_m2": p.get("contenance")}
