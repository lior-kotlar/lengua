"""Discover page: auto-select new vocabulary and generate sentences without manual input."""
import streamlit as st

from lengua import flashcards, proficiency, settings as app_settings
from lengua.gemini import generate_cards, suggest_new_words
from lengua.models import GeneratedCard
from lengua.ui import render_sidebar

st.set_page_config(page_title="Discover · Lengua", page_icon="🔍", layout="centered")

active = render_sidebar()
st.title("🔍 Discover new words")

if active is None:
    st.warning("Add and select a language in the sidebar first.")
    st.stop()

gen_score = proficiency.get_score(active["id"])
gen_band = proficiency.band_for_score(gen_score)
st.caption(
    f"Active language: **{active['name']}** · level **{gen_band}**. "
    "Lengua will pick vocabulary you haven't seen yet and write sentences around it."
)

count = st.slider("New words to introduce", min_value=3, max_value=10, value=app_settings.discover_word_count())
topic = st.text_input("Topic or theme (optional)", placeholder="e.g. food, travel, work…")
topic = topic.strip() or None

# ── Phase 1: word suggestion ──────────────────────────────────────────────────

if st.button("Discover", type="primary"):
    known = flashcards.get_known_words(active["id"])
    with st.spinner("Choosing new vocabulary…"):
        try:
            words = suggest_new_words(
                active["name"], gen_band, known, count=count, topic=topic
            )
        except Exception as e:
            st.error(f"Word selection failed: {e}")
            words = []
    if words:
        st.session_state["discover_words"] = words
        st.session_state["discover_lang_id"] = active["id"]
        st.session_state.pop("discover_cards", None)

# ── Show suggested words + approve/retry ─────────────────────────────────────

suggested = st.session_state.get("discover_words")
if suggested and st.session_state.get("discover_lang_id") == active["id"]:
    # Only show the word picker when we don't yet have generated sentences.
    if not st.session_state.get("discover_cards"):
        st.divider()
        st.subheader("Suggested words")
        st.write("  ·  ".join(f"**{w}**" for w in suggested))

        col_gen, col_retry = st.columns([1, 1], gap="small")

        with col_gen:
            if st.button("Generate sentences →", type="primary", use_container_width=True):
                with st.spinner(f"Writing sentences in {active['name']}…"):
                    try:
                        cards = generate_cards(
                            suggested,
                            active["name"],
                            vowelized=bool(active["vowelized"]),
                            level_band=gen_band,
                        )
                    except Exception as e:
                        st.error(f"Generation failed: {e}")
                        cards = []
                if cards:
                    st.session_state["discover_cards"] = [c.model_dump() for c in cards]
                    st.rerun()

        with col_retry:
            if st.button("Try different words", use_container_width=True):
                known = flashcards.get_known_words(active["id"])
                with st.spinner("Choosing different words…"):
                    try:
                        words = suggest_new_words(
                            active["name"], gen_band, known, count=count, topic=topic
                        )
                    except Exception as e:
                        st.error(f"Word selection failed: {e}")
                        words = []
                if words:
                    st.session_state["discover_words"] = words
                    st.rerun()

# ── Phase 2: sentence preview + save ─────────────────────────────────────────

cards = st.session_state.get("discover_cards")
if cards and st.session_state.get("discover_lang_id") == active["id"]:
    st.divider()
    st.subheader(f"{len(cards)} sentence(s)")
    for c in cards:
        st.markdown(f"**{c['sentence']}**")
        with st.expander("Translation"):
            st.write(c["translation"])
            if c["used_words"]:
                st.caption("Uses: " + ", ".join(c["used_words"]))

    col_save, col_back = st.columns([1, 1], gap="small")
    with col_save:
        if st.button("💾 Save all as flashcards", type="primary", use_container_width=True):
            n = flashcards.save_cards(
                active["id"],
                [GeneratedCard(**c) for c in cards],
                gen_level=gen_score,
            )
            st.success(
                f"Saved {n} sentence(s) as {n * 2} flashcards (reading + building) "
                f"to your **{active['name']}** deck."
            )
            st.session_state.pop("discover_words", None)
            st.session_state.pop("discover_cards", None)
    with col_back:
        if st.button("← Pick different words", use_container_width=True):
            st.session_state.pop("discover_cards", None)
            st.rerun()
