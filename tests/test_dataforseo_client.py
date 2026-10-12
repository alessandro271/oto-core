"""DataForSEO client contract (Basic auth, one task per POST, errors in the body).

Mocks `requests.Session.request`: checks path, method, body (ONE task in a
list, None options dropped so the API applies its defaults) and the mapping of
the five-digit body status to a typed `UpstreamHTTPError`.
"""
from __future__ import annotations

import pytest

from oto.tools.common.credentials import MissingCredential
from oto.tools.common.errors import UpstreamHTTPError
from oto.tools.dataforseo import DataForSeoClient
from oto.tools.dataforseo import client as dfs
from oto.tools.http.client import RedirectRefused

BASE = "https://api.dataforseo.com/v3"


class _Resp:
    def __init__(self, status_code: int, body, headers=None):
        self.status_code = status_code
        self._body = body
        self.content = b"x"
        self.text = str(body)
        self.headers = headers or {}

    def json(self):
        return self._body


def _ok(result=None, cost=0.0101):
    return {"version": "0.1", "status_code": 20000, "status_message": "Ok.",
            "cost": cost, "tasks_count": 1, "tasks_error": 0,
            "tasks": [{"id": "t1", "status_code": 20000, "status_message": "Ok.",
                       "cost": cost, "result_count": 1, "result": result or [{}]}]}


@pytest.fixture()
def capture(monkeypatch):
    seen = {"calls": [], "reply": _Resp(200, _ok())}

    def fake_request(self, method, url, **kwargs):
        seen["calls"].append({"method": method, "url": url, "kwargs": kwargs,
                              "auth": self.auth})
        return seen["reply"]

    monkeypatch.setattr(dfs.requests.Session, "request", fake_request)
    return seen


def _client():
    return DataForSeoClient(login="me@acme.com", password="s3cr3t")


def test_credentials_are_required():
    with pytest.raises(MissingCredential):
        DataForSeoClient(login="me@acme.com", password=None)
    with pytest.raises(MissingCredential):
        DataForSeoClient(login=None, password="x")


def test_basic_auth_never_in_url(capture):
    _client().backlinks_summary("acme.com")
    call = capture["calls"][0]
    assert call["auth"] == ("me@acme.com", "s3cr3t")
    assert "s3cr3t" not in call["url"]
    assert "params" not in call["kwargs"]
    assert call["kwargs"]["allow_redirects"] is False


def test_one_task_in_a_list_and_none_dropped(capture):
    _client().keyword_ideas(["crm"], location_code=2250, language_code="fr", limit=50)
    call = capture["calls"][0]
    assert call["method"] == "POST"
    assert call["url"] == f"{BASE}/dataforseo_labs/google/keyword_ideas/live"
    assert call["kwargs"]["json"] == [{"keywords": ["crm"], "location_code": 2250,
                                       "language_code": "fr", "limit": 50}]


def test_options_pass_through(capture):
    _client().ranked_keywords("acme.com", location_name="France",
                              options={"include_clickstream_data": True})
    task = capture["calls"][0]["kwargs"]["json"][0]
    assert task == {"target": "acme.com", "location_name": "France",
                    "include_clickstream_data": True}


def test_returns_the_task_with_its_cost(capture):
    capture["reply"] = _Resp(200, _ok(result=[{"items": [1]}], cost=0.02))
    t = _client().domain_rank_overview("acme.com")
    assert t["cost"] == 0.02
    assert t["result"] == [{"items": [1]}]


@pytest.mark.parametrize("method,args,path", [
    ("keyword_overview", (["a"],), "/dataforseo_labs/google/keyword_overview/live"),
    ("keyword_suggestions", ("a",), "/dataforseo_labs/google/keyword_suggestions/live"),
    ("related_keywords", ("a",), "/dataforseo_labs/google/related_keywords/live"),
    ("bulk_keyword_difficulty", (["a"],), "/dataforseo_labs/google/bulk_keyword_difficulty/live"),
    ("search_intent", (["a"],), "/dataforseo_labs/google/search_intent/live"),
    ("google_ads_search_volume", (["a"],), "/keywords_data/google_ads/search_volume/live"),
    ("competitors_domain", ("a.com",), "/dataforseo_labs/google/competitors_domain/live"),
    ("domain_intersection", ("a.com", "b.com"), "/dataforseo_labs/google/domain_intersection/live"),
    ("relevant_pages", ("a.com",), "/dataforseo_labs/google/relevant_pages/live"),
    ("keywords_for_site", ("a.com",), "/dataforseo_labs/google/keywords_for_site/live"),
    ("bulk_traffic_estimation", (["a.com"],), "/dataforseo_labs/google/bulk_traffic_estimation/live"),
    ("backlinks_list", ("a.com",), "/backlinks/backlinks/live"),
    ("referring_domains", ("a.com",), "/backlinks/referring_domains/live"),
    ("anchors", ("a.com",), "/backlinks/anchors/live"),
    ("bulk_ranks", (["a.com"],), "/backlinks/bulk_ranks/live"),
])
def test_paths(capture, method, args, path):
    getattr(_client(), method)(*args)
    call = capture["calls"][0]
    assert (call["method"], call["url"]) == ("POST", BASE + path)
    assert isinstance(call["kwargs"]["json"], list) and len(call["kwargs"]["json"]) == 1


def test_account_reads_are_get_without_body(capture):
    _client().user_data()
    _client().labs_locations_and_languages()
    assert [(c["method"], c["url"], c["kwargs"]["json"]) for c in capture["calls"]] == [
        ("GET", f"{BASE}/appendix/user_data", None),
        ("GET", f"{BASE}/dataforseo_labs/locations_and_languages", None)]


@pytest.mark.parametrize("code,http", [
    (40100, 401), (40104, 403), (40200, 402), (40210, 402), (40202, 429), (40400, 404),
    (40501, 400), (40000, 400), (50000, 502), (None, 502),
])
def test_task_error_in_200_body_is_typed(capture, code, http):
    body = _ok()
    body["tasks"][0].update(status_code=code, status_message="boom", result=None)
    capture["reply"] = _Resp(200, body)
    with pytest.raises(UpstreamHTTPError) as e:
        _client().backlinks_summary("acme.com")
    assert e.value.status_code == http
    assert e.value.body == {"status_code": code, "status_message": "boom"}


def test_request_level_error_is_typed(capture):
    capture["reply"] = _Resp(200, {"status_code": 40200,
                                   "status_message": "Payment Required.", "tasks": []})
    with pytest.raises(UpstreamHTTPError) as e:
        _client().keyword_overview(["a"], location_code=2840, language_code="en")
    assert e.value.status_code == 402


def test_http_error_is_typed(capture):
    capture["reply"] = _Resp(401, {"status_code": 40100,
                                   "status_message": "You are not authorized."})
    with pytest.raises(UpstreamHTTPError) as e:
        _client().user_data()
    assert e.value.status_code == 401


def test_empty_tasks_is_an_upstream_failure(capture):
    capture["reply"] = _Resp(200, {"status_code": 20000, "tasks": []})
    with pytest.raises(UpstreamHTTPError) as e:
        _client().user_data()
    assert e.value.status_code == 502


def test_redirect_is_refused(capture):
    capture["reply"] = _Resp(302, {}, headers={"Location": "https://elsewhere.example/x"})
    with pytest.raises(RedirectRefused):
        _client().user_data()


@pytest.mark.parametrize("method,args,path", [
    ("google_trends_explore", (["a"],), "/keywords_data/google_trends/explore/live"),
    ("historical_rank_overview", ("a.com",), "/dataforseo_labs/google/historical_rank_overview/live"),
    ("serp_competitors", (["a"],), "/dataforseo_labs/google/serp_competitors/live"),
    ("subdomains", ("a.com",), "/dataforseo_labs/google/subdomains/live"),
    ("backlinks_competitors", ("a.com",), "/backlinks/competitors/live"),
    ("backlinks_history", ("a.com",), "/backlinks/history/live"),
    ("backlinks_new_lost", ("a.com",), "/backlinks/timeseries_new_lost_summary/live"),
    ("backlinks_domain_pages", ("a.com",), "/backlinks/domain_pages/live"),
    ("llm_mentions_search", ([{"domain": "a.com"}],), "/ai_optimization/llm_mentions/search_mentions/live"),
    ("llm_mentions_metrics", ([{"domain": "a.com"}],), "/ai_optimization/llm_mentions/target_metrics/live"),
    ("llm_mentions_top_domains", ([{"keyword": "a"}],), "/ai_optimization/llm_mentions/top_mentioned_domains/live"),
    ("llm_mentions_top_pages", ([{"keyword": "a"}],), "/ai_optimization/llm_mentions/top_mentioned_pages/live"),
    ("llm_mentions_history", ([{"domain": "a.com"}],), "/ai_optimization/llm_mentions/historical/live"),
    ("google_ai_mode", ("a",), "/serp/google/ai_mode/live/advanced"),
    ("ai_keyword_search_volume", (["a"],), "/ai_optimization/ai_keyword_data/keywords_search_volume/live"),
    ("onpage_instant", ("https://a.com",), "/on_page/instant_pages"),
    ("onpage_content", ("https://a.com",), "/on_page/content_parsing/live"),
    ("lighthouse", ("https://a.com",), "/on_page/lighthouse/live/json"),
    ("onpage_pages", ("t1",), "/on_page/pages"),
    ("onpage_non_indexable", ("t1",), "/on_page/non_indexable"),
    ("onpage_duplicate_tags", ("t1",), "/on_page/duplicate_tags"),
    ("onpage_links", ("t1",), "/on_page/links"),
    ("onpage_redirect_chains", ("t1",), "/on_page/redirect_chains"),
    ("domain_technologies", ("a.com",), "/domain_analytics/technologies/domain_technologies/live"),
    ("domains_by_technology", (["Shopify"],), "/domain_analytics/technologies/domains_by_technology/live"),
    ("technologies_summary", (["Shopify"],), "/domain_analytics/technologies/technologies_summary/live"),
    ("content_search", ("acme",), "/content_analysis/search/live"),
    ("content_summary", ("acme",), "/content_analysis/summary/live"),
])
def test_paths_more(capture, method, args, path):
    getattr(_client(), method)(*args)
    call = capture["calls"][0]
    assert (call["method"], call["url"]) == ("POST", BASE + path)
    assert isinstance(call["kwargs"]["json"], list) and len(call["kwargs"]["json"]) == 1


def test_llm_response_path_per_engine(capture):
    _client().llm_response("perplexity", "best crm?", "sonar")
    call = capture["calls"][0]
    assert call["url"] == f"{BASE}/ai_optimization/perplexity/llm_responses/live"
    assert call["kwargs"]["json"] == [{"user_prompt": "best crm?", "model_name": "sonar"}]
    with pytest.raises(ValueError):
        _client().llm_response("copilot", "x", "y")


def test_intersection_targets_are_numbered(capture):
    _client().backlinks_intersection(["a.com", "b.com"], exclude_targets=["me.com"])
    task = capture["calls"][0]["kwargs"]["json"][0]
    assert task["targets"] == {"1": "a.com", "2": "b.com"}
    assert task["exclude_targets"] == ["me.com"]


def test_crawl_start_accepts_task_created(capture):
    body = _ok(result=None, cost=0.00075)
    body["tasks"][0]["status_code"] = 20100
    capture["reply"] = _Resp(200, body)
    t = _client().onpage_crawl_start("a.com", 5)
    assert t["cost"] == 0.00075
    assert capture["calls"][0]["kwargs"]["json"] == [{"target": "a.com", "max_crawl_pages": 5}]


def test_task_created_is_an_error_on_a_live_call(capture):
    body = _ok()
    body["tasks"][0]["status_code"] = 20100
    capture["reply"] = _Resp(200, body)
    with pytest.raises(UpstreamHTTPError):
        _client().backlinks_summary("a.com")


def test_summary_is_a_get(capture):
    _client().onpage_summary("t1")
    _client().llm_models("chat_gpt")
    assert [(c["method"], c["url"]) for c in capture["calls"]] == [
        ("GET", f"{BASE}/on_page/summary/t1"),
        ("GET", f"{BASE}/ai_optimization/chat_gpt/llm_responses/models")]
