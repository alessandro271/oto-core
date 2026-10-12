"""On-page audit: one page live, Lighthouse, content parsing, and the queued site crawl.

The crawl is the only queued flow of this client: `onpage_crawl_start` posts the
task (billed per page at posting, `max_crawl_pages` caps it) and returns its id;
`onpage_summary` says how far it got (`crawl_progress`: `in_progress` |
`finished`) and what it found; the reports read its pages, non-indexable pages,
duplicate tags, links and redirect chains.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

_OP = "/on_page"


class OnPageMixin:

    def onpage_instant(self, url: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """POST /on_page/instant_pages — audit ONE page now: meta tags, headings,
        content, links, load time and the failed checks."""
        return self._live(f"{_OP}/instant_pages", {"url": url, **(options or {})})

    def onpage_content(self, url: str, options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """POST /on_page/content_parsing/live — the page's content, structured
        (title, headings, text blocks, tables)."""
        return self._live(f"{_OP}/content_parsing/live", {"url": url, **(options or {})})

    def lighthouse(self, url: str, for_mobile: Optional[bool] = None,
                   categories: Optional[List[str]] = None,
                   options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """POST /on_page/lighthouse/live/json — a Lighthouse run (performance,
        accessibility, best practices, SEO scores and audits)."""
        return self._live(f"{_OP}/lighthouse/live/json", {
            "url": url, "for_mobile": for_mobile, "categories": categories, **(options or {})})

    def onpage_crawl_start(self, target: str, max_crawl_pages: int,
                           options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """POST /on_page/task_post — start crawling a site (domain without scheme).
        Returns the task (`id`, `cost`); billed per page at posting."""
        return self._task("POST", f"{_OP}/task_post",
                          {"target": target, "max_crawl_pages": max_crawl_pages,
                           **(options or {})}, ok=(20000, 20100))

    def onpage_summary(self, task_id: str) -> Dict[str, Any]:
        """GET /on_page/summary/{id} — crawl progress and the site-wide findings."""
        return self._task("GET", f"{_OP}/summary/{task_id}")

    def _report(self, report: str, task_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        return self._task("POST", f"{_OP}/{report}", {"id": task_id, **body})

    def onpage_pages(self, task_id: str, limit: Optional[int] = None,
                     offset: Optional[int] = None, filters: Optional[list] = None,
                     order_by: Optional[List[str]] = None) -> Dict[str, Any]:
        """POST /on_page/pages — the crawled pages with their checks."""
        return self._report("pages", task_id, {"limit": limit, "offset": offset,
                                               "filters": filters, "order_by": order_by})

    def onpage_non_indexable(self, task_id: str, limit: Optional[int] = None,
                             offset: Optional[int] = None,
                             filters: Optional[list] = None) -> Dict[str, Any]:
        """POST /on_page/non_indexable — pages search engines cannot index, and why."""
        return self._report("non_indexable", task_id,
                            {"limit": limit, "offset": offset, "filters": filters})

    def onpage_duplicate_tags(self, task_id: str, type: str = "duplicate_title",
                              limit: Optional[int] = None,
                              offset: Optional[int] = None) -> Dict[str, Any]:
        """POST /on_page/duplicate_tags — pages sharing a title
        (`duplicate_title`) or a description (`duplicate_description`)."""
        return self._report("duplicate_tags", task_id,
                            {"type": type, "limit": limit, "offset": offset})

    def onpage_links(self, task_id: str, limit: Optional[int] = None,
                     offset: Optional[int] = None, filters: Optional[list] = None,
                     options: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """POST /on_page/links — links found on the crawled pages (e.g. filter
        `["is_broken", "=", true]`)."""
        return self._report("links", task_id, {"limit": limit, "offset": offset,
                                               "filters": filters, **(options or {})})

    def onpage_redirect_chains(self, task_id: str, limit: Optional[int] = None,
                               offset: Optional[int] = None) -> Dict[str, Any]:
        """POST /on_page/redirect_chains — chains of redirects, loops flagged."""
        return self._report("redirect_chains", task_id, {"limit": limit, "offset": offset})
