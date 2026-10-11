"""Backlinks API — link profile of a domain, subdomain or page.

`target`: a domain or subdomain WITHOUT scheme or `www.`, or a page's absolute
URL. Same envelope and `options` rule as the keyword methods (e.g.
`include_subdomains`, `backlinks_status_type`, `rank_scale`).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

_BL = "/backlinks"


class BacklinksMixin:

    def backlinks_summary(self, target: str,
                          options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """POST /backlinks/summary/live — totals: backlinks, referring domains,
        IPs and subnets, rank, spam score, top TLDs and link types."""
        return self._live(f"{_BL}/summary/live", {"target": target, **(options or {})})

    def backlinks_list(
        self, target: str, mode: Optional[str] = None, limit: Optional[int] = None,
        offset: Optional[int] = None, filters: Optional[list] = None,
        order_by: Optional[List[str]] = None, options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /backlinks/backlinks/live — the backlinks themselves (source URL,
        anchor, dofollow, rank, first/last seen). `mode`: `as_is` (default) |
        `one_per_domain` | `one_per_anchor`. API default limit 100, max 1000."""
        return self._live(f"{_BL}/backlinks/live", {
            "target": target, "mode": mode, "limit": limit, "offset": offset,
            "filters": filters, "order_by": order_by, **(options or {})})

    def referring_domains(
        self, target: str, limit: Optional[int] = None, offset: Optional[int] = None,
        filters: Optional[list] = None, order_by: Optional[List[str]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /backlinks/referring_domains/live — domains linking to the
        target, with their backlink count and rank. API default limit 100, max 1000."""
        return self._live(f"{_BL}/referring_domains/live", {
            "target": target, "limit": limit, "offset": offset, "filters": filters,
            "order_by": order_by, **(options or {})})

    def anchors(
        self, target: str, limit: Optional[int] = None, offset: Optional[int] = None,
        filters: Optional[list] = None, order_by: Optional[List[str]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /backlinks/anchors/live — anchor texts pointing to the target,
        with backlink and referring-domain counts. API default limit 100, max 1000."""
        return self._live(f"{_BL}/anchors/live", {
            "target": target, "limit": limit, "offset": offset, "filters": filters,
            "order_by": order_by, **(options or {})})

    def bulk_ranks(self, targets: List[str],
                   options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """POST /backlinks/bulk_ranks/live — the backlink rank of up to 1000
        domains, subdomains or pages in one call."""
        return self._live(f"{_BL}/bulk_ranks/live", {"targets": targets, **(options or {})})
