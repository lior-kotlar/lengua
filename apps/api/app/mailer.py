"""Transactional-email seam (Phase 8, task 8.3.1).

The only mail Lengua sends today is the **account-deletion confirmation link** for the public
``/delete-account`` form. Email delivery follows the same "config flip, never a code change" seam as
the LLM provider:

* :class:`LoggingMailer` is the default — it sends **nothing** (zero network egress) and just logs
  that a message was suppressed. This is the ``local`` / ``ci`` / ``test`` / ``e2e`` path, and also
  the prod path *until* the owner configures Resend (owner item, issue #103). Suppressing mail here
  means the public form still accepts requests and the flow stays fully testable without SMTP.
* :class:`ResendMailer` is selected automatically when ``RESEND_API_KEY`` is set. It POSTs to the
  Resend HTTP API. A custom ``transport`` is injectable so the send path is unit-tested offline with
  an :class:`httpx.MockTransport` (no real email, no key).

The seam is the :class:`Mailer` Protocol + :func:`get_mailer`; call sites never branch on provider.
"""

from __future__ import annotations

import logging

import httpx

from app.settings import Settings, get_settings

logger = logging.getLogger("lengua.mailer")

#: Resend's transactional-send endpoint.
_RESEND_ENDPOINT = "https://api.resend.com/emails"


def _redact_email(email: str) -> str:
    """Mask an address for logs: ``a***@example.com`` — enough to correlate, not to expose."""
    local, _, domain = email.partition("@")
    shown = local[:1] if local else ""
    return f"{shown}***@{domain}" if domain else f"{shown}***"


class Mailer:
    """The transactional-mail seam; a concrete mailer implements ``send_account_deletion_link``."""

    async def send_account_deletion_link(self, *, to_email: str, confirm_url: str) -> None:
        """Email ``to_email`` a link (``confirm_url``) that completes their account deletion."""
        raise NotImplementedError


class LoggingMailer(Mailer):
    """A no-egress mailer: logs that a message was suppressed instead of sending it.

    The default everywhere no mail provider is configured. It deliberately does **not** log the
    ``confirm_url`` (which carries the deletion token) at INFO, so a token never lands in logs.
    """

    async def send_account_deletion_link(self, *, to_email: str, confirm_url: str) -> None:
        logger.info(
            "account-deletion email suppressed (no mail provider configured): to=%s",
            _redact_email(to_email),
        )


class ResendMailer(Mailer):
    """Send transactional mail via the Resend HTTP API (selected when ``RESEND_API_KEY`` is set)."""

    def __init__(
        self,
        *,
        api_key: str,
        sender: str,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = api_key
        self._sender = sender
        self._transport = transport

    async def send_account_deletion_link(self, *, to_email: str, confirm_url: str) -> None:
        subject = "Confirm your Lengua account deletion"
        body = (
            "You (or someone using your email) requested deletion of your Lengua account.\n\n"
            "To permanently delete your account and all your learning data, open this link "
            "within the next hour:\n\n"
            f"{confirm_url}\n\n"
            "If you did not request this, you can safely ignore this email — nothing will be "
            "deleted unless the link above is opened."
        )
        payload = {
            "from": self._sender,
            "to": [to_email],
            "subject": subject,
            "text": body,
        }
        headers = {"Authorization": f"Bearer {self._api_key}"}
        # A delivery failure must NEVER surface to the caller: mail is attempted only for a
        # REGISTERED address, so a raised transport error (Resend down/timeout/DNS) reaching the
        # endpoint would 500 a registered email while an unregistered one returns 200 — an
        # account-existence oracle. So we catch BOTH a raised transport error and a >=400 status,
        # log, and swallow (the endpoint always returns the same generic ack). Mirrors the sibling
        # service-role admin call sites, which likewise wrap httpx.HTTPError.
        try:
            async with httpx.AsyncClient(transport=self._transport, timeout=30.0) as client:
                response = await client.post(_RESEND_ENDPOINT, headers=headers, json=payload)
        except httpx.HTTPError as exc:
            logger.warning(
                "Resend send failed (transport) for to=%s: %s", _redact_email(to_email), exc
            )
            return
        if response.status_code >= 400:
            logger.warning(
                "Resend send failed (%s) for to=%s", response.status_code, _redact_email(to_email)
            )


def build_mailer(settings: Settings) -> Mailer:
    """Return the active mailer: ``ResendMailer`` when a key is set, else ``LoggingMailer``."""
    api_key = settings.resend_api_key.get_secret_value()
    if api_key:
        return ResendMailer(api_key=api_key, sender=settings.email_from)
    return LoggingMailer()


def get_mailer() -> Mailer:
    """FastAPI dependency: the active transactional mailer (tests override with a spy)."""
    return build_mailer(get_settings())
