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

    def backlinks_competitors(
        self, target: str, limit: Optional[int] = None, offset: Optional[int] = None,
        filters: Optional[list] = None, order_by: Optional[List[str]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /backlinks/competitors/live — domains sharing the most backlinks
        with the target."""
        return self._live(f"{_BL}/competitors/live", {
            "target": target, "limit": limit, "offset": offset, "filters": filters,
            "order_by": order_by, **(options or {})})

    def backlinks_intersection(
        self, targets: List[str], exclude_targets: Optional[List[str]] = None,
        limit: Optional[int] = None, offset: Optional[int] = None,
        filters: Optional[list] = None, order_by: Optional[List[str]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /backlinks/domain_intersection/live — referring domains that link
        to EVERY target (up to 20) and to none of `exclude_targets` (up to 10):
        e.g. competitors as targets and your site excluded = link prospects."""
        return self._live(f"{_BL}/domain_intersection/live", {
            "targets": {str(i): t for i, t in enumerate(targets, 1)},
            "exclude_targets": exclude_targets, "limit": limit, "offset": offset,
            "filters": filters, "order_by": order_by, **(options or {})})

    def backlinks_history(self, target: str, date_from: Optional[str] = None,
                          date_to: Optional[str] = None) -> Dict[str, Any]:
        """POST /backlinks/history/live — the domain's backlink profile month by
        month (from 2019-01-01): backlinks, referring domains, rank, new and lost."""
        return self._live(f"{_BL}/history/live", {"target": target, "date_from": date_from,
                                                 "date_to": date_to})

    def backlinks_new_lost(self, target: str, date_from: Optional[str] = None,
                           date_to: Optional[str] = None, group_range: Optional[str] = None,
                           options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """POST /backlinks/timeseries_new_lost_summary/live — new and lost backlinks
        and referring domains per `group_range` (`day`|`week`|`month`|`year`)."""
        return self._live(f"{_BL}/timeseries_new_lost_summary/live", {
            "target": target, "date_from": date_from, "date_to": date_to,
            "group_range": group_range, **(options or {})})

    def backlinks_domain_pages(
        self, target: str, limit: Optional[int] = None, offset: Optional[int] = None,
        filters: Optional[list] = None, order_by: Optional[List[str]] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """POST /backlinks/domain_pages/live — the target's pages with their own
        backlink and referring-domain counts (its most linked pages)."""
        return self._live(f"{_BL}/domain_pages/live", {
            "target": target, "limit": limit, "offset": offset, "filters": filters,
            "order_by": order_by, **(options or {})})
