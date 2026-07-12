"""Branch matrix for lengua_core.prompts — pure string assembly, no I/O.

Covers the two behavior-defining builders:
- system_instruction() over the (vowelized x level) branch matrix, and
- suggestion_instruction() over the (known_words empty/non-empty x topic present/absent) matrix.

Assertions reference the module's own template constants (not hard-coded prose) so they track edits
to the templates instead of going stale.
"""
from __future__ import annotations

from collections.abc import Iterator

import pytest

from lengua_core import prompts
from lengua_core.prompts import (
    GENERATION_INSTRUCTION,
    LEVEL_INSTRUCTION,
    OUTPUT_FORMAT,
    RULES_PROMPT,
    VOCALIZATION_INSTRUCTION,
    suggestion_instruction,
    system_instruction,
)

pytestmark = pytest.mark.disable_socket


@pytest.fixture
def _restore_source() -> Iterator[None]:
    """Clear the module-global prompt source after a test that installs one (offline, no store)."""
    yield
    prompts.set_prompt_source(None)

# Substrings unique to the two optional blocks, used to assert whether each branch was taken.
_VOCAL_MARKER = "fully vocalized"  # only in VOCALIZATION_INSTRUCTION
_LEVEL_MARKER = "CEFR level"  # only in LEVEL_INSTRUCTION


# ── system_instruction: (vowelized x level) matrix ────────────────────────────
def test_system_instruction_plain_has_rules_and_output_only() -> None:
    out = system_instruction("Spanish")
    assert RULES_PROMPT in out
    assert GENERATION_INSTRUCTION.format(language="Spanish") in out
    assert out.endswith(OUTPUT_FORMAT.format(language="Spanish"))
    assert _VOCAL_MARKER not in out  # vowelized branch NOT taken
    assert _LEVEL_MARKER not in out  # level branch NOT taken


def test_system_instruction_vowelized_appends_vocalization() -> None:
    out = system_instruction("Arabic", vowelized=True)
    assert VOCALIZATION_INSTRUCTION.format(language="Arabic") in out
    assert _LEVEL_MARKER not in out


@pytest.mark.parametrize("level", ["A1", "A2", "B1", "B2", "C1", "C2"])
def test_system_instruction_level_appends_and_interpolates(level: str) -> None:
    out = system_instruction("French", level=level)
    assert LEVEL_INSTRUCTION.format(language="French", level=level) in out
    assert _VOCAL_MARKER not in out


def test_system_instruction_empty_level_is_treated_as_absent() -> None:
    # `if level:` is a truthiness test — "" must skip the level block, same as None.
    assert _LEVEL_MARKER not in system_instruction("French", level="")
    assert _LEVEL_MARKER not in system_instruction("French", level=None)


def test_system_instruction_vowelized_and_level_appends_both_in_order() -> None:
    out = system_instruction("Hebrew", vowelized=True, level="B1")
    vocal = out.index(VOCALIZATION_INSTRUCTION.format(language="Hebrew"))
    level = out.index(LEVEL_INSTRUCTION.format(language="Hebrew", level="B1"))
    output = out.index(OUTPUT_FORMAT.format(language="Hebrew"))
    assert vocal < level < output  # vocalization -> level -> output format, output last


# ── suggestion_instruction: (known_words x topic) matrix ──────────────────────
_NO_PRIOR = "no prior vocabulary yet"
_KNOWS = "already knows these words"
_TOPIC = "Focus on the topic or domain:"


def test_suggestion_empty_words_no_topic() -> None:
    out = suggestion_instruction("Spanish", "A2", [], 5)
    assert _NO_PRIOR in out and _KNOWS not in out
    assert _TOPIC not in out
    assert "exactly 5" in out and "CEFR A2" in out and "Spanish vocabulary coach" in out


def test_suggestion_known_words_no_topic_lists_them() -> None:
    out = suggestion_instruction("Spanish", "B1", ["hola", "gato"], 3)
    assert _KNOWS in out and _NO_PRIOR not in out
    assert "hola, gato" in out  # ", ".join(known_words)
    assert _TOPIC not in out


def test_suggestion_empty_words_with_topic() -> None:
    out = suggestion_instruction("Spanish", "A2", [], 4, topic="cooking")
    assert _NO_PRIOR in out
    assert f"{_TOPIC} cooking." in out


def test_suggestion_known_words_with_topic() -> None:
    out = suggestion_instruction("Spanish", "C1", ["perro"], 2, topic="law")
    assert _KNOWS in out and "perro" in out
    assert f"{_TOPIC} law." in out


def test_suggestion_empty_topic_is_treated_as_absent() -> None:
    # `if topic:` truthiness — "" must not emit the topic line.
    assert _TOPIC not in suggestion_instruction("Spanish", "A2", [], 5, topic="")


# ── Render guard: a malformed DB override falls back to the code default (#150) ────────────────────
# A DB override is fed into ``str.format``; a bad template (unknown/positional placeholder, stray
# brace) must NOT raise across every generation request — it must degrade that one fragment to its
# code default and log loudly. These install a raw per-key source (no store) to inject a bad override.


def _install_source(overrides: dict[str, str]) -> None:
    """Install a per-key source returning ``overrides[key]`` (or None) — the legacy no-snapshot path."""
    prompts.set_prompt_source(lambda key: overrides.get(key))


@pytest.mark.parametrize(
    "bad_template",
    [
        "You teach {unknown_placeholder} — bad.",  # unknown named field → KeyError
        "You teach {0} — positional.",  # positional field → IndexError
        "You teach {} — auto-positional.",  # auto-numbered field → IndexError
        "You teach {language — stray unbalanced brace.",  # malformed → ValueError
        "You teach {language.foo} — bad attribute.",  # attribute access on a str → AttributeError
        "You teach {language[foo]} — bad index.",  # index access on a str → TypeError
    ],
)
def test_system_instruction_bad_override_falls_back_to_code_default(
    bad_template: str, _restore_source: None, caplog: pytest.LogCaptureFixture
) -> None:
    """A malformed ``generation_instruction`` override renders the code default instead of raising."""
    _install_source({prompts.KEY_GENERATION_INSTRUCTION: bad_template})
    with caplog.at_level("ERROR"):
        out = system_instruction("Spanish", level="A2")
    # The bad fragment degraded to its code default (interpolated), not the raw broken template.
    assert GENERATION_INSTRUCTION.format(language="Spanish") in out
    assert "unknown_placeholder" not in out and "auto-positional" not in out
    # Other fragments are unaffected and the failure was logged loudly.
    assert LEVEL_INSTRUCTION.format(language="Spanish", level="A2") in out
    assert any(
        prompts.KEY_GENERATION_INSTRUCTION in r.getMessage() for r in caplog.records
    )


def test_suggestion_instruction_bad_override_falls_back_to_code_default(
    _restore_source: None, caplog: pytest.LogCaptureFixture
) -> None:
    """A malformed ``suggestion_instruction`` override degrades to the code default, no raise."""
    _install_source({prompts.KEY_SUGGESTION_INSTRUCTION: "Pick {count} in {no_such_field}."})
    with caplog.at_level("ERROR"):
        out = suggestion_instruction("French", "B1", ["a"], 3, topic="travel")
    # Fell back to the full code default (still interpolated with the real fields).
    assert "French vocabulary coach" in out and "exactly 3" in out
    assert f"{_TOPIC} travel." in out


def test_good_override_still_renders_normally(_restore_source: None) -> None:
    """A well-formed override is still used verbatim (the guard doesn't over-trigger)."""
    _install_source({prompts.KEY_GENERATION_INSTRUCTION: "Teach me {language} now."})
    out = system_instruction("German")
    assert "Teach me German now." in out


def test_rules_override_with_literal_braces_is_not_formatted(_restore_source: None) -> None:
    """The ``rules`` block is appended verbatim — literal braces in an override are preserved."""
    _install_source({prompts.KEY_RULES: "Rules with a literal {brace} kept as-is."})
    out = system_instruction("Spanish")
    assert "Rules with a literal {brace} kept as-is." in out
