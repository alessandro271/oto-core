"""Projection of the GPU layers into a planning report — no geometry, no duplicate.

The raw layers are GeoJSON `FeatureCollection`s whose geometries weigh several MB
(a surface prescription layer over a city centre parcel: ~5 MB). The report keeps
the attributes that answer « what applies here », groups identical features (a
document repeats the same prescription over many polygons) and counts them.
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

DOCUMENT_PAGE = "https://www.geoportail-urbanisme.gouv.fr/document/by-id/{}"


def _props(fc: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [f.get("properties") or {} for f in (fc or {}).get("features") or []]


def _text(value: Any) -> Any:
    """Repairs UTF-8 text published decoded as Latin-1 (`HÃ´tel` → `Hôtel`), which
    some servitude batches carry; any other value is returned unchanged."""
    if not isinstance(value, str) or ("Ã" not in value and "Â" not in value):
        return value
    try:
        return value.encode("latin-1").decode("utf-8")
    except UnicodeError:
        return value


def _clean(d: Dict[str, Any]) -> Dict[str, Any]:
    """Drops empty values (the GPU publishes many optional attributes as null or '')
    and repairs mis-decoded text."""
    return {k: _text(v) for k, v in d.items() if v not in (None, "", [])}


def _regulation(p: Dict[str, Any]) -> Dict[str, Any]:
    return _clean({"file": p.get("nomfic"), "url": p.get("urlfic")})


def _group(rows: Iterable[Dict[str, Any]], key: Tuple[str, ...]) -> List[Dict[str, Any]]:
    """Identical rows (same `key` fields) collapse into one, with `count`."""
    out: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for row in rows:
        k = tuple(row.get(f) for f in key)
        if k in out:
            out[k]["count"] += 1
        else:
            out[k] = dict(row, count=1)
    return list(out.values())


def municipalities(fc: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [{"insee": p.get("insee"), "name": p.get("name"),
             "is_rnu": p.get("is_rnu"), "is_deleted": p.get("is_deleted")}
            for p in _props(fc)]


def documents(fc: Dict[str, Any]) -> List[Dict[str, Any]]:
    out = []
    for p in _props(fc):
        doc_id = p.get("gpu_doc_id") or p.get("id")
        out.append(_clean({
            "name": p.get("name"), "du_type": p.get("du_type"),
            "partition": p.get("partition"), "territory": p.get("grid_title"),
            "territory_code": p.get("grid_name"), "status": p.get("gpu_status"),
            "published_at": p.get("gpu_timestamp"), "gpu_doc_id": doc_id,
            "page": DOCUMENT_PAGE.format(doc_id) if doc_id else None,
        }))
    return out


def zones(fc: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = [_clean({
        "label": p.get("libelle"), "long_label": p.get("libelong"),
        "zone_type": p.get("typezone"), "main_use": p.get("destdomi"),
        "document": p.get("idurba"), "partition": p.get("partition"),
        "valid_from": p.get("datvalid"), "regulation": _regulation(p),
    }) for p in _props(fc)]
    return _group(rows, ("partition", "label", "long_label", "zone_type"))


def cc_sectors(fc: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = [_clean({
        "label": p.get("libelle"), "long_label": p.get("libelong"),
        "sector_type": p.get("typesect"), "main_use": p.get("destdomi"),
        "document": p.get("idurba"), "partition": p.get("partition"),
        "regulation": _regulation(p),
    }) for p in _props(fc)]
    return _group(rows, ("partition", "label", "sector_type"))


def _typed(fcs: Dict[str, Dict[str, Any]], code: str, subcode: str) -> List[Dict[str, Any]]:
    rows = []
    for shape, fc in fcs.items():
        for p in _props(fc):
            rows.append(_clean({
                "label": p.get("libelle"), "text": p.get("txt"),
                "type": p.get(code), "subtype": p.get(subcode), "shape": shape,
                "document": p.get("idurba"), "partition": p.get("partition"),
                "regulation": _regulation(p),
            }))
    return _group(rows, ("partition", "type", "subtype", "label", "text", "shape"))


def prescriptions(fcs: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """`fcs` = {"surface"|"line"|"point": FeatureCollection}."""
    return _typed(fcs, "typepsc", "stypepsc")


def informations(fcs: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    return _typed(fcs, "typeinf", "stypeinf")


def servitudes(assiettes: Dict[str, Dict[str, Any]],
               generateurs: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """One entry per servitude (`idsup`, else its partition), with the footprints
    (assiettes) that intersect the queried geometry and the generators that do too.

    A generator elsewhere (the monument whose surroundings cover the parcel) is not
    in `generateurs`: its id stays in `generator_ids` of the footprint.
    """
    sups: Dict[str, Dict[str, Any]] = {}

    def entry(p: Dict[str, Any]) -> Dict[str, Any]:
        idgen = p.get("idgen") or ""
        key = p.get("idsup") or idgen.rsplit("-", 1)[0] or p.get("partition")
        if key not in sups:
            sups[key] = _clean({
                "category": (p.get("suptype") or "").upper(),
                "name": p.get("nomsuplitt"), "partition": p.get("partition"),
                "act_file": p.get("fichier"), "id": key,
            })
            sups[key]["footprints"] = []
            sups[key]["generators"] = []
        return sups[key]

    for shape, fc in assiettes.items():
        for p in _props(fc):
            entry(p)["footprints"].append(_clean({
                "type": p.get("typeass"), "name": p.get("nomass"), "shape": shape,
                "mode": p.get("modegeoass"), "generator_id": p.get("idgen"),
            }))
    for shape, fc in generateurs.items():
        for p in _props(fc):
            entry(p)["generators"].append(_clean({
                "type": p.get("typegen"), "name": p.get("nomgen"), "shape": shape,
                "address": p.get("adresse"), "id": p.get("idgen"),
            }))
    return list(sups.values())


def notes(munis: List[Dict[str, Any]], docs: List[Dict[str, Any]]) -> List[str]:
    """What an empty answer means — the GPU does not hold every document yet."""
    out = []
    if not docs:
        if any(m.get("is_rnu") is False for m in munis):
            out.append("No planning document is published on the GPU here, but the "
                       "municipality is not under the RNU: an enforceable document exists "
                       "and must be obtained from the competent authority.")
        elif any(m.get("is_rnu") for m in munis):
            out.append("The municipality is under the RNU (national planning rules): "
                       "no local planning document applies.")
    out.append("Absence of a servitude or prescription in this answer does not prove it "
               "does not exist: publication on the GPU is not yet complete.")
    return out
