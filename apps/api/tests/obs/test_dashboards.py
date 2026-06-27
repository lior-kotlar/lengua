"""Task 5.6 (CI half): the Grafana dashboards are valid + reference only metrics we emit.

The dashboards live as code under ``infra/grafana/dashboards/*.json`` (reproducible per
environment). This test is the CI-verifiable replacement for the live "renders non-empty after a
load script" check (owner/Phase-6, logged in ``planning/outstanding-work.md`` §11). It makes the
dashboards **correct-by-construction** and guards against **metric-rename drift**:

1. **Structural validity** — every committed dashboard parses as JSON and carries the Grafana
   dashboard fields we rely on for provisioning (``uid`` / ``title`` / ``schemaVersion`` /
   ``panels`` / a ``datasource`` template variable), with unique uids across the set and unique
   panel ids within each dashboard.
2. **Metric cross-reference** — every Prometheus metric name referenced by a production dashboard's
   PromQL maps back to an instrument the backend **actually emits**. The emitted set is discovered
   programmatically (AST of :mod:`app.llm_observability` + :mod:`app.product_metrics`, plus the
   known FastAPI request-duration histogram) — never a hand-maintained duplicate list — so renaming
   an instrument without updating a dashboard fails CI.

The **infra** dashboard (task 5.6.4) is a Phase-6 *skeleton* (Cloud Run / Loki panels whose metrics
do not exist yet); it is tagged ``phase6-skeleton`` and is structurally validated but **excluded**
from the metric cross-reference (and not ticked).

Metric-name policy (see ``infra/grafana/README.md``): the provider-agnostic ``llm_*`` / ``*_total``
/ gauge names are already valid Prometheus names and are referenced as-is. The FastAPI
``http.server.duration`` histogram (unit ``ms``) reaches Prometheus/Mimir as
``http_server_duration_milliseconds`` with the ``_bucket`` / ``_count`` / ``_sum`` series under the
default OTLP→Prometheus translation (suffixes on); the reducer below strips the histogram + unit
suffixes so either the suffixed or unsuffixed form maps back to the emitted instrument.
"""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

import pytest

# apps/api/tests/obs/<this file> → parents[2] = apps/api, parents[4] = repo root.
_APPS_API = Path(__file__).resolve().parents[2]
_REPO_ROOT = Path(__file__).resolve().parents[4]
_DASHBOARD_DIR = _REPO_ROOT / "infra" / "grafana" / "dashboards"

#: The FastAPI server request-duration histogram (task 5.2.6). Not defined in our code (the
#: instrumentation owns it), so its name is listed here and drift-checked against
#: ``test_red_metrics._DURATION_HISTOGRAM_NAMES`` by ``test_histogram_names_match_red_metrics``.
_FASTAPI_DURATION_HISTOGRAMS = frozenset({"http.server.duration", "http.server.request.duration"})
#: …as Prometheus sees them (dots → underscores) — the base the duration-histogram series reduce to.
_HISTOGRAM_PROM_BASES = frozenset(n.replace(".", "_") for n in _FASTAPI_DURATION_HISTOGRAMS)

#: Tag marking a dashboard as a Phase-6 skeleton — structurally validated but not cross-referenced.
_SKELETON_TAG = "phase6-skeleton"

#: OTel meter instrument-factory method names whose first positional arg is the instrument name.
_INSTRUMENT_FACTORIES = frozenset(
    {
        "create_counter",
        "create_up_down_counter",
        "create_histogram",
        "create_gauge",
        "create_observable_counter",
        "create_observable_gauge",
        "create_observable_up_down_counter",
    }
)

# ── PromQL metric-name extraction ────────────────────────────────────────────────────────────────

_IDENT_RE = re.compile(r"[a-zA-Z_:][a-zA-Z0-9_:]*")
# Aggregation label lists / binary matching clauses whose parenthesised group holds LABELS, not
# metrics: ``by (a, b)``, ``without (..)``, ``on (..)``, ``ignoring (..)``, ``group_left (..)``.
_LABEL_LIST_RE = re.compile(
    r"\b(?:by|without|on|ignoring|group_left|group_right)\s*\([^()]*\)", re.IGNORECASE
)
# PromQL keywords / aggregation operators that are identifiers but never metric names. Functions
# (rate/sum/histogram_quantile/…) are excluded by the "followed by (" rule, but listing the bare
# keywords here is belt-and-suspenders for any that can appear without a following paren.
_PROMQL_KEYWORDS = frozenset(
    {
        "by",
        "without",
        "on",
        "ignoring",
        "group_left",
        "group_right",
        "and",
        "or",
        "unless",
        "offset",
        "bool",
        "le",
        "vector",
        "scalar",
        "inf",
        "nan",
        "start",
        "end",
        "sum",
        "avg",
        "min",
        "max",
        "count",
        "group",
        "topk",
        "bottomk",
        "quantile",
        "stddev",
        "stdvar",
        "count_values",
    }
)

# Prometheus series suffixes for histograms/summaries, and the unit suffixes the OTLP→Prometheus
# translation may append (from the OTel instrument's unit).
_SERIES_SUFFIXES = ("_bucket", "_sum", "_count")
_UNIT_SUFFIXES = ("_milliseconds", "_seconds", "_bytes", "_ratio")


def extract_metric_names(expr: str) -> set[str]:
    """Return the set of Prometheus metric names referenced by a PromQL expression.

    Strips quoted strings, range/offset ``[..]`` selectors, ``{..}`` label matchers, aggregation
    label lists (``by (..)`` etc.) and ``$``-variables, then collects identifiers that are not
    function calls (``ident(``) and not PromQL keywords — i.e. the names in metric-selector
    position. Deliberately simple (no full PromQL parser dependency) but exercised by
    ``test_metric_extractor`` on representative expressions.
    """
    s = expr
    s = re.sub(r"\"(?:[^\"\\]|\\.)*\"", " ", s)  # double-quoted strings
    s = re.sub(r"'(?:[^'\\]|\\.)*'", " ", s)  # single-quoted strings
    s = re.sub(r"\[[^\]]*\]", " ", s)  # range / subquery / offset brackets
    s = re.sub(r"\{[^{}]*\}", " ", s)  # label matchers
    while True:  # aggregation label lists (repeat: group_left(..) can follow on(..))
        collapsed = _LABEL_LIST_RE.sub(" ", s)
        if collapsed == s:
            break
        s = collapsed
    s = re.sub(r"\$\{?[a-zA-Z_][a-zA-Z0-9_]*\}?", " ", s)  # $__rate_interval / ${var}

    names: set[str] = set()
    for match in _IDENT_RE.finditer(s):
        token = match.group(0)
        if s[match.end() :].lstrip().startswith("("):  # function call → not a metric
            continue
        if token.lower() in _PROMQL_KEYWORDS:
            continue
        names.add(token)
    return names


def reduce_to_emitted(metric: str, emitted_prom: set[str]) -> str | None:
    """Map a referenced Prometheus metric name back to an emitted instrument, or ``None``.

    Checks the full name first (so ``llm_calls_total`` matches the instrument literally named
    ``llm_calls_total`` — its ``_total`` is part of the name, not a strippable suffix), then strips
    a histogram series suffix (``_bucket`` / ``_sum`` / ``_count``) and finally a unit suffix
    (``_milliseconds`` / …) so the FastAPI duration histogram's Prometheus form maps back to
    ``http.server.duration``.
    """
    if metric in emitted_prom:
        return metric
    base = metric
    for suffix in _SERIES_SUFFIXES:
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    if base in emitted_prom:
        return base
    for suffix in _UNIT_SUFFIXES:
        if base.endswith(suffix) and base[: -len(suffix)] in emitted_prom:
            return base[: -len(suffix)]
    return None


# ── Emitted-instrument discovery (AST of the metric modules) ──────────────────────────


def instrument_names_in_source(path: Path) -> set[str]:
    """Instrument names created in a module: the str first-arg of every ``meter.create_*`` call."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in _INSTRUMENT_FACTORIES
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            names.add(node.args[0].value)
    return names


def emitted_instrument_names() -> set[str]:
    """All OTel instrument names the backend emits (custom metrics + the FastAPI RED histogram)."""
    names = instrument_names_in_source(_APPS_API / "app" / "llm_observability.py")
    names |= instrument_names_in_source(_APPS_API / "app" / "product_metrics.py")
    names |= set(_FASTAPI_DURATION_HISTOGRAMS)
    return names


def _emitted_prometheus_names() -> set[str]:
    """Emitted instrument names as Prometheus would see them (dots → underscores)."""
    return {name.replace(".", "_") for name in emitted_instrument_names()}


# ── Dashboard loading + helpers ───────────────────────────────────────────────────────

_DASHBOARD_PATHS = sorted(_DASHBOARD_DIR.glob("*.json"))


def _load(path: Path) -> dict[str, Any]:
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - failure path asserted via test below
        pytest.fail(f"{path.name}: invalid JSON: {exc}")
    assert isinstance(data, dict), f"{path.name}: top-level must be a JSON object"
    return data


def _panels(dashboard: dict[str, Any]) -> list[dict[str, Any]]:
    return list(dashboard.get("panels", []))


def _expressions(dashboard: dict[str, Any]) -> list[str]:
    exprs: list[str] = []
    for panel in _panels(dashboard):
        for target in panel.get("targets", []) or []:
            expr = target.get("expr")
            if isinstance(expr, str) and expr.strip():
                exprs.append(expr)
    return exprs


def _is_skeleton(dashboard: dict[str, Any]) -> bool:
    return _SKELETON_TAG in (dashboard.get("tags") or [])


def _referenced_metrics(dashboard: dict[str, Any]) -> set[str]:
    metrics: set[str] = set()
    for expr in _expressions(dashboard):
        metrics |= extract_metric_names(expr)
    return metrics


# ── Tests ────────────────────────────────────────────────────────────────────────────────────────


def test_dashboard_files_present() -> None:
    """The four Phase-5.6 dashboards are committed as code."""
    assert _DASHBOARD_DIR.is_dir(), f"missing dashboards dir: {_DASHBOARD_DIR}"
    uids = {_load(p).get("uid") for p in _DASHBOARD_PATHS}
    assert {
        "lengua-service-health",
        "lengua-cost-guard",
        "lengua-product",
        "lengua-infra",
    } <= uids, f"missing expected dashboard uids; found {uids}"


def test_emitted_instruments_discovered() -> None:
    """The AST discovery finds the real custom instruments (guards the parser against none)."""
    emitted = emitted_instrument_names()
    assert {
        "llm_calls_total",
        "llm_cap_hits_total",
        "llm_tokens_total",
        "llm_budget_remaining",
        "reviews_total",
        "cards_created_total",
        "signups_total",
        "active_users",
    } <= emitted, f"AST discovery missed instruments; found {sorted(emitted)}"


def test_histogram_names_match_red_metrics() -> None:
    """Single source of truth for the RED histogram name (drift guard vs the 5.2.6 test)."""
    from tests.obs.test_red_metrics import _DURATION_HISTOGRAM_NAMES

    assert _FASTAPI_DURATION_HISTOGRAMS == _DURATION_HISTOGRAM_NAMES


@pytest.mark.parametrize("path", _DASHBOARD_PATHS, ids=lambda p: p.name)
def test_dashboard_is_structurally_valid(path: Path) -> None:
    """Every committed dashboard carries the Grafana fields provisioning relies on."""
    dashboard = _load(path)
    errors: list[str] = []

    for key, kind in (("uid", str), ("title", str), ("schemaVersion", int)):
        value = dashboard.get(key)
        if not isinstance(value, kind) or (kind is str and not value):
            errors.append(f"missing/invalid {key!r} (expected non-empty {kind.__name__})")

    panels = dashboard.get("panels")
    if not isinstance(panels, list) or not panels:
        errors.append("'panels' must be a non-empty list")
        panels = []

    templating = dashboard.get("templating")
    if not isinstance(templating, dict) or not isinstance(templating.get("list"), list):
        errors.append("'templating.list' must be a list")
    declared_vars = declared_datasource_vars(dashboard)
    if not declared_vars:
        errors.append("expected at least one 'datasource'-type template variable (portability)")

    time_range = dashboard.get("time")
    if not isinstance(time_range, dict) or "from" not in time_range or "to" not in time_range:
        errors.append("'time' must define 'from' and 'to'")

    seen_ids: set[int] = set()
    for index, panel in enumerate(panels):
        if not isinstance(panel, dict):
            errors.append(f"panel[{index}] is not an object")
            continue
        prefix = f"panel[{index}] ({panel.get('title', '?')})"
        if not isinstance(panel.get("type"), str) or not panel.get("type"):
            errors.append(f"{prefix}: missing 'type'")
        if not isinstance(panel.get("title"), str):
            errors.append(f"{prefix}: missing 'title'")
        panel_id = panel.get("id")
        if not isinstance(panel_id, int):
            errors.append(f"{prefix}: 'id' must be an int")
        elif panel_id in seen_ids:
            errors.append(f"{prefix}: duplicate panel id {panel_id}")
        else:
            seen_ids.add(panel_id)
        grid = panel.get("gridPos")
        if not isinstance(grid, dict) or not all(
            isinstance(grid.get(k), int) for k in ("h", "w", "x", "y")
        ):
            errors.append(f"{prefix}: 'gridPos' must have int h/w/x/y")

        for target in panel.get("targets", []) or []:
            if not isinstance(target, dict):
                errors.append(f"{prefix}: target is not an object")
                continue
            expr = target.get("expr")
            if not isinstance(expr, str) or not expr.strip():
                errors.append(f"{prefix}: target missing non-empty 'expr'")
            ref_id = target.get("refId")
            if not isinstance(ref_id, str) or not ref_id:
                errors.append(f"{prefix}: target missing 'refId'")

        # Any datasource variable reference must point at a declared template variable.
        for ds in panel_datasource_refs(panel):
            var = datasource_var_name(ds)
            if var is not None and var not in declared_vars:
                errors.append(f"{prefix}: datasource var ${{{var}}} not declared in templating")

    assert not errors, f"{path.name} structural problems:\n  - " + "\n  - ".join(errors)


def declared_datasource_vars(dashboard: dict[str, Any]) -> set[str]:
    """Names of ``type=datasource`` template variables declared on the dashboard."""
    variables = dashboard.get("templating", {}).get("list", [])
    return {
        v["name"]
        for v in variables
        if isinstance(v, dict) and v.get("type") == "datasource" and isinstance(v.get("name"), str)
    }


def panel_datasource_refs(panel: dict[str, Any]) -> list[Any]:
    """The panel's own datasource plus each target's datasource (whatever shape they are)."""
    refs: list[Any] = []
    if "datasource" in panel:
        refs.append(panel["datasource"])
    for target in panel.get("targets", []) or []:
        if isinstance(target, dict) and "datasource" in target:
            refs.append(target["datasource"])
    return refs


def datasource_var_name(datasource: Any) -> str | None:
    """Return the template-variable name if ``datasource.uid`` is a ``${var}`` ref, else None."""
    uid = datasource.get("uid") if isinstance(datasource, dict) else None
    if isinstance(uid, str):
        match = re.fullmatch(r"\$\{(\w+)\}", uid)
        if match:
            return match.group(1)
    return None


_PRODUCTION_DASHBOARDS = [p for p in _DASHBOARD_PATHS if not _is_skeleton(_load(p))]


@pytest.mark.parametrize("path", _PRODUCTION_DASHBOARDS, ids=lambda p: p.name)
def test_production_dashboard_references_only_emitted_metrics(path: Path) -> None:
    """Every PromQL metric a production dashboard queries maps to an emitted instrument."""
    dashboard = _load(path)
    emitted_prom = _emitted_prometheus_names()
    referenced = _referenced_metrics(dashboard)
    assert referenced, f"{path.name}: expected the dashboard to reference at least one metric"

    unknown = {m: reduce_to_emitted(m, emitted_prom) for m in sorted(referenced)}
    bad = sorted(m for m, mapped in unknown.items() if mapped is None)
    assert not bad, (
        f"{path.name} references metrics the backend does not emit: {bad}\n"
        f"emitted (Prometheus form): {sorted(emitted_prom)}"
    )


def test_dashboards_cover_their_key_metrics() -> None:
    """Each production dashboard actually uses the metric group it is responsible for.

    Not just "no unknown names" but "the right names are present" — so an accidentally-gutted
    dashboard (or a panel silently dropped) fails here.
    """
    by_uid = {d["uid"]: _referenced_metrics(d) for d in (_load(p) for p in _PRODUCTION_DASHBOARDS)}
    emitted_prom = _emitted_prometheus_names()

    # Service health → the FastAPI RED duration histogram.
    health = by_uid["lengua-service-health"]
    assert any(reduce_to_emitted(m, emitted_prom) in _HISTOGRAM_PROM_BASES for m in health), (
        f"service-health must use the request-duration histogram; saw {sorted(health)}"
    )

    # Cost guard → the cost-guard counters + budget gauge.
    cost = by_uid["lengua-cost-guard"]
    assert {
        "llm_calls_total",
        "llm_budget_remaining",
        "llm_cap_hits_total",
        "llm_tokens_total",
    } <= cost, f"cost-guard missing key metrics; saw {sorted(cost)}"

    # Product → the product counters + active-users gauge.
    product = by_uid["lengua-product"]
    assert {
        "reviews_total",
        "cards_created_total",
        "signups_total",
        "active_users",
    } <= product, f"product missing key metrics; saw {sorted(product)}"


def test_infra_dashboard_is_marked_phase6_skeleton() -> None:
    """The infra dashboard is the deferred skeleton: tagged + excluded from the cross-reference."""
    infra = next(d for d in (_load(p) for p in _DASHBOARD_PATHS) if d.get("uid") == "lengua-infra")
    assert _is_skeleton(infra), "infra dashboard must carry the 'phase6-skeleton' tag (5.6.4)"
    assert infra not in [_load(p) for p in _PRODUCTION_DASHBOARDS]


def test_unique_uids_across_dashboards() -> None:
    """Provisioning keys on uid — duplicates would clobber each other."""
    uids = [_load(p)["uid"] for p in _DASHBOARD_PATHS]
    assert len(uids) == len(set(uids)), f"duplicate dashboard uids: {uids}"


# ── Extractor unit tests (so the cross-reference above is trustworthy) ──────────────────

_DURATION_COUNT = "http_server_duration_milliseconds_count"
_DURATION_BUCKET = "http_server_duration_milliseconds_bucket"


def test_metric_extractor() -> None:
    cases: list[tuple[str, set[str]]] = [
        ("min(llm_budget_remaining)", {"llm_budget_remaining"}),
        ("max(active_users)", {"active_users"}),
        ("sum(increase(reviews_total[1d]))", {"reviews_total"}),
        ("sum by (gate) (rate(llm_cap_hits_total[$__rate_interval]))", {"llm_cap_hits_total"}),
        (
            "sum by (kind, result) (rate(llm_calls_total[$__rate_interval]))",
            {"llm_calls_total"},
        ),
        (
            f'sum by (http_target) (rate({_DURATION_COUNT}{{http_status_code=~"5.."}}'
            "[$__rate_interval]))",
            {_DURATION_COUNT},
        ),
        (
            "histogram_quantile(0.95, sum by (le, http_target) "
            f"(rate({_DURATION_BUCKET}[$__rate_interval])))",
            {_DURATION_BUCKET},
        ),
        (
            f'sum(rate({_DURATION_COUNT}{{http_status_code=~"5.."}}[$__rate_interval])) '
            f"/ clamp_min(sum(rate({_DURATION_COUNT}[$__rate_interval])), 1)",
            {_DURATION_COUNT},
        ),
    ]
    for expr, expected in cases:
        assert extract_metric_names(expr) == expected, expr


def test_reduce_to_emitted() -> None:
    emitted = _emitted_prometheus_names()
    # Custom metrics match literally (the trailing _total is part of the name).
    assert reduce_to_emitted("llm_calls_total", emitted) == "llm_calls_total"
    assert reduce_to_emitted("active_users", emitted) == "active_users"
    # The FastAPI histogram's Prometheus forms reduce back to the dotted instrument base.
    assert reduce_to_emitted(_DURATION_BUCKET, emitted) == "http_server_duration"
    assert reduce_to_emitted(_DURATION_COUNT, emitted) == "http_server_duration"
    assert reduce_to_emitted("http_server_duration_bucket", emitted) == "http_server_duration"
    # A genuinely unknown metric does not map.
    assert reduce_to_emitted("gemini_calls_total", emitted) is None
    assert reduce_to_emitted("totally_made_up", emitted) is None
