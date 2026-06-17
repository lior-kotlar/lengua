"""Shared Streamlit UI pieces — notably the always-present language sidebar."""
import streamlit as st

from . import languages
from .db import init_db


def ensure_ready() -> None:
    """Run once-per-session setup (idempotent)."""
    if not st.session_state.get("_db_ready"):
        init_db()
        st.session_state["_db_ready"] = True


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
        else:
            st.info("Add a language to get started.")

        with st.expander("Manage languages"):
            with st.form("add_language", clear_on_submit=True):
                name = st.text_input("Name", placeholder="Spanish")
                code = st.text_input("Code (optional)", placeholder="es")
                if st.form_submit_button("Add") and name.strip():
                    languages.add_language(name, code)
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
