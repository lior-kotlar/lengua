"""Generate page: vocabulary words in -> example sentences out."""
import re

import streamlit as st

from lengua import flashcards, proficiency
from lengua.gemini import generate_cards
from lengua.ui import render_sidebar

st.set_page_config(page_title="Generate · Lengua", page_icon="✍️", layout="centered")

active = render_sidebar()
st.title("✍️ Generate sentences")

if active is None:
    st.warning("Add and select a language in the sidebar first.")
    st.stop()

gen_score = proficiency.get_score(active["id"])
gen_band = proficiency.band_for_score(gen_score)
st.caption(f"Active language: **{active['name']}** · level **{gen_band}**. Just enter "
           "words — the rules prompt, language, and your level are added automatically.")

raw = st.text_area(
    "Vocabulary words",
    height=160,
    placeholder="One per line, or comma-separated:\ncasa\nperro\ncomer",
)

if st.button("Generate", type="primary"):
    words = [w.strip() for w in re.split(r"[\n,]+", raw) if w.strip()]
    if not words:
        st.warning("Enter at least one word.")
    else:
        with st.spinner(f"Asking Gemini for sentences in {active['name']}…"):
            try:
                cards = generate_cards(
                    words,
                    active["name"],
                    vowelized=bool(active["vowelized"]),
                    level_band=gen_band,
                )
            except Exception as e:  # surface API/config errors to the user
                st.error(f"Generation failed: {e}")
                cards = []
        st.session_state["generated"] = [c.model_dump() for c in cards]
        st.session_state["generated_lang_id"] = active["id"]

cards = st.session_state.get("generated")
if cards and st.session_state.get("generated_lang_id") == active["id"]:
    st.divider()
    st.subheader(f"{len(cards)} sentence(s)")
    for c in cards:
        st.markdown(f"**{c['sentence']}**")
        with st.expander("Translation"):
            st.write(c["translation"])
            if c["used_words"]:
                st.caption("Uses: " + ", ".join(c["used_words"]))

    if st.button("💾 Save all as flashcards"):
        from lengua.models import GeneratedCard

        n = flashcards.save_cards(
            active["id"], [GeneratedCard(**c) for c in cards], gen_level=gen_score
        )
        st.success(
            f"Saved {n} sentence(s) as {n * 2} flashcards (reading + building) "
            f"to your **{active['name']}** deck."
        )
        st.session_state.pop("generated", None)
