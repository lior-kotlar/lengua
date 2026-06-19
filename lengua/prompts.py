"""The constant prompt pieces attached to every generation request.

To add, remove, or change a rule, edit the ``RULES`` list below — each ``Rule`` is
one numbered section and each string in ``points`` is one bullet. Nothing else needs
to change; the prompt text is assembled from this list automatically.

The output shape (sentence / translation / used_words) is enforced programmatically
by ``response_schema`` in lengua/gemini.py and described in ``OUTPUT_FORMAT`` below,
so the rules here only govern *how* sentences are written, not their formatting.
"""
from dataclasses import dataclass, field


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


def _render_rules() -> str:
    blocks = []
    for i, rule in enumerate(RULES, 1):
        bullets = "\n".join(f"  - {p}" for p in rule.points)
        blocks.append(f"#### {i}. {rule.title}\n{bullets}")
    return "\n\n".join(blocks)


# Full rules block (assembled from RULES). Exposed for inspection/debugging.
RULES_PROMPT = INTRO + "\n\n" + _render_rules()


def system_instruction(language: str, vowelized: bool = False) -> str:
    """Full system instruction for a generation request in `language`.

    When `vowelized`, ask the model to fully vocalize the target-language sentence
    (harakat / nikkud), for scripts with optional diacritics.
    """
    parts = [RULES_PROMPT, GENERATION_INSTRUCTION.format(language=language)]
    if vowelized:
        parts.append(VOCALIZATION_INSTRUCTION.format(language=language))
    parts.append(OUTPUT_FORMAT.format(language=language))
    return "\n\n".join(parts)
