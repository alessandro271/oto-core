"""The Modjo client follows its description: one method per function, same
arguments, and no module of 500 lines or more."""

import inspect
import pathlib

import pytest
import yaml

from oto.tools.modjo import ModjoClient

ROOT = pathlib.Path(__file__).resolve().parent.parent
DESCRIPTION = yaml.safe_load((ROOT / "connectors" / "modjo" / "connector.yaml").read_text(encoding="utf-8"))
FUNCTIONS = DESCRIPTION["functions"]


@pytest.mark.parametrize("function", FUNCTIONS, ids=lambda f: f["name"])
def test_each_function_is_a_method_with_the_same_arguments(function):
    method = getattr(ModjoClient, function["name"], None)
    assert callable(method), f"ModjoClient has no {function['name']}"
    params = inspect.signature(method).parameters
    declared = set(function["input"]["properties"])
    assert declared <= set(params)
    for name in function["input"].get("required", []):
        assert params[name].default is inspect.Parameter.empty


def test_only_the_import_is_sensitive_and_only_tags_are_written():
    by_class = {}
    for function in FUNCTIONS:
        by_class.setdefault(function["class"], set()).add(function["name"])
    assert by_class["sensitive"] == {"upload_call"}
    assert by_class["write"] == {"add_call_tag", "remove_call_tag"}


def test_base_url_is_the_described_one():
    assert DESCRIPTION["connector"]["base_url"] == ModjoClient.BASE_URL


def test_modules_stay_under_500_lines():
    package = ROOT / "oto" / "tools" / "modjo"
    for path in package.rglob("*.py"):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 500, path
