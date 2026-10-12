"""Domain analytics: DataForSEO Labs (Google) — rankings, traffic, competitors.

`target` is a domain WITHOUT scheme or `www.` (`example.com`); endpoints that
also accept a page take its absolute URL. Same envelope and `options` rule as
the keyword methods.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

_LABS = "/dataforseo_labs/google"


class DomainsMixin:

    def domain_rank_overview(
        self, target: str, location_code: Optional[int] = None,
        location_name: Optional[str] = None, language_code: Optional[str] = None,
        language_name: Optional[str] = None, options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /dataforseo_labs/google/domain_rank_overview/live — organic and
        paid footprint: ranking keyword count per position bucket, estimated
        traffic (`etv`) and its value. No location = every location."""
        task = self._location({"target": target}, location_code, location_name,
                              language_code, language_name)
        return self._live(f"{_LABS}/domain_rank_overview/live", {**task, **(options or {})})

    def ranked_keywords(
        self, target: str, location_code: Optional[int] = None,
        location_name: Optional[str] = None, language_code: Optional[str] = None,
        language_name: Optional[str] = None, limit: Optional[int] = None,
        offset: Optional[int] = None, filters: Optional[list] = None,
        order_by: Optional[List[str]] = None, options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /dataforseo_labs/google/ranked_keywords/live — the keywords a
        domain or page ranks for, with position, URL and volume. API default
        limit 100, max 1000."""
        task = self._location({"target": target, "limit": limit, "offset": offset,
                               "filters": filters, "order_by": order_by},
                              location_code, location_name, language_code, language_name)
        return self._live(f"{_LABS}/ranked_keywords/live", {**task, **(options or {})})

    def competitors_domain(
        self, target: str, location_code: Optional[int] = None,
        location_name: Optional[str] = None, language_code: Optional[str] = None,
        language_name: Optional[str] = None, limit: Optional[int] = None,
        offset: Optional[int] = None, filters: Optional[list] = None,
        order_by: Optional[List[str]] = None, options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /dataforseo_labs/google/competitors_domain/live — domains that
        rank for the same keywords, with overlap and their metrics. Location and
        language required. API default limit 100, max 1000."""
        task = self._location({"target": target, "limit": limit, "offset": offset,
                               "filters": filters, "order_by": order_by},
                              location_code, location_name, language_code, language_name)
        return self._live(f"{_LABS}/competitors_domain/live", {**task, **(options or {})})

    def domain_intersection(
        self, target1: str, target2: str, location_code: Optional[int] = None,
        location_name: Optional[str] = None, language_code: Optional[str] = None,
        language_name: Optional[str] = None, intersections: Optional[bool] = None,
        limit: Optional[int] = None, offset: Optional[int] = None,
        filters: Optional[list] = None, order_by: Optional[List[str]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /dataforseo_labs/google/domain_intersection/live — keywords both
        domains rank for (`intersections=True`, default) or that `target1` ranks
        for and `target2` does not (`False`). Location and language required."""
        task = self._location({"target1": target1, "target2": target2,
                               "intersections": intersections, "limit": limit,
                               "offset": offset, "filters": filters, "order_by": order_by},
                              location_code, location_name, language_code, language_name)
        return self._live(f"{_LABS}/domain_intersection/live", {**task, **(options or {})})

    def relevant_pages(
        self, target: str, location_code: Optional[int] = None,
        location_name: Optional[str] = None, language_code: Optional[str] = None,
        language_name: Optional[str] = None, limit: Optional[int] = None,
        offset: Optional[int] = None, filters: Optional[list] = None,
        order_by: Optional[List[str]] = None, options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /dataforseo_labs/google/relevant_pages/live — a domain's pages
        with their ranking keyword counts and estimated traffic."""
        task = self._location({"target": target, "limit": limit, "offset": offset,
                               "filters": filters, "order_by": order_by},
                              location_code, location_name, language_code, language_name)
        return self._live(f"{_LABS}/relevant_pages/live", {**task, **(options or {})})

    def keywords_for_site(
        self, target: str, location_code: Optional[int] = None,
        location_name: Optional[str] = None, language_code: Optional[str] = None,
        language_name: Optional[str] = None, limit: Optional[int] = None,
        offset: Optional[int] = None, filters: Optional[list] = None,
        order_by: Optional[List[str]] = None, options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /dataforseo_labs/google/keywords_for_site/live — keywords
        RELEVANT to a site's content (whether it ranks for them or not).
        Location required."""
        task = self._location({"target": target, "limit": limit, "offset": offset,
                               "filters": filters, "order_by": order_by},
                              location_code, location_name, language_code, language_name)
        return self._live(f"{_LABS}/keywords_for_site/live", {**task, **(options or {})})

    def bulk_traffic_estimation(
        self, targets: List[str], location_code: Optional[int] = None,
        location_name: Optional[str] = None, language_code: Optional[str] = None,
        language_name: Optional[str] = None, options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /dataforseo_labs/google/bulk_traffic_estimation/live — estimated
        monthly organic and paid traffic for up to 1000 domains, subdomains or
        pages in one call."""
        task = self._location({"targets": targets}, location_code, location_name,
                              language_code, language_name)
        return self._live(f"{_LABS}/bulk_traffic_estimation/live", {**task, **(options or {})})

    def historical_rank_overview(
        self, target: str, location_code: Optional[int] = None,
        location_name: Optional[str] = None, language_code: Optional[str] = None,
        language_name: Optional[str] = None, date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /dataforseo_labs/google/historical_rank_overview/live — the domain's
        ranking keyword counts and estimated traffic, month by month. Location and
        language required. Dates `yyyy-mm-dd`."""
        task = self._location({"target": target, "date_from": date_from, "date_to": date_to},
                              location_code, location_name, language_code, language_name)
        return self._live(f"{_LABS}/historical_rank_overview/live", task)

    def serp_competitors(
        self, keywords: List[str], location_code: Optional[int] = None,
        location_name: Optional[str] = None, language_code: Optional[str] = None,
        language_name: Optional[str] = None, limit: Optional[int] = None,
        offset: Optional[int] = None, filters: Optional[list] = None,
        order_by: Optional[List[str]] = None, options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /dataforseo_labs/google/serp_competitors/live — the domains that
        rank for a set of keywords (max 200), with their average position and
        visibility. Location and language required."""
        task = self._location({"keywords": keywords, "limit": limit, "offset": offset,
                               "filters": filters, "order_by": order_by},
                              location_code, location_name, language_code, language_name)
        return self._live(f"{_LABS}/serp_competitors/live", {**task, **(options or {})})

    def subdomains(
        self, target: str, location_code: Optional[int] = None,
        location_name: Optional[str] = None, language_code: Optional[str] = None,
        language_name: Optional[str] = None, limit: Optional[int] = None,
        offset: Optional[int] = None, filters: Optional[list] = None,
        order_by: Optional[List[str]] = None, options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /dataforseo_labs/google/subdomains/live — a domain's subdomains
        with their ranking keywords and estimated traffic."""
        task = self._location({"target": target, "limit": limit, "offset": offset,
                               "filters": filters, "order_by": order_by},
                              location_code, location_name, language_code, language_name)
        return self._live(f"{_LABS}/subdomains/live", {**task, **(options or {})})
