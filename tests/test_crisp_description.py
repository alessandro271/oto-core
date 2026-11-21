"""La description `crisp` 1.1.0 : la messagerie client de Crisp ; son client : `test_crisp_client.py`.

Gardes : chaque lecture (`class: read`, jamais `act`) est servie par un `GET`, chaque écriture par un `POST` ou un
`PATCH`, jamais un `DELETE` ; l'envoi d'un message au contact est la seule fonction qui envoie (`sensitive`, `effect:
send`, avec son résumé de confirmation), et les deux listes de segments, envoyées entières, sont déclarées comme
remplaçant (`sensitive`, `effect: destroy`) ; rien n'écrit dans la base de connaissances ; le compte est le jeton
de site (identifiant et clé en Basic, en-tête `X-Crisp-Tier: website`) et l'identifiant du site est un réglage du
compte, cité par `base_url`, jamais un argument ; chaque fonction qui lit une conversation, un message ou un contact
dit à l'agent que le contenu peut porter des données personnelles ou de santé, et de ne pas chercher une personne par
son nom ou son téléphone sans nécessité ; un argument qui peut désigner une personne est `personal`.
"""
from __future__ import annotations

import copy

import yaml

from fabrique.descriptions import CONNECTORS, check
from fabrique.typescript import connector_module

CRISP = CONNECTORS / "crisp" / "connector.yaml"
PRIVACY = (
    "May contain personal or health data: read only what the task needs, and do not look a person up by name or "
    "phone number unless the task requires it."
)
WRITES = {
    "add_conversation_note": "write", "change_conversation_state": "write", "update_conversation_meta": "write",
    "set_conversation_segments": "sensitive", "send_message": "sensitive", "update_person": "write",
    "update_person_data": "write", "set_person_segments": "sensitive",
}
HELPDESK_OR_WORKSPACE = {
    "get_website", "list_inboxes", "get_inbox", "get_helpdesk", "list_helpdesk_locales", "list_helpdesk_pages",
    "list_helpdesk_tree", "get_helpdesk_entry", "get_helpdesk_content", "get_helpdesk_metadata",
}


def _description() -> dict:
    return copy.deepcopy(yaml.safe_load(CRISP.read_text(encoding="utf-8")))


def _functions() -> list[dict]:
    return _description()["functions"]


def test_description_passes_the_fabrique():
    module = connector_module(check(_description(), CRISP))
    assert module.generated and module.skipped == []


def test_every_read_is_a_get_and_every_write_a_post_or_a_patch():
    for function in _functions():
        name = function["name"]
        if name in WRITES:
            assert function["class"] == WRITES[name], name
            assert function.get("act", True) is True, name
            assert function["call"]["method"] in ("POST", "PATCH"), name
            assert not name.startswith(("get_", "list_", "search_")), name
        else:
            assert function["class"] == "read", name
            assert function.get("act", False) is False, name
            assert function["call"]["method"] == "GET", name
            assert "body" not in function["call"] and "confirm" not in function, name


def test_only_send_message_sends_and_it_says_it_cannot_be_taken_back():
    by_name = {f["name"]: f for f in _functions()}
    assert {n for n, f in by_name.items() if f.get("effect") == "send"} == {"send_message"}
    send = by_name["send_message"]
    assert send["call"]["constants"]["body"] == {"type": "text", "from": "operator", "origin": "chat"}
    assert "cannot be taken back" in send["confirm"]["summary"]
    assert "cannot be taken back" in " ".join(send["description"].split())
    note = by_name["add_conversation_note"]
    assert note["call"]["constants"]["body"] == {"type": "note", "from": "operator", "origin": "chat"}


def test_the_segment_lists_are_declared_as_replacing():
    for name in ("set_conversation_segments", "set_person_segments"):
        function = next(f for f in _functions() if f["name"] == name)
        assert function["effect"] == "destroy" and "confirm" in function, name
        assert function["call"]["body"] == {"segments": "segments"}, name


def test_nothing_writes_the_knowledge_base():
    for function in _functions():
        if function["name"] in WRITES:
            assert "helpdesk" not in function["call"]["path"], function["name"]


def test_the_account_is_a_website_token_and_the_website_id_a_setting():
    connector = _description()["connector"]
    assert connector["auth"] == {"kind": "basic", "username": "token_identifier", "password": "token_key"}
    assert connector["headers"] == {"X-Crisp-Tier": "website"}
    assert connector["base_url"] == "https://api.crisp.chat/v1/website/{website_id}"
    assert [s["name"] for s in connector["settings"]] == ["website_id"]
    for function in _functions():
        assert "website_id" not in function["input"]["properties"], function["name"]


def test_conversations_messages_and_contacts_carry_the_privacy_notice():
    readers = [f for f in _functions() if f["name"] not in HELPDESK_OR_WORKSPACE | set(WRITES)]
    assert {f["name"] for f in readers} == {
        "list_conversations", "search_conversations", "get_conversation", "get_conversation_meta",
        "list_conversation_messages", "list_people", "search_people", "get_person", "get_person_data",
        "list_person_conversations",
    }
    for function in readers:
        assert PRIVACY in " ".join(function["description"].split()), function["name"]


def test_an_argument_that_may_name_a_person_is_personal():
    by_name = {f["name"]: f["input"]["properties"] for f in _functions()}
    for name, argument in [("get_person", "people_id"), ("get_person_data", "people_id"),
                           ("list_person_conversations", "people_id"), ("search_people", "search_text"),
                           ("search_conversations", "search_query"), ("send_message", "content"),
                           ("add_conversation_note", "content"), ("update_person", "email"),
                           ("update_person", "nickname"), ("update_person", "phone"),
                           ("update_conversation_meta", "email"), ("update_conversation_meta", "phone")]:
        assert by_name[name][argument].get("personal") is True, (name, argument)
