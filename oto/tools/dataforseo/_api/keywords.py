"""Keyword research: DataForSEO Labs (Google) + Google Ads search volume.

Every method POSTs one task to a `live` endpoint and returns the task envelope
(`cost` in USD, `result: [...]`). `options` carries any other documented field
of the endpoint as is (e.g. `include_serp_info`, `include_clickstream_data`).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

_LABS = "/dataforseo_labs/google"


class KeywordsMixin:

    def keyword_overview(
        self, keywords: List[str], location_code: Optional[int] = None,
        location_name: Optional[str] = None, language_code: Optional[str] = None,
        language_name: Optional[str] = None, options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /dataforseo_labs/google/keyword_overview/live — volume, CPC,
        competition, intent, difficulty and monthly trend per keyword (max 700).
        Location and language required (code or name)."""
        task = self._location({"keywords": keywords}, location_code, location_name,
                              language_code, language_name)
        return self._live(f"{_LABS}/keyword_overview/live", {**task, **(options or {})})

    def keyword_ideas(
        self, keywords: List[str], location_code: Optional[int] = None,
        location_name: Optional[str] = None, language_code: Optional[str] = None,
        language_name: Optional[str] = None, limit: Optional[int] = None,
        offset: Optional[int] = None, filters: Optional[list] = None,
        order_by: Optional[List[str]] = None, options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /dataforseo_labs/google/keyword_ideas/live — keywords of the same
        category as the seeds (max 200 seeds). Location required. API default
        limit 700, max 1000 — billed per returned keyword."""
        task = self._location({"keywords": keywords, "limit": limit, "offset": offset,
                               "filters": filters, "order_by": order_by},
                              location_code, location_name, language_code, language_name)
        return self._live(f"{_LABS}/keyword_ideas/live", {**task, **(options or {})})

    def keyword_suggestions(
        self, keyword: str, location_code: Optional[int] = None,
        location_name: Optional[str] = None, language_code: Optional[str] = None,
        language_name: Optional[str] = None, limit: Optional[int] = None,
        offset: Optional[int] = None, filters: Optional[list] = None,
        order_by: Optional[List[str]] = None, options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /dataforseo_labs/google/keyword_suggestions/live — long-tail
        queries that CONTAIN the seed keyword. API default limit 100, max 1000."""
        task = self._location({"keyword": keyword, "limit": limit, "offset": offset,
                               "filters": filters, "order_by": order_by},
                              location_code, location_name, language_code, language_name)
        return self._live(f"{_LABS}/keyword_suggestions/live", {**task, **(options or {})})

    def related_keywords(
        self, keyword: str, location_code: Optional[int] = None,
        location_name: Optional[str] = None, language_code: Optional[str] = None,
        language_name: Optional[str] = None, depth: Optional[int] = None,
        limit: Optional[int] = None, offset: Optional[int] = None,
        filters: Optional[list] = None, order_by: Optional[List[str]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /dataforseo_labs/google/related_keywords/live — Google's "searches
        related to", expanded `depth` levels (0-4, default 1). Location and
        language required. API default limit 100, max 1000."""
        task = self._location({"keyword": keyword, "depth": depth, "limit": limit,
                               "offset": offset, "filters": filters, "order_by": order_by},
                              location_code, location_name, language_code, language_name)
        return self._live(f"{_LABS}/related_keywords/live", {**task, **(options or {})})

    def bulk_keyword_difficulty(
        self, keywords: List[str], location_code: Optional[int] = None,
        location_name: Optional[str] = None, language_code: Optional[str] = None,
        language_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """POST /dataforseo_labs/google/bulk_keyword_difficulty/live — ranking
        difficulty 0-100 per keyword (max 1000). Location and language required."""
        task = self._location({"keywords": keywords}, location_code, location_name,
                              language_code, language_name)
        return self._live(f"{_LABS}/bulk_keyword_difficulty/live", task)

    def search_intent(self, keywords: List[str], language_code: Optional[str] = None,
                      language_name: Optional[str] = None) -> Dict[str, Any]:
        """POST /dataforseo_labs/google/search_intent/live — intent per keyword
        (informational, navigational, commercial, transactional) with a probability
        (max 1000 keywords)."""
        return self._live(f"{_LABS}/search_intent/live",
                          {"keywords": keywords, "language_code": language_code,
                           "language_name": language_name})

    def google_ads_search_volume(
        self, keywords: List[str], location_code: Optional[int] = None,
        location_name: Optional[str] = None, language_code: Optional[str] = None,
        language_name: Optional[str] = None, date_from: Optional[str] = None,
        date_to: Optional[str] = None, options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /keywords_data/google_ads/search_volume/live — Google Ads (Keyword
        Planner) volume, CPC, competition and monthly searches (max 1000
        keywords). No location = worldwide. Dates `yyyy-mm-dd`."""
        task = self._location({"keywords": keywords, "date_from": date_from,
                               "date_to": date_to},
                              location_code, location_name, language_code, language_name)
        return self._live("/keywords_data/google_ads/search_volume/live",
                          {**task, **(options or {})})
