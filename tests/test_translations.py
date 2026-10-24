"""Keep the translation files consistent with each other."""

import json
from pathlib import Path
from typing import Any

import pytest

INTEGRATION = Path(__file__).parent.parent / "custom_components" / "intradel"


def _load(relative: str) -> dict[str, Any]:
    return json.loads((INTEGRATION / relative).read_text(encoding="utf-8"))


def _keys(node: Any, prefix: str = "") -> set[str]:
    """Every leaf path of a nested translation file."""
    if not isinstance(node, dict):
        return {prefix}
    return {key for name, child in node.items() for key in _keys(child, f"{prefix}.{name}")}


def test_strings_json_is_the_english_translation() -> None:
    """strings.json is the source file; en.json must not drift from it."""
    assert _load("strings.json") == _load("translations/en.json")


@pytest.mark.parametrize("language", ["fr"])
def test_translation_covers_every_english_string(language: str) -> None:
    """A string added to English must be translated in every other language."""
    english = _keys(_load("translations/en.json"))
    translated = _keys(_load(f"translations/{language}.json"))

    assert translated == english
