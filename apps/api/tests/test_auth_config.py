"""Supabase Auth configuration — email/password + confirmation, password policy, redirect
allow-list, and branded email templates (tasks 2.1.1, 2.1.4, 2.2.3; scaffold for 2.1.2/2.1.3).

The canonical, version-controlled source of truth is the repo-root ``supabase/config.toml`` (the
file the Supabase CLI actually reads) plus the templates under ``supabase/templates/``. Two layers:

* **Unit (always run)** — parse ``config.toml`` / the template files and assert the configured
  contract: email confirmation required, the password policy, the redirect/site-URL allow-list
  (listed origins present, no catch-all, an un-listed origin absent), the three branded templates
  wired with a working ``{{ .ConfirmationURL }}``, and that the OAuth providers reference *env*
  secrets only (nothing committed).
* **Integration (``@pytest.mark.integration``, auto-skipped when the stack is unreachable)** — drive
  the *live* local Supabase Auth stack: a public signup stays unconfirmed (``email_confirmed_at``
  null, ``confirmation_sent_at`` set), a weak password is rejected, and the delivered confirmation
  email (read from Inbucket) carries the Lengua branding and a verify link whose ``redirect_to`` is
  honored for a listed origin and refused for an un-listed one.
"""

from __future__ import annotations

import html
import os
import re
import time
import tomllib
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

import httpx
import psycopg
import pytest

from scripts.seed_e2e import _find_user_id_by_email, _supabase_url
from tests.conftest import database_url
from tests.supabase_auth import delete_user, signup

# apps/api/tests/<this file> → parents[3] is the repo root (where the Supabase CLI runs).
_REPO_ROOT = Path(__file__).resolve().parents[3]
_CONFIG_TOML = _REPO_ROOT / "supabase" / "config.toml"
_TEMPLATES_DIR = _REPO_ROOT / "supabase" / "templates"

# A site URL / web origin Lengua's local dev serves on (the Vite dev server, apps/web).
_SITE_URL = "http://localhost:5173"
# A password satisfying the configured policy (lower + upper + digits, length >= 8). Not a secret —
# a fixed local test credential; the inline token tells gitleaks to ignore this specific line.
_COMPLIANT_PASSWORD = "Test-pass-123"  # noqa: S105  # gitleaks:allow
# The three transactional templates Lengua brands (task 2.2.3).
_BRANDED_TEMPLATES = ("confirmation", "recovery", "magic_link")
_APP_NAME = "Lengua"


# ── config.toml loading ──────────────────────────────────────────────────────────────────────


def _config() -> dict[str, Any]:
    data = tomllib.loads(_CONFIG_TOML.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _auth() -> dict[str, Any]:
    auth = _config()["auth"]
    assert isinstance(auth, dict)
    return auth


# ── 2.1.1 — email confirmation required + password policy ─────────────────────────────────────


def test_canonical_config_and_templates_exist() -> None:
    """The CLI-read config + the branded templates live where the config references them."""
    assert _CONFIG_TOML.is_file(), f"expected canonical Supabase config at {_CONFIG_TOML}"
    for kind in _BRANDED_TEMPLATES:
        assert (_TEMPLATES_DIR / f"{kind}.html").is_file(), f"missing template {kind}.html"


def test_email_confirmation_required() -> None:
    """Signup requires confirming the email address before the account can sign in."""
    assert _auth()["email"]["enable_confirmations"] is True


def test_password_policy_enforced() -> None:
    """A sensible password policy: minimum length >= 8 and a non-empty strength requirement."""
    auth = _auth()
    assert auth["minimum_password_length"] >= 8
    assert auth["password_requirements"] in {
        "letters_digits",
        "lower_upper_letters_digits",
        "lower_upper_letters_digits_symbols",
    }


# ── 2.1.4 — site URL + redirect allow-list ────────────────────────────────────────────────────


def _redirect_urls() -> list[str]:
    urls = _auth()["additional_redirect_urls"]
    assert isinstance(urls, list)
    return [str(u) for u in urls]


def test_site_url_is_local_web_origin() -> None:
    """``site_url`` (used for email links + the default redirect) is the local web origin."""
    assert _auth()["site_url"] == _SITE_URL


def test_redirect_allowlist_includes_all_environments() -> None:
    """The allow-list covers local + staging + prod web origins and the native app scheme."""
    urls = _redirect_urls()

    def has(substr: str) -> bool:
        return any(substr in u for u in urls)

    # Local web: Vite dev (5173), preview/E2E (4173), alt (3000).
    assert _SITE_URL in urls
    assert has(":5173") and has(":4173") and has(":3000")
    # Staging + prod web (Vercel / custom domain placeholders — owner confirms finals).
    assert has("vercel.app")
    assert has("lengua.app")
    # Capacitor native app: local WebView origin + a deep-link scheme.
    assert "capacitor://localhost" in urls
    assert has("app.lengua://")


def test_redirect_allowlist_rejects_unlisted_and_has_no_catch_all() -> None:
    """An un-listed origin is absent and there is no wildcard that would allow everything."""
    urls = _redirect_urls()
    # A representative un-listed origin must not be permitted.
    assert not any("evil.example.com" in u for u in urls)
    # No catch-all that would defeat the allow-list (e.g. ``*`` / ``http://*`` / ``**``).
    catch_all = {"*", "**", "*://*", "http://*", "https://*", "http://**", "https://**"}
    assert not (set(urls) & catch_all)
    # Every entry is a concrete scheme-qualified origin (not an empty / bare-host string).
    assert all("://" in u for u in urls)


# ── 2.2.3 — branded email templates wired into config.toml ────────────────────────────────────


def test_email_templates_referenced_in_config() -> None:
    """Each branded template is wired with a branded subject and a content_path to the real file."""
    templates = _auth()["email"]["template"]
    for kind in _BRANDED_TEMPLATES:
        block = templates[kind]
        assert _APP_NAME in block["subject"], f"{kind} subject should be branded"
        assert block["content_path"] == f"./supabase/templates/{kind}.html"
        assert (_TEMPLATES_DIR / f"{kind}.html").is_file()


def test_templates_carry_branding_and_confirmation_url() -> None:
    """Every template renders the app name and the ``{{ .ConfirmationURL }}`` action link."""
    for kind in _BRANDED_TEMPLATES:
        body = (_TEMPLATES_DIR / f"{kind}.html").read_text(encoding="utf-8")
        assert _APP_NAME in body, f"{kind}.html must carry the app branding"
        assert "{{ .ConfirmationURL }}" in body, f"{kind}.html must link {{{{ .ConfirmationURL }}}}"


# ── 2.1.2 / 2.1.3 — OAuth provider scaffold (no committed secrets) ────────────────────────────


def test_oauth_providers_use_env_substituted_secrets() -> None:
    """Google + Apple read credentials via env() substitution — no secret is committed."""
    external = _auth()["external"]
    for provider in ("google", "apple"):
        block = external[provider]
        assert block["client_id"].startswith("env("), f"{provider} client_id must be env-wired"
        assert block["secret"].startswith("env("), f"{provider} secret must be env-wired"
    # Apple stays disabled (owner action — paid account / Phase 7); Google is scaffolded armed.
    assert external["apple"]["enabled"] is False
    assert isinstance(external["google"]["enabled"], bool)


# ── Integration: the live Supabase Auth stack ─────────────────────────────────────────────────


def _unique_email(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}@lengua.test"


@pytest.mark.integration
def test_public_signup_requires_email_confirmation() -> None:
    """A public signup stays unconfirmed: ``email_confirmed_at`` null, confirmation email sent."""
    email = _unique_email("confirm")
    with httpx.Client(timeout=30.0) as client:
        resp = signup(client, email, _COMPLIANT_PASSWORD, redirect_to=f"{_SITE_URL}/auth/callback")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        user_id = body["id"]
        try:
            # No session is handed back — login is blocked until the email is confirmed.
            assert "access_token" not in body
            with psycopg.connect(database_url()) as conn:
                row = conn.execute(
                    "SELECT email_confirmed_at, confirmation_sent_at FROM auth.users WHERE id = %s",
                    (user_id,),
                ).fetchone()
            assert row is not None
            email_confirmed_at, confirmation_sent_at = row
            assert email_confirmed_at is None, "a fresh signup must be unconfirmed"
            assert confirmation_sent_at is not None, "a confirmation email must have been sent"
        finally:
            delete_user(client, user_id)


@pytest.mark.integration
def test_weak_password_is_rejected() -> None:
    """The password policy rejects a weak password on public signup (and creates no user)."""
    email = _unique_email("weak")
    with httpx.Client(timeout=30.0) as client:
        resp = signup(client, email, "weak")  # too short, no upper-case, no digit
        assert resp.status_code in (400, 422), resp.text
        assert "password" in resp.text.lower()
        assert _find_user_id_by_email(client, email) is None, "no user should exist after rejection"


# ── Mail-catcher helpers (Mailpit on the current CLI; Inbucket on older ones) ─────────────────


def _mail_base() -> str:
    override = os.getenv("MAILPIT_URL") or os.getenv("INBUCKET_URL")
    if override:
        return override.rstrip("/")
    parsed = urlsplit(_supabase_url())
    return f"{parsed.scheme}://{parsed.hostname or '127.0.0.1'}:54324"


def _latest_email_html(client: httpx.Client, email: str) -> str | None:
    """Return the HTML body of the most recent message for ``email`` (or None if none yet).

    The Supabase CLI ships **Mailpit** as its local mail catcher (current versions) or **Inbucket**
    (older ones); we try the Mailpit REST API first and fall back to the Inbucket one."""
    base = _mail_base()

    # Mailpit: search by recipient (newest first), then fetch the message (HTML/Text capitalised).
    search = client.get(f"{base}/api/v1/search", params={"query": f"to:{email}"})
    if search.status_code == 200:
        messages = search.json().get("messages", [])
        if messages:
            detail = client.get(f"{base}/api/v1/message/{messages[0]['ID']}")
            if detail.status_code == 200:
                payload = detail.json()
                content = payload.get("HTML") or payload.get("Text")
                if isinstance(content, str) and content:
                    return content

    # Inbucket: mailbox keyed by the local-part (fall back to the full address).
    for mailbox in (email.split("@", 1)[0], email):
        listing = client.get(f"{base}/api/v1/mailbox/{mailbox}")
        if listing.status_code != 200 or not listing.json():
            continue
        message = client.get(f"{base}/api/v1/mailbox/{mailbox}/{listing.json()[-1]['id']}")
        if message.status_code != 200:
            continue
        content = message.json().get("body", {}).get("html") or message.json().get("body", {}).get(
            "text"
        )
        if isinstance(content, str) and content:
            return content
    return None


def _await_email_html(email: str, *, timeout: float = 20.0) -> str:
    deadline = time.monotonic() + timeout
    with httpx.Client(timeout=10.0) as client:
        while time.monotonic() < deadline:
            body = _latest_email_html(client, email)
            if body:
                return body
            time.sleep(0.5)
    raise AssertionError(f"no confirmation email arrived for {email} within {timeout}s")


def _confirmation_url(email_html: str) -> str:
    """Extract the rendered ``{{ .ConfirmationURL }}`` verify link (proof the template rendered).

    GoTrue renders it as ``<auth-url>/verify?token=...&type=signup&redirect_to=...`` — match the
    ``href`` carrying both the token and the redirect param (HTML-unescaping ``&amp;``)."""
    for match in re.finditer(r'href="([^"]+)"', email_html):
        href = html.unescape(match.group(1))
        if "token=" in href and "redirect_to=" in href:
            return href
    raise AssertionError(f"no verify link in email (template did not render): {email_html[:400]}")


def _redirect_to(confirmation_url: str) -> str | None:
    values = parse_qs(urlsplit(confirmation_url).query).get("redirect_to")
    return values[0] if values else None


@pytest.mark.integration
def test_confirmation_email_branding_and_redirect_allowlist() -> None:
    """The delivered email is branded; a listed redirect is honored, an un-listed one refused."""
    listed = f"{_SITE_URL}/auth/callback"
    unlisted = "https://evil.example.com/callback"

    with httpx.Client(timeout=30.0) as client:
        listed_email = _unique_email("listed")
        listed_resp = signup(client, listed_email, _COMPLIANT_PASSWORD, redirect_to=listed)
        assert listed_resp.status_code == 200, listed_resp.text
        listed_id = listed_resp.json()["id"]

        unlisted_email = _unique_email("unlisted")
        unlisted_resp = signup(client, unlisted_email, _COMPLIANT_PASSWORD, redirect_to=unlisted)
        unlisted_id = unlisted_resp.json().get("id") if unlisted_resp.status_code == 200 else None

        try:
            # Listed redirect: branded email whose verify link keeps the requested redirect.
            listed_html = _await_email_html(listed_email)
            assert _APP_NAME in listed_html, "the confirmation email must carry the app branding"
            listed_url = _confirmation_url(listed_html)
            assert _redirect_to(listed_url) == listed, f"listed redirect not honored: {listed_url}"

            # Un-listed redirect: GoTrue either rejects outright (4xx) or drops it back to
            # site_url — either way the evil origin must never reach the email link.
            if unlisted_resp.status_code >= 400:
                assert unlisted_resp.status_code in (400, 422), unlisted_resp.text
            else:
                unlisted_html = _await_email_html(unlisted_email)
                unlisted_url = _confirmation_url(unlisted_html)
                assert "evil.example.com" not in unlisted_url, f"origin leaked: {unlisted_url}"
                redirect = _redirect_to(unlisted_url)
                assert redirect is not None and redirect.startswith(_SITE_URL)
        finally:
            delete_user(client, listed_id)
            if unlisted_id:
                delete_user(client, unlisted_id)
