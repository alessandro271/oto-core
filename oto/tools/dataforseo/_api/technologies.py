"""Domain technologies: what a site is built with, and which sites use a technology.

Detected on the sites themselves (CMS, analytics, e-commerce, payment…), by
technology name (`Shopify`, `HubSpot`) or by keyword in a site's title and meta.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

_TECH = "/domain_analytics/technologies"


class TechnologiesMixin:

    def domain_technologies(self, target: str) -> Dict[str, Any]:
        """POST /domain_analytics/technologies/domain_technologies/live — a
        domain's technologies by group and category, plus its country, language
        and contact details found on the site."""
        return self._live(f"{_TECH}/domain_technologies/live", {"target": target})

    def domains_by_technology(
        self, technologies: Optional[List[str]] = None, keywords: Optional[List[str]] = None,
        limit: Optional[int] = None, offset: Optional[int] = None,
        filters: Optional[list] = None, order_by: Optional[List[str]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /domain_analytics/technologies/domains_by_technology/live — the
        domains using the technologies (or matching the keywords), filterable by
        e.g. `["country_iso_code", "=", "FR"]`, `["domain_rank", ">", 300]`.
        API default limit 100, max 10000."""
        return self._live(f"{_TECH}/domains_by_technology/live", {
            "technologies": technologies, "keywords": keywords, "limit": limit,
            "offset": offset, "filters": filters, "order_by": order_by, **(options or {})})

    def technologies_summary(
        self, technologies: Optional[List[str]] = None, keywords: Optional[List[str]] = None,
        filters: Optional[list] = None, options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /domain_analytics/technologies/technologies_summary/live — how many
        domains use the technologies, by country, language and co-used technology."""
        return self._live(f"{_TECH}/technologies_summary/live", {
            "technologies": technologies, "keywords": keywords, "filters": filters,
            **(options or {})})
