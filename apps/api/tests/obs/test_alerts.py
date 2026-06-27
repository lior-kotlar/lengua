"""Tasks 5.7 + 5.8 (CI half): the as-code alerting + external uptime monitor are valid.

The Grafana provisioned-alerting files live under ``infra/grafana/alerts/*.yaml`` and the external
uptime-monitor descriptor under ``infra/uptime/*.yaml`` (reproducible per environment). Every
5.7.x / 5.8.1 verify is **live** (deliver to a real Slack/Discord/email channel, fire on staging
traffic, an external prober flips DOWN) and needs live Grafana Cloud creds + a deployed Cloud Run
service (Phase 6) — so NONE of those boxes are ticked here (logged in
``planning/outstanding-work.md`` §11).

This is the CI-verifiable substitute: it proves the committed config is **correct-by-construction**
so it is just-wire-creds-later, and it guards against drift:

1. **Parse + structure** — every file is valid YAML with the Grafana provisioning shape (contact
   points, notification policies, alert-rule groups) and the uptime descriptor's required fields.
2. **Condition integrity** — each alert rule's ``condition`` refId exists in its ``data`` stages and
   uids are unique.
3. **Metric cross-reference** — every PromQL metric an alert evaluates maps back to an instrument
   the backend actually emits (reusing the dashboard extractor), except the one allow-listed
   *external* probe metric (``probe_success``, from the uptime prober — task 5.8.1).
4. **Budget-threshold drift guard** — the LLM-budget early-warning threshold equals 20% of the
   configured ``GLOBAL_DAILY_BUDGET`` default, so the alert can't silently diverge from the gate.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from app.settings import Settings
from tests.obs.test_dashboards import (
    _emitted_prometheus_names,
    extract_metric_names,
    reduce_to_emitted,
)

# apps/api/tests/obs/<this file> → parents[2] = apps/api, parents[4] = repo root.
_REPO_ROOT = Path(__file__).resolve().parents[4]
_ALERTS_DIR = _REPO_ROOT / "infra" / "grafana" / "alerts"
_UPTIME_DIR = _REPO_ROOT / "infra" / "uptime"

_CONTACT_POINTS = _ALERTS_DIR / "contact-points.yaml"
_POLICIES = _ALERTS_DIR / "notification-policies.yaml"
_ALERT_RULES = _ALERTS_DIR / "alert-rules.yaml"
_UPTIME_MONITOR = _UPTIME_DIR / "uptime-monitor.yaml"

#: Metric produced by the EXTERNAL uptime prober (Grafana Synthetic Monitoring / Blackbox exporter,
#: task 5.8.1) — not an app instrument, so it is allow-listed for the alert cross-reference.
_EXTERNAL_PROBE_METRICS = frozenset({"probe_success"})

#: The on-call contact point every policy/route resolves to.
_CONTACT_NAME = "lengua-oncall"

#: All YAML files this group commits — used by the "everything parses" sweep.
_ALL_YAML = (_CONTACT_POINTS, _POLICIES, _ALERT_RULES, _UPTIME_MONITOR)


def _load(path: Path) -> dict[str, Any]:
    assert path.is_file(), f"missing committed file: {path}"
    try:
        data: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:  # pragma: no cover - failure path asserted elsewhere
        pytest.fail(f"{path.name}: invalid YAML: {exc}")
    assert isinstance(data, dict), f"{path.name}: top-level must be a mapping"
    return data


def _rules() -> list[dict[str, Any]]:
    """Every alert rule across all groups in alert-rules.yaml."""
    doc = _load(_ALERT_RULES)
    rules: list[dict[str, Any]] = []
    for group in doc.get("groups", []):
        for rule in group.get("rules", []):
            assert isinstance(rule, dict)
            rules.append(rule)
    return rules


# ── Parse / structure ────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", _ALL_YAML, ids=lambda p: p.name)
def test_all_files_parse(path: Path) -> None:
    """Every committed alerting/uptime YAML file parses into a mapping (the 5.7/5.8 lint verify)."""
    data = _load(path)
    assert data, f"{path.name}: parsed to an empty document"


def test_contact_points_structure() -> None:
    doc = _load(_CONTACT_POINTS)
    assert doc.get("apiVersion") == 1, "Grafana provisioning files must declare apiVersion: 1"
    points = doc.get("contactPoints")
    assert isinstance(points, list) and points, "contactPoints must be a non-empty list"

    point = next((p for p in points if p.get("name") == _CONTACT_NAME), None)
    assert point is not None, f"expected a contact point named {_CONTACT_NAME!r}"
    receivers = point.get("receivers")
    assert isinstance(receivers, list) and receivers, "the contact point needs >=1 receiver"

    # The active (uncommented) receiver is Slack; every active receiver carries a type + uid.
    types = set()
    for receiver in receivers:
        assert isinstance(receiver, dict)
        assert isinstance(receiver.get("uid"), str) and receiver["uid"], "receiver needs a uid"
        assert isinstance(receiver.get("type"), str) and receiver["type"], "receiver needs a type"
        assert isinstance(receiver.get("settings"), dict), "receiver needs settings"
        types.add(receiver["type"])
    assert "slack" in types, "the primary Slack receiver must be active"


def test_notification_policies_structure() -> None:
    doc = _load(_POLICIES)
    assert doc.get("apiVersion") == 1
    policies = doc.get("policies")
    assert isinstance(policies, list) and policies, "policies must be a non-empty list"

    root = policies[0]
    assert root.get("receiver") == _CONTACT_NAME, "the root policy must route to the contact point"
    for route in root.get("routes", []) or []:
        assert route.get("receiver") == _CONTACT_NAME, "every route must resolve to the contact"
        matchers = route.get("object_matchers")
        assert isinstance(matchers, list) and matchers, "a route needs object_matchers"


def test_alert_rules_structure_and_condition_integrity() -> None:
    """Every rule has the required fields and its `condition` refId exists in its `data`."""
    rules = _rules()
    assert rules, "expected at least one alert rule"

    seen_uids: set[str] = set()
    errors: list[str] = []
    for rule in rules:
        title = rule.get("title", "?")
        uid = rule.get("uid")
        if not isinstance(uid, str) or not uid:
            errors.append(f"rule {title!r}: missing uid")
        elif uid in seen_uids:
            errors.append(f"rule {title!r}: duplicate uid {uid}")
        else:
            seen_uids.add(uid)

        for key in ("title", "condition"):
            if not isinstance(rule.get(key), str) or not rule.get(key):
                errors.append(f"rule {uid}: missing {key!r}")
        if not isinstance(rule.get("for"), str) or not rule.get("for"):
            errors.append(f"rule {uid}: missing 'for' duration")

        labels = rule.get("labels")
        if not isinstance(labels, dict) or labels.get("severity") not in {"critical", "warning"}:
            errors.append(f"rule {uid}: labels.severity must be critical|warning")
        annotations = rule.get("annotations")
        if not isinstance(annotations, dict) or not annotations.get("summary"):
            errors.append(f"rule {uid}: annotations.summary required")

        data = rule.get("data")
        if not isinstance(data, list) or not data:
            errors.append(f"rule {uid}: 'data' must be a non-empty list")
            continue
        ref_ids = {stage.get("refId") for stage in data if isinstance(stage, dict)}
        if rule.get("condition") not in ref_ids:
            errors.append(
                f"rule {uid}: condition {rule.get('condition')!r} not among data refIds {ref_ids}"
            )

    assert not errors, "alert-rule problems:\n  - " + "\n  - ".join(errors)


def test_expected_rules_present() -> None:
    """The four Phase-5.7 alert rules are committed (guards against an accidentally-gutted file)."""
    uids = {rule.get("uid") for rule in _rules()}
    assert {
        "lengua-api-5xx-spike",  # 5.7.2
        "lengua-api-p95-latency",  # 5.7.3
        "lengua-llm-budget-80pct",  # 5.7.4
        "lengua-health-uptime-down",  # 5.7.5
    } <= uids, f"missing expected alert-rule uids; found {uids}"


# ── Metric cross-reference (reuse the dashboard extractor) ──────────────────────────────────────


def _query_expressions() -> list[str]:
    """PromQL `expr` strings from every rule's query stage (expression stages carry no `expr`)."""
    exprs: list[str] = []
    for rule in _rules():
        for stage in rule.get("data", []):
            model = stage.get("model", {}) if isinstance(stage, dict) else {}
            expr = model.get("expr")
            if isinstance(expr, str) and expr.strip():
                exprs.append(expr)
    return exprs


def test_alerts_reference_only_emitted_or_probe_metrics() -> None:
    """Every metric an alert evaluates is an emitted instrument or the allow-listed probe metric."""
    emitted = _emitted_prometheus_names()
    exprs = _query_expressions()
    assert exprs, "expected the alert rules to carry PromQL query expressions"

    bad: dict[str, set[str]] = {}
    for expr in exprs:
        for metric in extract_metric_names(expr):
            if metric in _EXTERNAL_PROBE_METRICS:
                continue
            if reduce_to_emitted(metric, emitted) is None:
                bad.setdefault(metric, set()).add(expr)
    assert not bad, (
        "alert rules reference metrics the backend does not emit "
        f"(and are not allow-listed probes): {sorted(bad)}\n"
        f"emitted (Prometheus form): {sorted(emitted)}"
    )


def test_uptime_rule_uses_external_probe_metric() -> None:
    """5.7.5 evaluates the external `probe_success` series (ties to the uptime monitor, 5.8.1)."""
    rule = next(r for r in _rules() if r.get("uid") == "lengua-health-uptime-down")
    exprs = [
        s["model"]["expr"]
        for s in rule["data"]
        if isinstance(s.get("model"), dict) and "expr" in s["model"]
    ]
    metrics = set().union(*(extract_metric_names(e) for e in exprs))
    assert metrics & _EXTERNAL_PROBE_METRICS, f"uptime rule should use probe_success; saw {metrics}"


# ── Budget-threshold drift guard ─────────────────────────────────────────────────────────────────


def _threshold_param(rule: dict[str, Any]) -> float:
    """The first threshold-evaluator param of a rule's condition stage."""
    condition = rule["condition"]
    stage = next(s for s in rule["data"] if s.get("refId") == condition)
    return float(stage["model"]["conditions"][0]["evaluator"]["params"][0])


def test_budget_alert_threshold_tracks_global_daily_budget() -> None:
    """The LLM-budget early-warning fires at 20% remaining = 80% of GLOBAL_DAILY_BUDGET consumed.

    Reads the default off the field (no env / no Settings instantiation) so the alert threshold and
    the configured ceiling can't silently drift apart.
    """
    budget_default = Settings.model_fields["global_daily_budget"].default
    assert isinstance(budget_default, int) and budget_default > 0
    expected = round(0.2 * budget_default)

    rule = next(r for r in _rules() if r.get("uid") == "lengua-llm-budget-80pct")
    assert _threshold_param(rule) == expected, (
        f"budget alert threshold {_threshold_param(rule)} != 20% of "
        f"GLOBAL_DAILY_BUDGET default ({budget_default} → {expected}); update the alert or the test"
    )
    # The condition must be "remaining < threshold" (less-than), i.e. an early warning as it falls.
    condition = rule["condition"]
    stage = next(s for s in rule["data"] if s.get("refId") == condition)
    assert stage["model"]["conditions"][0]["evaluator"]["type"] == "lt"


# ── External uptime monitor (5.8.1) ──────────────────────────────────────────────────────────────


def test_uptime_monitor_descriptor() -> None:
    """The external prober targets /health on a few-minute interval, alerting on failure (5.8.1)."""
    doc = _load(_UPTIME_MONITOR)
    monitor = doc.get("monitor")
    assert isinstance(monitor, dict), "uptime-monitor.yaml needs a 'monitor' mapping"

    target = monitor.get("target_url")
    assert isinstance(target, str) and target.endswith("/health"), (
        f"the monitor must target /health, got {target!r}"
    )
    interval = monitor.get("interval_seconds")
    assert isinstance(interval, int) and 60 <= interval <= 600, (
        f"interval should be a few minutes (60-600s), got {interval!r}"
    )
    assert monitor.get("alert_on_failure") is True, "the monitor must alert on failure"
    assert monitor.get("expected_status") == 200, "prod /health should expect HTTP 200"
    contact = monitor.get("contact")
    assert isinstance(contact, dict) and contact.get("type"), "the monitor needs a contact"

    # The provider encodings all describe the SAME /health target.
    for name, provider in (doc.get("providers") or {}).items():
        blob = yaml.safe_dump(provider)
        assert "/health" in blob, f"provider {name!r} must target /health"
