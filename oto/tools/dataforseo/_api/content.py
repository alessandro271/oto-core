"""Content analysis: web pages that mention a keyword or brand, with sentiment.

`page_type` narrows the sources: `ecommerce`, `news`, `blogs`,
`message-boards`, `organization`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

_CA = "/content_analysis"


class ContentMixin:

    def content_search(
        self, keyword: str, page_type: Optional[List[str]] = None,
        limit: Optional[int] = None, offset: Optional[int] = None,
        filters: Optional[list] = None, order_by: Optional[List[str]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /content_analysis/search/live — citations of the keyword: URL,
        domain, snippet, date, sentiment. Max 100 per call."""
        return self._live(f"{_CA}/search/live", {
            "keyword": keyword, "page_type": page_type, "limit": limit, "offset": offset,
            "filters": filters, "order_by": order_by, **(options or {})})

    def content_summary(self, keyword: str, page_type: Optional[List[str]] = None,
                        options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """POST /content_analysis/summary/live — totals for the keyword's
        citations: count, sentiment and connotations, top domains, countries,
        page types."""
        return self._live(f"{_CA}/summary/live", {"keyword": keyword, "page_type": page_type,
                                                  **(options or {})})
