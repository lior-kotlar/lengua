"""Task 1.5.9 verify: ``PUT /settings`` upserts a value; ``GET /settings`` reads it back.

The settings store is a generic per-user ``{key: value}`` map (daily limits, discover count, …).
This drives the router over HTTP: PUT a daily-limit value, GET it back unchanged, then PUT a
second key and confirm PUT merges (does not replace) the existing keys.

Named ``tests/api/test_settings.py`` (the API router); distinct from ``tests/test_settings.py``
(which covers ``app.settings``) — both import cleanly as they live in separate test packages.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


async def test_put_then_get_roundtrip(api_client: AsyncClient) -> None:
    # Empty to start.
    assert (await api_client.get("/settings")).json() == {"values": {}}

    # PUT a daily-limit value.
    put = await api_client.put("/settings", json={"values": {"daily_total_limit": "30"}})
    assert put.status_code == 200
    assert put.json() == {"values": {"daily_total_limit": "30"}}

    # GET it back unchanged.
    got = await api_client.get("/settings")
    assert got.status_code == 200
    assert got.json() == {"values": {"daily_total_limit": "30"}}


async def test_put_merges_and_updates(api_client: AsyncClient) -> None:
    await api_client.put("/settings", json={"values": {"daily_total_limit": "30"}})

    # A second PUT merges a new key and updates the existing one (does not wipe the map).
    merged = await api_client.put(
        "/settings", json={"values": {"daily_new_limit": "5", "daily_total_limit": "40"}}
    )
    assert merged.status_code == 200
    assert merged.json() == {"values": {"daily_total_limit": "40", "daily_new_limit": "5"}}


async def test_put_empty_values_rejected_422(api_client: AsyncClient) -> None:
    # min_length=1 on the values map -> 422.
    assert (await api_client.put("/settings", json={"values": {}})).status_code == 422


async def test_put_blank_key_rejected_422(api_client: AsyncClient) -> None:
    # The service rejects a blank/whitespace key -> 422.
    resp = await api_client.put("/settings", json={"values": {"   ": "x"}})
    assert resp.status_code == 422


async def test_put_out_of_bounds_rejected_422(api_client: AsyncClient) -> None:
    # A typed numeric value outside its bounds is refused, and nothing is written (finding S9).
    resp = await api_client.put("/settings", json={"values": {"daily_new_limit": "100000"}})
    assert resp.status_code == 422
    assert (await api_client.get("/settings")).json() == {"values": {}}


async def test_put_cross_field_rejected_422(api_client: AsyncClient) -> None:
    # The S9 repro: a tiny total beneath a large new-card limit is refused up front — otherwise the
    # review batch would silently let the smaller total win and never show the surplus new cards.
    resp = await api_client.put(
        "/settings", json={"values": {"daily_new_limit": "100", "daily_total_limit": "1"}}
    )
    assert resp.status_code == 422
    assert (await api_client.get("/settings")).json() == {"values": {}}


async def test_put_null_removes_key(api_client: AsyncClient) -> None:
    # Write two keys, then PUT one as null to remove it (finding S10); the other is left intact.
    await api_client.put(
        "/settings", json={"values": {"discover_count": "8", "daily_total_limit": "40"}}
    )
    removed = await api_client.put("/settings", json={"values": {"discover_count": None}})
    assert removed.status_code == 200
    assert removed.json() == {"values": {"daily_total_limit": "40"}}

    # The removal is durable: a fresh GET no longer carries the key.
    assert (await api_client.get("/settings")).json() == {"values": {"daily_total_limit": "40"}}
