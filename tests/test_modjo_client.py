"""Contrat du client Modjo (API v2, `Authorization: Bearer`).

Mocke `requests.Session.request` : verbes et chemins relevés dans l'OpenAPI
publique v2, en-tête d'auth, encodage des listes, bornes, re-tentatives — et
les pièges propres à Modjo, chacun verrouillé par un test :

- `date_from`/`date_to` partent en `from`/`to` ;
- `ids` et `expand` joints par virgule ;
- un id d'appel ne sort jamais du chemin ;
- un 429 attend `X-RateLimit-Reset` ; l'import d'un appel n'est jamais rejoué.
"""
from __future__ import annotations

import pytest

from oto.tools.common.credentials import MissingCredential
from oto.tools.common.errors import UpstreamHTTPError
from oto.tools.modjo import client as mc
from oto.tools.modjo import ModjoClient, has_next_page

BASE = "https://api.modjo.ai/v2"
UUID = "0b6c3f7e-2a41-4d0c-9a51-3f1e2d7c8b90"


class _Resp:
    def __init__(self, status_code: int = 200, body=None, headers=None):
        self.status_code = status_code
        self._body = body if body is not None else {"data": []}
        self.content = b"" if status_code == 204 else b"x"
        self.text = str(self._body)
        self.headers = headers or {}

    def json(self):
        return self._body


@pytest.fixture()
def capture(monkeypatch):
    seen = {"calls": [], "responses": [], "sleeps": []}

    def fake_request(self, method, url, **kwargs):
        seen.update(method=method, url=url, kwargs=kwargs, headers=dict(self.headers))
        seen["calls"].append((method, url))
        if seen["responses"]:
            return seen["responses"].pop(0)
        return _Resp(200)

    monkeypatch.setattr(mc.requests.Session, "request", fake_request)
    monkeypatch.setattr(mc.time, "sleep", seen["sleeps"].append)
    return seen


@pytest.fixture()
def cli():
    return ModjoClient(api_key="mj_test")


def test_the_key_is_required():
    with pytest.raises(MissingCredential):
        ModjoClient(api_key=None)


def test_bearer_header_and_no_redirect(capture, cli):
    cli.list_tags()
    assert capture["headers"]["Authorization"] == "Bearer mj_test"
    assert capture["kwargs"]["allow_redirects"] is False
    assert capture["url"] == f"{BASE}/tags"


def test_list_calls_maps_dates_and_joins_lists(capture, cli):
    cli.list_calls(ids=[1, 2], date_from="2026-10-01T00:00:00Z", date_to="2026-10-08T00:00:00Z",
                   user_id=42, expand=["contacts", "transcript", "contacts"], size=50)
    assert capture["kwargs"]["params"] == {
        "ids": "1,2", "from": "2026-10-01T00:00:00Z", "to": "2026-10-08T00:00:00Z",
        "user_id": 42, "expand": "contacts,transcript", "size": 50}


@pytest.mark.parametrize("bad", [{"expand": ["highlights"]}, {"expand": "tags"}, {"size": 101},
                                 {"page": 0}, {"ids": []}, {"user_id": True},
                                 {"recording_retention_status": "gone"}])
def test_list_calls_refuses_before_the_call(capture, cli, bad):
    with pytest.raises(ValueError):
        cli.list_calls(**bad)
    assert capture["calls"] == []


@pytest.mark.parametrize("call_id", ["123", 123, UUID])
def test_call_id_is_digits_or_uuid(capture, cli, call_id):
    cli.get_call_transcript(call_id)
    assert capture["url"] == f"{BASE}/calls/{call_id}/transcript"


@pytest.mark.parametrize("call_id", ["..", "12/../users", "", "abc", None, True])
def test_call_id_never_leaves_the_path(capture, cli, call_id):
    with pytest.raises(ValueError):
        cli.get_call(call_id)
    assert capture["calls"] == []


def test_sub_resources_paths(capture, cli):
    for method, suffix in ((cli.list_call_summaries, "summaries"), (cli.list_call_notes, "notes"),
                           (cli.list_call_next_steps, "next-steps"), (cli.get_call_recording, "recording"),
                           (cli.list_call_crm_filling_answers, "crm-filling-answers"),
                           (cli.list_call_tags, "tags")):
        method("7")
        assert capture["calls"][-1] == ("GET", f"{BASE}/calls/7/{suffix}")


def test_tag_writes(capture, cli):
    capture["responses"] = [_Resp(201, {"callId": 7, "tagId": 3}), _Resp(204)]
    assert cli.add_call_tag("7", 3) == {"callId": 7, "tagId": 3}
    assert capture["kwargs"]["json"] == {"tagId": 3}
    assert cli.remove_call_tag("7", 3) == {}
    assert capture["calls"][-1] == ("DELETE", f"{BASE}/calls/7/tags/3")


def test_a_429_waits_for_the_window_then_retries_a_read(capture, cli):
    capture["responses"] = [_Resp(429, {"code": "rate_limited"}, {"X-RateLimit-Reset": "12"}),
                            _Resp(200, {"data": []})]
    cli.list_users(email="jane@example.com")
    assert capture["sleeps"] == [12.0] and len(capture["calls"]) == 2


def test_the_wait_is_bounded(capture, cli):
    capture["responses"] = [_Resp(429, {}, {"X-RateLimit-Reset": "3600"}), _Resp(200)]
    cli.list_tags()
    assert capture["sleeps"] == [mc.MAX_RESET_WAIT]


def test_an_import_is_never_replayed(capture, cli):
    capture["responses"] = [_Resp(503, {"code": "internal_error"})]
    with pytest.raises(UpstreamHTTPError) as error:
        cli.upload_call("https://storage.example.com/a.mp3", "2026-10-12T09:30:00Z",
                        [{"email": "jane@company.example", "type": "user"}])
    assert error.value.status_code == 503 and len(capture["calls"]) == 1


def test_upload_body_and_checks(capture, cli):
    capture["responses"] = [_Resp(202, {"callId": UUID, "status": "processing"})]
    cli.upload_call("https://storage.example.com/a.mp3", "2026-10-12T09:30:00Z",
                    [{"email": "jane@company.example", "type": "user"}],
                    deal={"crm": "hubspot", "crmId": "123"}, crm_activity_id="act-1")
    assert capture["kwargs"]["json"] == {
        "downloadMediaUrl": "https://storage.example.com/a.mp3", "date": "2026-10-12T09:30:00Z",
        "participants": [{"email": "jane@company.example", "type": "user"}],
        "deal": {"crm": "hubspot", "crmId": "123"}, "crmActivityId": "act-1"}
    for media, people in (("http://storage.example.com/a.mp3", [{"email": "a@b.c", "type": "user"}]),
                          ("https://s.example.com/a.mp3", [{"email": "a@b.c", "type": "contact"}]),
                          ("https://s.example.com/a.mp3", [{"email": "a@b.c"}])):
        with pytest.raises(ValueError):
            cli.upload_call(media, "2026-10-12T09:30:00Z", people)


def test_reviews_query_names(capture, cli):
    cli.list_call_reviews(start_date_time="2026-09-01T00:00:00Z", order="asc")
    assert capture["kwargs"]["params"] == {"startDateTime": "2026-09-01T00:00:00Z", "order": "asc"}


def test_directory_paths(capture, cli):
    cli.list_deals(account_id=4, status="Closed won")
    assert capture["kwargs"]["params"] == {"account_id": 4, "status": "Closed won"}
    cli.get_deal_summary(9)
    assert capture["calls"][-1] == ("GET", f"{BASE}/deals/9/summary")
    cli.list_team_members(3, page=2)
    assert capture["calls"][-1] == ("GET", f"{BASE}/teams/3/members")
    cli.list_crm_filling_template_fields(UUID)
    assert capture["calls"][-1] == ("GET", f"{BASE}/crm-filling-templates/{UUID}/fields")
    with pytest.raises(ValueError):
        cli.get_crm_filling_template("../webhooks")


def test_ask_agent_is_long_and_never_replayed(capture, cli):
    capture["responses"] = [_Resp(504, {"code": "upstream_timeout"})]
    with pytest.raises(UpstreamHTTPError):
        cli.ask_agent("call", "123", instructions="Did they agree on a price?",
                      schema={"type": "object", "properties": {"agreed": {"type": "boolean"}}})
    assert len(capture["calls"]) == 1
    assert capture["kwargs"]["timeout"] == mc.ASK_TIMEOUT
    assert capture["kwargs"]["json"]["scope"] == {"type": "call", "id": 123}
    assert capture["kwargs"]["json"]["responseFormat"]["json_schema"]["name"] == "answer"


def test_has_next_page():
    assert has_next_page({"pagination": {"page": 1, "size": 25, "total": 26}})
    assert not has_next_page({"pagination": {"page": 2, "size": 25, "total": 50}})
    assert not has_next_page({"data": []})
