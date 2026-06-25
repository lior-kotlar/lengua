"""Legacy single-user Streamlit app (kept runnable during productionization).

This package holds the original Streamlit UI and its **SQLite** persistence. The pure domain
logic it builds on lives in :mod:`lengua_core`; everything database-coupled (the connection,
schema, language/settings CRUD, and the FSRS/proficiency/card orchestration that reads and
writes SQLite) lives here in :mod:`legacy_streamlit.store` so ``lengua_core`` stays pure.
"""
