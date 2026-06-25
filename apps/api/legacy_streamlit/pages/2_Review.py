"""Review page: daily flashcard batch scheduled by FSRS."""
import json

import streamlit as st
from fsrs import Rating

from lengua_core import gemini

from legacy_streamlit import store
from legacy_streamlit.ui import render_sidebar

# Style the per-word buttons so they read as inline sentence text, with a
# hover lift + highlight. Scoped to the keyed container Streamlit emits as
# `.st-key-lwrow*` so it doesn't bleed into the rating buttons.
_WORD_CSS = """
<style>
[class*="st-key-lwrow"] { row-gap: 0.1rem; column-gap: 0.05rem; }
[class*="st-key-lwrow"] button {
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    color: inherit;
    min-height: 0 !important;
    padding: 0.05em 0.18em !important;
    border-radius: 0.3em !important;
    transition: background-color .15s ease, transform .15s ease, box-shadow .15s ease;
}
/* Match the front (#### = H4: 1.5rem / 600). Streamlit sets the label size on
   the inner markdown <p>, so it must be targeted too or it stays button-tiny. */
[class*="st-key-lwrow"] button,
[class*="st-key-lwrow"] button [data-testid="stMarkdownContainer"],
[class*="st-key-lwrow"] button p {
    font-size: 1.5rem !important;
    font-weight: 600 !important;
    line-height: 1.4 !important;
}
[class*="st-key-lwrow"] button:hover {
    background-color: rgba(128, 128, 128, 0.18) !important;
    transform: translateY(-2px);
    box-shadow: 0 3px 8px rgba(0, 0, 0, 0.18) !important;
}
[class*="st-key-lwrow"] button[data-testid="stBaseButton-primary"] {
    background-color: rgba(128, 128, 128, 0.30) !important;
    color: inherit !important;
}
[class*="st-key-lwrow-rtl"] { direction: rtl; }
</style>
"""

# Color the four rating buttons by difficulty: Again=red, Hard=orange, Good=blue,
# Easy=green. Targets the per-key class Streamlit emits (`.st-key-rate-<name>`).
_RATING_CSS = """
<style>
[class*="st-key-rate-again"] button { background-color: #e53935 !important; }
[class*="st-key-rate-hard"]  button { background-color: #fb8c00 !important; }
[class*="st-key-rate-good"]  button { background-color: #1e88e5 !important; }
[class*="st-key-rate-easy"]  button { background-color: #43a047 !important; }
[class*="st-key-rate-"] button {
    color: #fff !important;
    border: none !important;
}
[class*="st-key-rate-"] button:hover { filter: brightness(1.1); }
</style>
"""


def _is_rtl(text: str) -> bool:
    """True if the text contains Arabic or Hebrew letters (right-to-left script)."""
    return any("֐" <= ch <= "ۿ" for ch in text)


st.set_page_config(page_title="Review · Lengua", page_icon="🃏", layout="centered")

active = render_sidebar()
st.title("🃏 Review")

if active is None:
    st.warning("Add and select a language in the sidebar first.")
    st.stop()

lang_id = active["id"]

# Load today's batch once per language, then walk through it in session state.
batch_key = f"review_batch_{lang_id}"
if batch_key not in st.session_state:
    st.session_state[batch_key] = store.due_cards(lang_id)
    st.session_state[f"review_idx_{lang_id}"] = 0
    st.session_state[f"review_show_{lang_id}"] = False

batch = st.session_state[batch_key]
idx = st.session_state[f"review_idx_{lang_id}"]

total_saved = store.count_saved(lang_id)
new_count = sum(1 for c in batch if store.is_new_card(c))
due_count = len(batch) - new_count
level_band = store.get_band(lang_id)
st.caption(
    f"Level **{level_band}** · {new_count} new · {due_count} due · "
    f"{total_saved} cards in your {active['name']} deck"
)

if st.button("🔄 Refresh batch"):
    for k in list(st.session_state):
        if k.endswith(f"_{lang_id}"):
            del st.session_state[k]
    st.rerun()

if total_saved == 0:
    st.info("No flashcards yet. Generate some sentences and save them first.")
    st.stop()

if idx >= len(batch):
    st.success("🎉 Done for today! No more cards due.")
    st.stop()

card = batch[idx]
show = st.session_state[f"review_show_{lang_id}"]

# Prompt depends on the card direction (legacy cards without one are recognition).
if card.get("direction") == store.PRODUCTION:
    prompt_label = f"✍️ Build the sentence in {active['name']}"
    reveal_label = "Show answer"
else:
    prompt_label = "📖 Read & understand"
    reveal_label = "Show translation"

st.divider()
st.caption(prompt_label)
st.markdown(f"#### {card['front']}")

if not show:
    if st.button(reveal_label, type="primary"):
        st.session_state[f"review_show_{lang_id}"] = True
        st.rerun()
else:
    if card.get("direction") == store.PRODUCTION:
        card_id = card["id"]
        sel_key = f"word_sel_{card_id}"
        selected_word = st.session_state.get(sel_key)

        st.markdown(_WORD_CSS, unsafe_allow_html=True)
        row_key = f"lwrow-rtl-{card_id}" if _is_rtl(card["back"]) else f"lwrow-{card_id}"
        with st.container(horizontal=True, key=row_key):
            for i, token in enumerate(card["back"].split()):
                bare = store.bare_word(token)
                if not bare:
                    st.markdown(token)
                    continue
                if st.button(
                    token,
                    key=f"w_{card_id}_{i}",
                    type="primary" if bare == selected_word else "secondary",
                ):
                    st.session_state[sel_key] = bare
                    st.rerun()
        st.caption("👆 Tap any word above for a quick explanation.")

        if selected_word:
            # Seed the session cache once from the card's pre-generated notes so
            # stored words render instantly (no spinner, no API call).
            cache = st.session_state.get(f"word_cache_{card_id}")
            if cache is None:
                stored = card.get("word_explanations")
                cache = json.loads(stored) if stored else {}
                st.session_state[f"word_cache_{card_id}"] = cache
            if selected_word not in cache:
                with st.spinner(f'Explaining "{selected_word}"…'):
                    try:
                        note = gemini.explain_word(
                            selected_word,
                            card["back"],
                            card["front"],
                            active["name"],
                        )
                        cache[selected_word] = note
                        # Persist so it's instant next time (covers imported cards).
                        store.save_word_explanation(card_id, selected_word, note)
                    except Exception as exc:  # surface API issues instead of crashing
                        cache[selected_word] = f"⚠️ Couldn't fetch an explanation: {exc}"
            exp_col, close_col = st.columns([0.92, 0.08], vertical_alignment="top")
            exp_col.info(f"**{selected_word}** — {cache[selected_word]}")
            if close_col.button("✕", key=f"close_{card_id}", help="Close"):
                st.session_state[sel_key] = None
                st.rerun()
    else:
        st.markdown(f"#### {card['back']}")

    st.divider()
    st.markdown(_RATING_CSS, unsafe_allow_html=True)
    cols = st.columns(4)
    ratings = [
        ("Again", Rating.Again),
        ("Hard", Rating.Hard),
        ("Good", Rating.Good),
        ("Easy", Rating.Easy),
    ]
    for col, (label, rating) in zip(cols, ratings):
        if col.button(
            label, key=f"rate-{label.lower()}-{lang_id}", use_container_width=True
        ):
            store.grade(card["id"], rating)
            st.session_state[f"review_idx_{lang_id}"] = idx + 1
            st.session_state[f"review_show_{lang_id}"] = False
            st.rerun()

st.progress((idx) / len(batch) if batch else 0.0, text=f"{idx}/{len(batch)} reviewed")
