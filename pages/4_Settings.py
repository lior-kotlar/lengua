"""Settings page: configure app-wide behaviour stored in the local database."""
import streamlit as st

from lengua import settings as app_settings
from lengua.ui import render_sidebar

st.set_page_config(page_title="Settings · Lengua", page_icon="⚙️", layout="centered")

render_sidebar()
st.title("⚙️ Settings")
st.caption("Changes take effect immediately and persist across restarts.")

# ── Review ────────────────────────────────────────────────────────────────────
st.header("Review")

daily_new = st.number_input(
    "Daily new cards",
    min_value=1,
    max_value=100,
    value=app_settings.daily_new_limit(),
    help="Maximum brand-new (never-reviewed) cards shown in a single review session.",
)

daily_total = st.number_input(
    "Daily total cards",
    min_value=1,
    max_value=500,
    value=app_settings.daily_total_limit(),
    help="Hard cap on the total number of cards in a review session (new + due).",
)

# ── Discover ──────────────────────────────────────────────────────────────────
st.header("Discover")

discover_count = st.slider(
    "Default word count",
    min_value=3,
    max_value=10,
    value=app_settings.discover_word_count(),
    help="How many new vocabulary words the Discover page suggests by default.",
)

# ── Generation ────────────────────────────────────────────────────────────────
st.header("Generation")

_MODELS = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]
current_model = app_settings.gemini_model()
if current_model not in _MODELS:
    _MODELS = [current_model] + _MODELS

model = st.selectbox(
    "Gemini model",
    options=_MODELS,
    index=_MODELS.index(current_model),
    help="Model used for sentence generation and word suggestions. gemini-2.5-flash is fast and cheap; gemini-2.5-pro gives higher quality.",
)

# ── Save ─────────────────────────────────────────────────────────────────────
st.divider()
if st.button("Save settings", type="primary"):
    app_settings.set_daily_new_limit(int(daily_new))
    app_settings.set_daily_total_limit(int(daily_total))
    app_settings.set_discover_word_count(int(discover_count))
    app_settings.set_gemini_model(model)
    st.success("Settings saved.")
