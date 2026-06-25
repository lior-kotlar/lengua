"""Shared Streamlit UI pieces — notably the always-present language sidebar."""
import streamlit as st

from . import config, languages, proficiency
from .db import init_db


def ensure_ready() -> None:
    """Run once-per-session setup (idempotent)."""
    if not st.session_state.get("_db_ready"):
        init_db()
        st.session_state["_db_ready"] = True


def _render_level(language_id: int) -> None:
    """Show the learner's CEFR level for a language, with progress and a manual override."""
    score = proficiency.get_score(language_id)
    band = proficiency.band_for_score(score)

    st.markdown(f"**Level: {band}**")
    if band != config.CEFR_BANDS[-1]:
        nxt = config.CEFR_BANDS[config.CEFR_BANDS.index(band) + 1]
        st.progress(proficiency.band_progress(score), text=f"Progress to {nxt}")

    with st.expander("Adjust level"):
        choice = st.selectbox(
            "Set level manually",
            options=config.CEFR_BANDS,
            index=config.CEFR_BANDS.index(band),
            help="Auto-adjusts as you review; override it here if it's off.",
            key=f"level_select_{language_id}",
        )
        if choice != band:
            proficiency.set_band(language_id, choice)
            st.rerun()


def render_sidebar():
    """Render the global language selector + management. Returns the active
    language as a plain dict, or None if none exists yet."""
    ensure_ready()
    # Plain dicts (not sqlite3.Row) so Streamlit can pickle widget state.
    langs = [dict(r) for r in languages.list_languages()]
    names = {l["id"]: l["name"] for l in langs}
    ids = list(names)

    with st.sidebar:
        st.header("🌍 Language")

        active = None
        if langs:
            active_id = languages.get_active_language_id()
            index = ids.index(active_id) if active_id in ids else 0
            # selectbox options are picklable ints; format_func maps id -> name.
            choice_id = st.selectbox(
                "Currently learning",
                options=ids,
                index=index,
                format_func=lambda i: names[i],
                key="active_language_select",
            )
            if choice_id != active_id:
                languages.set_active_language_id(choice_id)
            active = next(l for l in langs if l["id"] == choice_id)

            # Per-language vocalization toggle (keyed per id to avoid stale state).
            vowel = st.checkbox(
                "Vowel marks (harakat / nikkud)",
                value=bool(active["vowelized"]),
                help="Ask the model to fully vocalize sentences in this language.",
                key=f"vowelized_{active['id']}",
            )
            if vowel != bool(active["vowelized"]):
                languages.set_vowelized(active["id"], vowel)
                active["vowelized"] = int(vowel)

            _render_level(active["id"])
        else:
            st.info("Add a language to get started.")

        with st.expander("Manage languages"):
            with st.form("add_language", clear_on_submit=True):
                name = st.text_input("Name", placeholder="Spanish")
                code = st.text_input("Code (optional)", placeholder="es")
                new_vowelized = st.checkbox("Include vowel marks (harakat / nikkud)")
                if st.form_submit_button("Add") and name.strip():
                    languages.add_language(name, code, vowelized=new_vowelized)
                    st.rerun()

            if langs:
                delete_id = st.selectbox(
                    "Remove a language",
                    options=ids,
                    format_func=lambda i: names[i],
                    key="delete_language_select",
                )
                if st.button("Delete", type="secondary"):
                    languages.delete_language(delete_id)
                    st.rerun()

    return active
