"""Boot-time deployment config guard (see :func:`app.main._check_deployment_secrets`).

``AccountDeletionService`` fails closed only when a user first calls ``DELETE /account``, so a
misconfigured staging/prod (empty ``SUPABASE_SERVICE_ROLE_KEY`` / ``SUPABASE_URL``) otherwise looks
healthy until then. The guard logs a CRITICAL at boot instead. These tests prove it fires for a real
deployment env with a missing secret and stays SILENT for the local/ci/test/e2e envs (which run
without the key by design). No DB / HTTP.
"""

from __future__ import annotations

import logging

import pytest
from pydantic import SecretStr

from app.main import _SECRET_REQUIRED_ENVS, _check_deployment_secrets, create_app
from app.settings import Settings, get_settings


def _settings(*, env: str, service_key: str = "", url: str = "") -> Settings:
    """A ``Settings`` with the fields the guard reads set explicitly (init kwargs beat env/.env)."""
    return Settings(env=env, supabase_service_role_key=SecretStr(service_key), supabase_url=url)


def _criticals(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.levelno == logging.CRITICAL]


@pytest.mark.parametrize("env", ["prod", "staging"])
def test_warns_when_service_role_key_missing_in_deployment(
    env: str, caplog: pytest.LogCaptureFixture
) -> None:
    """A deployment env with an empty service-role key logs a CRITICAL naming the missing var."""
    with caplog.at_level(logging.WARNING):
        _check_deployment_secrets(_settings(env=env, service_key="", url="https://x.supabase.co"))
    records = _criticals(caplog)
    assert records, "expected a CRITICAL when the service-role key is missing in a deployment"
    assert "SUPABASE_SERVICE_ROLE_KEY" in records[0].getMessage()


def test_warns_when_supabase_url_missing_in_deployment(caplog: pytest.LogCaptureFixture) -> None:
    """A deployment env with an empty Supabase URL logs a CRITICAL naming that var too."""
    with caplog.at_level(logging.WARNING):
        _check_deployment_secrets(_settings(env="prod", service_key="secret", url=""))
    message = " ".join(r.getMessage() for r in _criticals(caplog))
    assert "SUPABASE_URL" in message


@pytest.mark.parametrize("env", ["local", "ci", "test", "e2e"])
def test_no_warning_for_non_deployment_env(env: str, caplog: pytest.LogCaptureFixture) -> None:
    """The guard is a strict no-op for local/ci/test/e2e — even with the key fully unset."""
    with caplog.at_level(logging.DEBUG):
        _check_deployment_secrets(_settings(env=env, service_key="", url=""))
    assert not _criticals(caplog)


def test_no_warning_when_deployment_fully_configured(caplog: pytest.LogCaptureFixture) -> None:
    """A deployment env with both values present logs nothing."""
    with caplog.at_level(logging.DEBUG):
        _check_deployment_secrets(
            _settings(env="prod", service_key="secret", url="https://x.supabase.co")
        )
    assert not _criticals(caplog)


def test_create_app_boots_in_local_env_without_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Building the app in the default (local) env must not raise nor emit the deployment CRITICAL.

    ``create_app`` runs the guard against the process ``get_settings()`` (env defaults to ``local``
    in dev/CI), so this exercises the real wiring, not just the helper.
    """
    with caplog.at_level(logging.WARNING):
        app = create_app()
    assert app.title == "Lengua API"
    # In dev/CI ENV is unset → env="local", so the guard is silent. Guard the assertion so a stray
    # deployment ENV in the shell (with a real key set) doesn't make this a false failure.
    if get_settings().env.strip().lower() not in _SECRET_REQUIRED_ENVS:
        assert not _criticals(caplog)
