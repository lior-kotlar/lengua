"""Lengua — language learning app. Streamlit entry point / home page."""
import streamlit as st

from lengua_core.ui import render_sidebar

st.set_page_config(page_title="Lengua", page_icon="🗣️", layout="centered")

active = render_sidebar()

st.title("🗣️ Lengua")
st.markdown(
    """
Welcome! Use the pages in the sidebar:

- **Generate** — paste vocabulary words and get example sentences in your active
  language. The rules prompt and target language are attached automatically.
- **Review** — practice your saved sentences as flashcards, scheduled with FSRS.
"""
)

if active is None:
    st.warning("Add a language in the sidebar to begin.")
else:
    st.success(f"Active language: **{active['name']}**")
