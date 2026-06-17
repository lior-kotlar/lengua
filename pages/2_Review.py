"""Review page: daily flashcard batch scheduled by FSRS."""
import streamlit as st
from fsrs import Rating

from lengua import flashcards, scheduler
from lengua.ui import render_sidebar

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
    st.session_state[batch_key] = scheduler.due_cards(lang_id)
    st.session_state[f"review_idx_{lang_id}"] = 0
    st.session_state[f"review_show_{lang_id}"] = False

batch = st.session_state[batch_key]
idx = st.session_state[f"review_idx_{lang_id}"]

total_saved = flashcards.count_saved(lang_id)
st.caption(f"{len(batch)} due today · {total_saved} cards in your {active['name']} deck")

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

st.divider()
st.markdown(f"#### {card['front']}")

if not show:
    if st.button("Show translation", type="primary"):
        st.session_state[f"review_show_{lang_id}"] = True
        st.rerun()
else:
    st.markdown(f"**{card['back']}**")
    st.divider()
    cols = st.columns(4)
    ratings = [
        ("Again", Rating.Again),
        ("Hard", Rating.Hard),
        ("Good", Rating.Good),
        ("Easy", Rating.Easy),
    ]
    for col, (label, rating) in zip(cols, ratings):
        if col.button(label, use_container_width=True):
            scheduler.grade(card["id"], rating)
            st.session_state[f"review_idx_{lang_id}"] = idx + 1
            st.session_state[f"review_show_{lang_id}"] = False
            st.rerun()

st.progress((idx) / len(batch) if batch else 0.0, text=f"{idx}/{len(batch)} reviewed")
