"""The prompt pieces attached to every generation request — code defaults + a DB-backed override.

Every fragment below (the numbered ``RULES`` block, the generation / vocalization / level
instructions, the output-format spec, and the suggestion template) has both a **code default**
(the constants in this module — the bootstrap seed *and* the runtime fallback) and an optional
**DB override**. The builders (:func:`system_instruction`, :func:`suggestion_instruction`) keep all
assembly + placeholder interpolation in code; they only source each fragment's *text* through
:func:`resolve_fragment`, which returns the DB override when one is installed and falls back to the
code default otherwise.

**Why a DB override.** So an operator can tweak a prompt in production — or roll back to an older
wording — **without a code change + redeploy**, and keep a full version history of what was tried
(GitHub #80). The override text lives in the ``prompt_versions`` table (append-only, one active
version per key); the app layer (:mod:`app.prompt_store`) reads the active version on a privileged,
RLS-bypassing session, caches it with a TTL, and installs a **synchronous** source hook here via
:func:`set_prompt_source`. This module stays DB-agnostic (it never imports SQLAlchemy or ``app``):
it only knows about a ``key -> text | None`` callable, so :mod:`lengua_core` keeps its "pure, no I/O"
contract and the builders' signatures are unchanged.

**Fallback / no-DB paths.** When no source is installed (the default), or the source returns
``None`` for a key (DB empty / unreachable / that key not seeded), the builder uses the code default.
That keeps the **legacy Streamlit app** (which never installs a source) and the **CI/E2E FakeLLM
path** working against the code constants with zero DB dependency — the "keep legacy runnable" +
"zero real-LLM-call E2E" contracts are untouched.

To add, remove, or change a rule *in code*, edit the ``RULES`` list below — each ``Rule`` is one
numbered section and each string in ``points`` is one bullet. The rendered block (``RULES_PROMPT``)
is the code default for the ``rules`` key; to change it **in production without a redeploy**, add a
new active ``prompt_versions`` row for ``rules`` instead (see ``docs`` / ``apps/api/README.md``).

The output shape (sentence / translation / used_words) is enforced programmatically by
``response_schema`` in lengua_core/gemini.py and described in ``OUTPUT_FORMAT`` below, so the rules
here only govern *how* sentences are written, not their formatting.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

# ── Logical prompt-fragment keys ─────────────────────────────────────────────────────────────────
# The stable string keys under which each fragment is stored/overridden (the ``prompt_versions.key``
# values). Kept as named constants so the builders, the store, the seed migration, and the tests all
# reference the same spelling — a typo can't silently split a fragment into two keys.
KEY_RULES = "rules"
KEY_GENERATION_INSTRUCTION = "generation_instruction"
KEY_VOCALIZATION_INSTRUCTION = "vocalization_instruction"
KEY_LEVEL_INSTRUCTION = "level_instruction"
KEY_OUTPUT_FORMAT = "output_format"
KEY_SUGGESTION_INSTRUCTION = "suggestion_instruction"

#: Every logical fragment key, in a stable order (used by the seed round-trip test + the store).
PROMPT_KEYS: tuple[str, ...] = (
    KEY_RULES,
    KEY_GENERATION_INSTRUCTION,
    KEY_VOCALIZATION_INSTRUCTION,
    KEY_LEVEL_INSTRUCTION,
    KEY_OUTPUT_FORMAT,
    KEY_SUGGESTION_INSTRUCTION,
)


@dataclass
class Rule:
    title: str
    points: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# EDIT HERE to tweak behavior. Add a Rule(...) entry to add a rule; add or edit
# a string in `points` to add or change a bullet.
# ---------------------------------------------------------------------------
RULES: list[Rule] = [
    Rule(
        "Core Principle: Absolute Naturalness Over Everything",
        [
            "Prioritize how a native speaker would naturally choose to phrase things "
            "in casual, real-life conversations.",
            "Never force words together into a sentence if it compromises the flow, "
            "logic, or cultural authenticity. If a sentence feels like a stiff, literal "
            "textbook translation, discard it.",
            "Avoid literal translations of idioms. Choose simpler, punchier, or more "
            "idiomatic contexts that a native speaker would naturally prefer.",
        ],
    ),
    Rule(
        "High-Context & Definitive Scenarios",
        [
            "Ensure the context of the sentence actively reflects and illuminates the "
            "unique meaning, physical characteristics, behavior, or function of the "
            "vocabulary word.",
            'Avoid generic, low-context sentences where the target word could easily be '
            'swapped for almost any other object or concept (e.g., for "dog", do NOT '
            'write "Look at the dog across the street," because "dog" could be replaced '
            'by "car", "tree", or "man").',
            'DO create high-context scenarios that rely on characteristics unique to '
            'that word (e.g., "Don\'t worry, the dog might bark, but it won\'t bite," or '
            '"Please put your dog on a leash so it doesn\'t run into traffic"). The '
            "sentence must make it clear why that exact word is necessary.",
        ],
    ),
    Rule(
        "Word Packing & Complexity",
        [
            "Aim for a sweet spot of 2 to 3 vocabulary words per sentence by grouping "
            "them logically into realistic scenarios.",
            "If words cannot be naturally paired without feeling forced, break them up "
            "into separate, simpler sentences.",
            "You may repeat a vocabulary word across different sentences if it helps "
            "maintain an authentic context.",
            "If the list provides both the singular and plural forms of a noun as "
            "separate entries, generate distinct contexts for each to demonstrate how "
            "their usage naturally shifts in conversation.",
        ],
    ),
    Rule(
        "Grammar & Pronunciation",
        [
            "Conjugate all verbs naturally to fit the specific scenario (even if they "
            "are provided in their root or infinitive forms in the word list).",
            "Include any relevant pronunciation aids, accent marks, or phonetic guides "
            "within the sentence when they are critical for a learner reading the "
            "target language's script.",
        ],
    ),
    Rule(
        "Compulsory Quality Control (The Double-Review Rule)",
        [
            "Before finalizing, review each sentence internally at least twice.",
            "If a sentence feels even slightly forced, awkward, or structurally stiff, "
            "replace it entirely with a more natural, context-rich phrase before "
            "presenting the final output.",
        ],
    ),
]

INTRO = "Please strictly follow the rules and preferences below:"

# Describes each JSON field so the model knows what goes where. Keep in sync with
# lengua/models.py:GeneratedCard (the schema enforces this shape regardless).
OUTPUT_FORMAT = """\
Output format — return a list of items, where each item has exactly these fields:
- "sentence": the example sentence in {language}, with correct spelling, accents, and \
any critical pronunciation aids.
- "translation": a natural English translation of the sentence (faithful, not \
word-for-word).
- "used_words": the list of supplied vocabulary words that appear in the sentence.
- "word_notes": a list of {{"word", "note"}} objects, one for each meaningful word in \
the sentence. "word" is the word exactly as it appears in the sentence (keep all vowel \
marks / diacritics). "note" is a brief gloss — at most two sentences covering its \
meaning and role in this sentence; for a very simple or common word (e.g. "to", "in", \
"and") a single word or short phrase is enough.
Do not add any other text, commentary, or numbering outside these fields."""

# Standing instruction. {language} is filled per request.
GENERATION_INSTRUCTION = """\
You are helping a student learn {language}. Using the vocabulary words supplied by the \
user, write natural example sentences in {language} that follow all the rules above. \
Together, the sentences must use every one of the supplied vocabulary words at least \
once."""

# Appended only for languages flagged as vowelized (per-language toggle).
VOCALIZATION_INSTRUCTION = """\
Write every word in the {language} sentence fully vocalized: include all vowel marks / \
diacritics (e.g., Arabic harakat, Hebrew niqqud) on every word, as in a fully-pointed \
beginner text. The English translation stays unchanged."""

# Appended when the learner's level is known, to size sentence length & complexity.
LEVEL_INSTRUCTION = """\
Write the {language} sentences for a learner at CEFR level {level}. Match that level's \
typical sentence length, grammar, and vocabulary: at A1/A2 keep them short and simple \
with high-frequency words and basic tenses; at B1 use longer connected clauses and common \
idioms; at B2/C1/C2 allow long, multi-clause sentences with richer vocabulary, idioms, and \
varied tenses. The English translation stays natural."""


def _render_rules() -> str:
    blocks = []
    for i, rule in enumerate(RULES, 1):
        bullets = "\n".join(f"  - {p}" for p in rule.points)
        blocks.append(f"#### {i}. {rule.title}\n{bullets}")
    return "\n\n".join(blocks)


# Full rules block (assembled from RULES). Exposed for inspection/debugging AND the code default for
# the ``rules`` key (the DB seed inserts exactly this as version 1).
RULES_PROMPT = INTRO + "\n\n" + _render_rules()

# ── The suggestion-instruction template (Discover) ───────────────────────────────────────────────
# Stored as a **template** with named placeholders. ``{language}``/``{count}``/``{level_band}`` are
# straight interpolations; ``{topic_line}`` and ``{known_block}`` are the two conditionally-assembled
# sub-blocks the builder fills in below (so the wording is DB-overridable while the conditional
# assembly stays in code). The literal ``["word1", "word2"]`` carries no braces, so it is safe under
# ``str.format``.
SUGGESTION_INSTRUCTION = (
    "You are a {language} vocabulary coach.\n\n"
    "Pick exactly {count} vocabulary words in {language} that are appropriate for a "
    "CEFR {level_band} learner. Choose words that are useful, natural, and suited to "
    "that level's typical range — not too simple, not too advanced.{topic_line}\n\n"
    "{known_block}\n\n"
    'Return ONLY a JSON array of {count} strings, e.g. ["word1", "word2"]. '
    "No explanations, no numbering, no extra text."
)

# ── The code-default content for every key (the bootstrap seed + the runtime fallback) ───────────
# Mapping key -> its code-default text. This is the ONE place the seed migration and the fallback
# agree on; a round-trip test asserts the seeded ``prompt_versions`` rows match this exactly.
CODE_DEFAULTS: dict[str, str] = {
    KEY_RULES: RULES_PROMPT,
    KEY_GENERATION_INSTRUCTION: GENERATION_INSTRUCTION,
    KEY_VOCALIZATION_INSTRUCTION: VOCALIZATION_INSTRUCTION,
    KEY_LEVEL_INSTRUCTION: LEVEL_INSTRUCTION,
    KEY_OUTPUT_FORMAT: OUTPUT_FORMAT,
    KEY_SUGGESTION_INSTRUCTION: SUGGESTION_INSTRUCTION,
}


# ── The synchronous DB-override source hook ──────────────────────────────────────────────────────
# A ``key -> text | None`` callable the app layer installs (:func:`set_prompt_source`). ``None`` is
# "no override — use the code default". It is intentionally **synchronous**: the builders run inside
# the blocking provider call (offloaded to a worker thread by ``app.llm_runner``), so they can't
# await; the app layer refreshes an async TTL cache on the event loop *before* dispatching the call
# and this hook reads the already-materialised snapshot. Default: no source (always code defaults) —
# which is exactly the legacy-Streamlit / no-DB behaviour.
_PromptSource = Callable[[str], str | None]
_prompt_source: _PromptSource | None = None


def set_prompt_source(source: _PromptSource | None) -> None:
    """Install (or clear with ``None``) the synchronous DB-override source used by the builders.

    ``source(key)`` returns the active override text for ``key`` or ``None`` to fall back to the code
    default. Installed once at app startup by :mod:`app.prompt_store`; never called by
    :mod:`lengua_core` itself, so this module stays DB-agnostic. Passing ``None`` restores the
    pure code-default behaviour (used by tests and the no-DB paths).
    """
    global _prompt_source
    _prompt_source = source


def resolve_fragment(key: str) -> str:
    """Return the text for ``key``: the installed source's override, else the code default.

    A missing/unknown ``key`` with no source (or a source returning ``None``) falls back to
    :data:`CODE_DEFAULTS`; an unknown key not present there raises ``KeyError`` (a programming error,
    not a runtime override miss). This never performs I/O — it only reads the in-memory snapshot the
    source closes over — so it is safe to call from the provider worker thread.
    """
    source = _prompt_source
    if source is not None:
        override = source(key)
        if override is not None:
            return override
    return CODE_DEFAULTS[key]


def suggestion_instruction(
    language: str,
    level_band: str,
    known_words: list[str],
    count: int,
    topic: str | None = None,
) -> str:
    """System instruction for the word-suggestion step of the Discover feature.

    Asks the model to pick `count` vocabulary words in `language` at `level_band` that are
    not in `known_words`. Optionally constrained to a `topic` domain. The template text comes from
    :func:`resolve_fragment` (DB override or code default); the two conditional sub-blocks
    (``known_block`` / ``topic_line``) are assembled here in code and interpolated in.
    """
    known_block = (
        "The learner already knows these words — do NOT include any of them:\n"
        + ", ".join(known_words)
        if known_words
        else "The learner has no prior vocabulary yet."
    )
    topic_line = f"\nFocus on the topic or domain: {topic}." if topic else ""
    return resolve_fragment(KEY_SUGGESTION_INSTRUCTION).format(
        language=language,
        level_band=level_band,
        count=count,
        known_block=known_block,
        topic_line=topic_line,
    )


def system_instruction(
    language: str, vowelized: bool = False, level: str | None = None
) -> str:
    """Full system instruction for a generation request in `language`.

    When `vowelized`, ask the model to fully vocalize the target-language sentence
    (harakat / nikkud), for scripts with optional diacritics. When `level` (a CEFR band
    like "A2") is given, size sentence length and complexity to that level.

    Each fragment's text comes from :func:`resolve_fragment` (DB override or code default); the
    assembly — which fragments are included, in what order, and their ``{language}`` / ``{level}``
    interpolation — stays here in code.
    """
    parts = [
        resolve_fragment(KEY_RULES),
        resolve_fragment(KEY_GENERATION_INSTRUCTION).format(language=language),
    ]
    if vowelized:
        parts.append(resolve_fragment(KEY_VOCALIZATION_INSTRUCTION).format(language=language))
    if level:
        parts.append(
            resolve_fragment(KEY_LEVEL_INSTRUCTION).format(language=language, level=level)
        )
    parts.append(resolve_fragment(KEY_OUTPUT_FORMAT).format(language=language))
    return "\n\n".join(parts)
