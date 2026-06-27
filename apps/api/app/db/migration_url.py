"""Resolve the Alembic migration target database URL (tasks 1.4.1 + 6.6.3).

A pure, importable helper so the precedence is unit-testable **without** importing
``migrations/env.py`` (whose module body runs the migrations on import). ``env.py`` delegates here.

Precedence (highest wins):

1. ``alembic -x db_url=postgresql://…`` — an explicit per-invocation override (the schema
   round-trip tests + one-off ops point this at a throwaway/hosted DB).
2. ``alembic -x env=staging|prod|local`` — selects a named environment's connection-string env
   var: ``staging`` → ``STAGING_DATABASE_URL``, ``prod`` (alias ``production``) →
   ``PROD_DATABASE_URL``, ``local`` → ``DATABASE_URL``. This is what the CD migrate jobs use so a
   "migrate staging" / "migrate prod" job reads its own per-environment secret (6.6.3 / 6.7.3).
3. ``DATABASE_URL`` (the resolved default, read via :class:`app.settings.Settings`, which also
   sources ``.env``) — the local/default path.
"""

from __future__ import annotations

from collections.abc import Mapping

# `-x env=<name>` → the environment variable holding that environment's connection string.
# `local` maps to the app's canonical DATABASE_URL; `staging` / `prod` map to the CD-only
# STAGING_DATABASE_URL / PROD_DATABASE_URL the deploy pipeline sets from the per-env secrets
# (SUPABASE_STAGING_DATABASE_URL / SUPABASE_PROD_DATABASE_URL).
_ENV_DB_VAR: dict[str, str] = {
    "local": "DATABASE_URL",
    "staging": "STAGING_DATABASE_URL",
    "prod": "PROD_DATABASE_URL",
    "production": "PROD_DATABASE_URL",
}


def resolve_migration_url(
    x_args: Mapping[str, str],
    environ: Mapping[str, str],
    default_url: str,
) -> str:
    """Resolve the migration target DB URL from ``-x`` args, the environment, and the default.

    ``default_url`` is the app's resolved ``DATABASE_URL`` (``get_settings().database_url``). The
    returned value is the *raw* connection string — the caller normalizes the driver scheme.
    Raises :class:`RuntimeError` for an unknown ``-x env=`` or when the selected source is empty.
    """
    # 1. An explicit -x db_url= override wins over everything.
    db_url = x_args.get("db_url")
    if db_url:
        return db_url

    # 2. -x env=staging|prod|local selects a named environment's connection-string variable.
    env = x_args.get("env")
    if env:
        key = env.strip().lower()
        var = _ENV_DB_VAR.get(key)
        if var is None:
            allowed = ", ".join(sorted(set(_ENV_DB_VAR) - {"production"}))
            raise RuntimeError(f"Unknown `-x env={env}`: expected one of {allowed}.")
        # `local` resolves through the app default (DATABASE_URL via Settings/.env); the hosted
        # environments read their dedicated var straight from the process environment.
        url = default_url if var == "DATABASE_URL" else environ.get(var, "")
        if not url:
            raise RuntimeError(f"`-x env={key}` requires {var} to be set (it is empty/missing).")
        return url

    # 3. Default: the app's DATABASE_URL.
    if not default_url:
        raise RuntimeError(
            "No database URL: set DATABASE_URL, or pass "
            "`alembic -x db_url=postgresql://…` or `alembic -x env=staging|prod|local`."
        )
    return default_url
