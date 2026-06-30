"""Non-destructive live-staging API smoke test for Lengua.

Exercises every Lengua API endpoint as the demo user against **LIVE staging** and prints a
per-endpoint PASS / FAIL / SKIP table. Because it hits live staging — real Cloud Run, and real
Groq on ``POST /generate`` / ``POST /discover`` — it is deliberately kept **out** of the FakeLLM CI
gate: it is never imported by the test suite and never wired into ``ci.yml`` or the default test
runs. The central orchestrator (not CI) runs it on demand::

    cd apps/api && uv run python scripts/staging_smoke.py

It is **non-destructive** by construction:

* never calls ``DELETE /account`` and never grades a card (no FSRS state is mutated);
* never persists a settings change (it only ``GET``s ``/settings``);
* the *only* write is a uniquely-named throwaway language that is created and then immediately
  deleted again, leaving the demo account exactly as it found it.

The two real-LLM probes are kept minimal (one trivial word) and gated behind ``SMOKE_INCLUDE_LLM``
(default on); an HTTP ``429`` cost-guard or ``503`` backoff on those probes is treated as PASS,
since the cost guard firing is correct behaviour, not an endpoint failure.

Config (env, with safe staging defaults):

* ``STAGING_API_URL``            default ``https://lengua-api-staging-cxiyhzhria-ew.a.run.app``
* ``STAGING_SUPABASE_URL``       default ``https://rydclyotzdwcbbeyitcx.supabase.co``
* ``STAGING_SUPABASE_ANON_KEY``  required for the GoTrue login (unless a token is supplied)
* ``STAGING_BEARER_TOKEN``       optional — skip login and use this access token directly
* ``DEMO_EMAIL`` / ``DEMO_PASSWORD``  default ``demo@lengua.test`` / ``demo-password-123``
* ``SMOKE_INCLUDE_LLM``          ``1`` (default) runs the real-LLM probes; ``0`` skips them
* ``SMOKE_TIMEOUT_SECONDS``      per-request timeout in seconds (default ``30``)

Exit code: ``0`` when every required endpoint passed (a ``SKIP`` is not a failure), ``1`` otherwise.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any

import httpx

DEFAULT_API_URL = "https://lengua-api-staging-cxiyhzhria-ew.a.run.app"
DEFAULT_SUPABASE_URL = "https://rydclyotzdwcbbeyitcx.supabase.co"
DEFAULT_DEMO_EMAIL = "demo@lengua.test"
DEFAULT_DEMO_PASSWORD = "demo-password-123"  # noqa: S105 (fixed demo credential)
DEFAULT_TIMEOUT_SECONDS = 30.0
# Sorts last and is obviously disposable, so a failed cleanup is easy to spot and remove by hand.
THROWAWAY_LANGUAGE_PREFIX = "zz-smoke"


class Status(Enum):
    """The outcome of a single endpoint check."""

    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"


@dataclass
class Result:
    """One row in the report: an endpoint, its status, and a short human detail."""

    name: str
    status: Status
    detail: str = ""


@dataclass
class Config:
    """Resolved runtime configuration, read from the environment + CLI overrides."""

    api_url: str
    supabase_url: str
    supabase_anon_key: str | None
    bearer_token: str | None
    demo_email: str
    demo_password: str
    include_llm: bool
    timeout: float

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> Config:
        """Build the config from env vars, applying any CLI overrides on top."""
        include_llm = _env_bool("SMOKE_INCLUDE_LLM", default=True)
        if bool(args.no_llm):
            include_llm = False
        timeout = (
            float(args.timeout)
            if args.timeout is not None
            else _env_float("SMOKE_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS)
        )
        return cls(
            api_url=_env("STAGING_API_URL", DEFAULT_API_URL).rstrip("/"),
            supabase_url=_env("STAGING_SUPABASE_URL", DEFAULT_SUPABASE_URL).rstrip("/"),
            supabase_anon_key=os.getenv("STAGING_SUPABASE_ANON_KEY") or None,
            bearer_token=os.getenv("STAGING_BEARER_TOKEN") or None,
            demo_email=_env("DEMO_EMAIL", DEFAULT_DEMO_EMAIL),
            demo_password=_env("DEMO_PASSWORD", DEFAULT_DEMO_PASSWORD),
            include_llm=include_llm,
            timeout=timeout,
        )


def _env(name: str, default: str) -> str:
    """Return ``$name`` if set and non-empty, else ``default``."""
    value = os.getenv(name)
    return value if value is not None and value != "" else default


def _env_bool(name: str, *, default: bool) -> bool:
    """Parse a truthy env flag (``1/true/yes/on``); ``default`` when unset/empty."""
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    """Parse a float env value; ``default`` when unset/empty/invalid."""
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _short(text: str, limit: int = 160) -> str:
    """Collapse whitespace and clip ``text`` to ``limit`` chars for a one-line detail."""
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 3] + "..."


def _http_detail(resp: httpx.Response) -> str:
    """A compact one-line detail for an unexpected response: status + clipped body."""
    return f"HTTP {resp.status_code} {_short(resp.text)}"


class StagingSmoke:
    """Drives the non-destructive endpoint sweep and accumulates results."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.results: list[Result] = []
        # Pre-supplied token short-circuits the login; otherwise login() fills it in.
        self.token: str | None = config.bearer_token
        # The first real language's id, captured by check_languages() and reused by the
        # language-scoped probes (review/discover/generate).
        self.language_id: int | None = None
        self.client = httpx.Client(base_url=config.api_url, timeout=config.timeout)

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self.client.close()

    # ── result + request helpers ──────────────────────────────────────────────────────────────

    def _record(self, name: str, status: Status, detail: str = "") -> None:
        self.results.append(Result(name=name, status=status, detail=detail))

    def _authed_headers(self) -> dict[str, str]:
        if self.token is None:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    @staticmethod
    def _json(resp: httpx.Response) -> Any:
        try:
            return resp.json()
        except ValueError:
            return None

    def _get(self, path: str, name: str) -> httpx.Response | None:
        try:
            return self.client.get(path, headers=self._authed_headers())
        except httpx.RequestError as exc:
            self._record(name, Status.FAIL, f"request error: {exc!r}")
            return None

    def _post(self, path: str, name: str, body: dict[str, Any]) -> httpx.Response | None:
        try:
            return self.client.post(path, headers=self._authed_headers(), json=body)
        except httpx.RequestError as exc:
            self._record(name, Status.FAIL, f"request error: {exc!r}")
            return None

    def _delete(self, path: str, name: str) -> httpx.Response | None:
        try:
            return self.client.delete(path, headers=self._authed_headers())
        except httpx.RequestError as exc:
            self._record(name, Status.FAIL, f"request error: {exc!r}")
            return None

    # ── auth ──────────────────────────────────────────────────────────────────────────────────

    def login(self) -> bool:
        """Obtain a bearer token (or reuse a supplied one). Returns True on success."""
        if self.token is not None:
            self._record("auth (token)", Status.PASS, "using STAGING_BEARER_TOKEN")
            return True
        if not self.config.supabase_anon_key:
            self._record(
                "auth (login)",
                Status.FAIL,
                "set STAGING_SUPABASE_ANON_KEY (or STAGING_BEARER_TOKEN) to authenticate",
            )
            return False
        url = f"{self.config.supabase_url}/auth/v1/token?grant_type=password"
        try:
            resp = httpx.post(
                url,
                headers={
                    "apikey": self.config.supabase_anon_key,
                    "Content-Type": "application/json",
                },
                json={"email": self.config.demo_email, "password": self.config.demo_password},
                timeout=self.config.timeout,
            )
        except httpx.RequestError as exc:
            self._record("auth (login)", Status.FAIL, f"request error: {exc!r}")
            return False
        if resp.status_code != 200:
            self._record("auth (login)", Status.FAIL, _http_detail(resp))
            return False
        body = self._json(resp)
        token = body.get("access_token") if isinstance(body, dict) else None
        if not isinstance(token, str) or token == "":
            self._record("auth (login)", Status.FAIL, "no access_token in GoTrue response")
            return False
        self.token = token
        self._record("auth (login)", Status.PASS, "GoTrue password grant -> bearer token")
        return True

    # ── unauthenticated probes ────────────────────────────────────────────────────────────────

    def check_health(self) -> None:
        name = "GET /health"
        resp = self._get("/health", name)
        if resp is None:
            return
        body = self._json(resp)
        ok = resp.status_code == 200 and isinstance(body, dict) and body.get("status") == "ok"
        self._record(name, Status.PASS if ok else Status.FAIL, _http_detail(resp))

    def check_ready(self) -> None:
        name = "GET /ready"
        resp = self._get("/ready", name)
        if resp is None:
            return
        body = self._json(resp)
        ok = resp.status_code == 200 and isinstance(body, dict) and body.get("status") == "ready"
        self._record(name, Status.PASS if ok else Status.FAIL, _http_detail(resp))

    def check_feature_flags(self) -> None:
        name = "GET /feature-flags"
        resp = self._get("/feature-flags", name)
        if resp is None:
            return
        body = self._json(resp)
        ok = (
            resp.status_code == 200
            and isinstance(body, dict)
            and all(isinstance(v, bool) for v in body.values())
        )
        if ok:
            self._record(name, Status.PASS, f"HTTP 200, {len(body)} flags")
        else:
            self._record(name, Status.FAIL, _http_detail(resp))

    # ── authenticated read probes ─────────────────────────────────────────────────────────────

    def check_me(self) -> None:
        name = "GET /me"
        resp = self._get("/me", name)
        if resp is None:
            return
        body = self._json(resp)
        ok = (
            resp.status_code == 200
            and isinstance(body, dict)
            and isinstance(body.get("id"), str)
            and isinstance(body.get("email"), str)
        )
        if ok:
            self._record(name, Status.PASS, f"HTTP 200, email={body['email']}")
        else:
            self._record(name, Status.FAIL, _http_detail(resp))

    def check_languages(self) -> None:
        name = "GET /languages"
        resp = self._get("/languages", name)
        if resp is None:
            return
        body = self._json(resp)
        if resp.status_code != 200 or not isinstance(body, list):
            self._record(name, Status.FAIL, _http_detail(resp))
            return
        # Capture the first real language for the language-scoped probes below.
        for item in body:
            if isinstance(item, dict) and isinstance(item.get("id"), int):
                self.language_id = int(item["id"])
                break
        if self.language_id is None:
            self._record(name, Status.PASS, "HTTP 200, 0 languages (scoped probes will SKIP)")
        else:
            self._record(
                name,
                Status.PASS,
                f"HTTP 200, {len(body)} languages (using id={self.language_id})",
            )

    def check_review_due(self) -> None:
        name = "GET /review/due"
        if self.language_id is None:
            self._record(name, Status.SKIP, "no language available")
            return
        resp = self._get(f"/review/due?language_id={self.language_id}", name)
        if resp is None:
            return
        body = self._json(resp)
        ok = (
            resp.status_code == 200
            and isinstance(body, dict)
            and isinstance(body.get("new"), list)
            and isinstance(body.get("due"), list)
        )
        if ok:
            detail = f"HTTP 200, {len(body['new'])} new / {len(body['due'])} due"
            self._record(name, Status.PASS, detail)
        else:
            self._record(name, Status.FAIL, _http_detail(resp))

    def check_settings(self) -> None:
        name = "GET /settings"
        resp = self._get("/settings", name)
        if resp is None:
            return
        body = self._json(resp)
        ok = (
            resp.status_code == 200
            and isinstance(body, dict)
            and isinstance(body.get("values"), dict)
        )
        if ok:
            self._record(name, Status.PASS, f"HTTP 200, {len(body['values'])} settings")
        else:
            self._record(name, Status.FAIL, _http_detail(resp))

    def check_account_export(self) -> None:
        name = "GET /account/export"
        resp = self._get("/account/export", name)
        if resp is None:
            return
        body = self._json(resp)
        ok = resp.status_code == 200 and isinstance(body, dict)
        if ok:
            self._record(name, Status.PASS, f"HTTP 200, {len(body)} sections")
        else:
            self._record(name, Status.FAIL, _http_detail(resp))

    # ── non-destructive write round-trip ──────────────────────────────────────────────────────

    def check_language_round_trip(self) -> None:
        """Create a throwaway language, then delete it — exercises POST + DELETE /languages."""
        name = f"{THROWAWAY_LANGUAGE_PREFIX}-{int(time.time())}"
        post_label = "POST /languages (throwaway)"
        resp = self._post("/languages", post_label, {"name": name, "vowelized": False})
        if resp is None:
            return
        body = self._json(resp)
        ok = resp.status_code == 200 and isinstance(body, dict) and isinstance(body.get("id"), int)
        if not ok:
            self._record(post_label, Status.FAIL, _http_detail(resp))
            return
        created_id = int(body["id"])
        self._record(post_label, Status.PASS, f"HTTP 200, id={created_id} name={name}")

        # Always clean up the throwaway so the sweep stays non-destructive.
        del_label = f"DELETE /languages/{created_id} (cleanup)"
        del_resp = self._delete(f"/languages/{created_id}", del_label)
        if del_resp is None:
            return
        if del_resp.status_code == 204:
            self._record(del_label, Status.PASS, "HTTP 204 (throwaway removed)")
        else:
            self._record(
                del_label,
                Status.FAIL,
                f"HTTP {del_resp.status_code} — throwaway '{name}' may linger; remove it by hand",
            )

    # ── real-LLM probes (gated, cost-aware) ───────────────────────────────────────────────────

    def check_discover(self) -> None:
        name = "POST /discover (preview)"
        if not self.config.include_llm:
            self._record(name, Status.SKIP, "SMOKE_INCLUDE_LLM disabled")
            return
        if self.language_id is None:
            self._record(name, Status.SKIP, "no language available")
            return
        resp = self._post("/discover", name, {"language_id": self.language_id, "count": 3})
        if resp is None:
            return
        if resp.status_code in (429, 503):
            self._record(
                name,
                Status.PASS,
                f"HTTP {resp.status_code} cost-guard/backoff (expected -> PASS)",
            )
            return
        body = self._json(resp)
        ok = (
            resp.status_code == 200
            and isinstance(body, dict)
            and isinstance(body.get("words"), list)
        )
        if ok:
            self._record(name, Status.PASS, f"HTTP 200, {len(body['words'])} suggestions")
        else:
            self._record(name, Status.FAIL, _http_detail(resp))

    def check_generate(self) -> None:
        name = "POST /generate (1 word, real LLM)"
        if not self.config.include_llm:
            self._record(name, Status.SKIP, "SMOKE_INCLUDE_LLM disabled")
            return
        if self.language_id is None:
            self._record(name, Status.SKIP, "no language available")
            return
        resp = self._post("/generate", name, {"language_id": self.language_id, "words": ["hola"]})
        if resp is None:
            return
        if resp.status_code in (429, 503):
            self._record(
                name,
                Status.PASS,
                f"HTTP {resp.status_code} cost-guard/backoff (expected -> PASS)",
            )
            return
        body = self._json(resp)
        if resp.status_code == 200 and isinstance(body, list):
            self._record(name, Status.PASS, f"HTTP 200, {len(body)} card previews (not persisted)")
        else:
            self._record(name, Status.FAIL, _http_detail(resp))

    # ── orchestration + reporting ─────────────────────────────────────────────────────────────

    def run(self) -> None:
        """Run the full sweep. Unauthenticated probes run first, then login gates the rest."""
        self.check_health()
        self.check_ready()
        self.check_feature_flags()
        if not self.login():
            return
        self.check_me()
        self.check_languages()
        self.check_review_due()
        self.check_settings()
        self.check_account_export()
        self.check_language_round_trip()
        self.check_discover()
        self.check_generate()

    def summary(self) -> dict[str, int]:
        """Count results by status."""
        counts = {"passed": 0, "failed": 0, "skipped": 0}
        for result in self.results:
            if result.status is Status.PASS:
                counts["passed"] += 1
            elif result.status is Status.FAIL:
                counts["failed"] += 1
            else:
                counts["skipped"] += 1
        return counts

    def print_report(self, *, as_json: bool) -> None:
        """Print the per-endpoint table (or a JSON document when ``as_json``)."""
        if as_json:
            payload = {
                "results": [
                    {"name": r.name, "status": r.status.value, "detail": r.detail}
                    for r in self.results
                ],
                "summary": self.summary(),
            }
            print(json.dumps(payload, indent=2))
            return
        name_width = max((len(r.name) for r in self.results), default=len("ENDPOINT"))
        print()
        print(f"{'ENDPOINT'.ljust(name_width)}  STATUS  DETAIL")
        print(f"{'-' * name_width}  ------  {'-' * 6}")
        for result in self.results:
            status = result.status.value.ljust(6)
            print(f"{result.name.ljust(name_width)}  {status}  {result.detail}")
        counts = self.summary()
        print()
        print(f"{counts['passed']} passed, {counts['failed']} failed, {counts['skipped']} skipped")


_ENV_HELP = """\
environment variables (all optional except an auth source):
  STAGING_API_URL            default the Cloud Run staging URL
  STAGING_SUPABASE_URL       default the Supabase staging project URL
  STAGING_SUPABASE_ANON_KEY  required for login (unless STAGING_BEARER_TOKEN is set)
  STAGING_BEARER_TOKEN       optional access token; skips the GoTrue login
  DEMO_EMAIL / DEMO_PASSWORD default the seeded demo account
  SMOKE_INCLUDE_LLM          1 (default) runs the real-LLM probes; 0 skips them
  SMOKE_TIMEOUT_SECONDS      per-request timeout (default 30)

This hits LIVE staging (real Cloud Run + real Groq) and is intentionally NOT part of CI.
"""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        prog="staging_smoke.py",
        description="Non-destructive live-staging API smoke test for Lengua (hits LIVE staging).",
        epilog=_ENV_HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--no-llm",
        action="store_true",
        help="skip the real-LLM /discover + /generate probes (overrides SMOKE_INCLUDE_LLM)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=None,
        help="per-request timeout in seconds (overrides SMOKE_TIMEOUT_SECONDS)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the report as JSON instead of a table",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint: run the sweep, print the report, and return the exit code."""
    args = parse_args(argv)
    config = Config.from_args(args)
    if not bool(args.json):
        print(f"Lengua staging smoke -> API {config.api_url}")
        print(
            f"  Supabase {config.supabase_url} | demo {config.demo_email} | "
            f"LLM probes {'on' if config.include_llm else 'off'}"
        )
    smoke = StagingSmoke(config)
    try:
        smoke.run()
    finally:
        smoke.close()
    smoke.print_report(as_json=bool(args.json))
    return 1 if smoke.summary()["failed"] > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
