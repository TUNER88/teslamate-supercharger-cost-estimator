import json
import time

import httpx
import pytest

from suc_estimator.pricesource import fetch_prices


def _write_cache(tmp_path, payload, fetched_at=None):
    cache = tmp_path / "europe.json"
    cache.write_text(json.dumps(payload), encoding="utf-8")
    meta = tmp_path / "europe.meta.json"
    meta.write_text(
        json.dumps(
            {"fetched_at": fetched_at if fetched_at is not None else time.time(), "url": "http://example.test"}
        ),
        encoding="utf-8",
    )
    return cache, meta


def test_fresh_cache_used_without_network(monkeypatch, tmp_path):
    payload = {"stations": []}
    _write_cache(tmp_path, payload)  # fetched just now -> within TTL

    def _fail_get(*args, **kwargs):  # pragma: no cover - must not be called
        raise AssertionError("network must not be hit")

    class _FakeClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **kw):
            return _fail_get(*a, **kw)

    monkeypatch.setattr("suc_estimator.pricesource.httpx.Client", _FakeClient)
    out = fetch_prices(cache_dir=tmp_path, ttl_seconds=43_200)
    assert out == payload


def test_stale_cache_fallback_on_network_error(monkeypatch, tmp_path):
    payload = {"stations": [{"id": "stale"}]}
    # fetched_at=1000.0 -> cache far older than TTL -> would try network
    _write_cache(tmp_path, payload, fetched_at=1000.0)

    class _BrokenClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **kw):
            raise httpx.ConnectError("boom", request=httpx.Request("GET", "http://x"))

    monkeypatch.setattr("suc_estimator.pricesource.httpx.Client", _BrokenClient)
    out = fetch_prices(cache_dir=tmp_path, ttl_seconds=43_200)
    assert out == payload  # fell back to stale copy


def test_stale_cache_fallback_on_http_error(monkeypatch, tmp_path):
    payload = {"stations": [{"id": "stale"}]}
    _write_cache(tmp_path, payload, fetched_at=1000.0)

    class _BrokenClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **kw):
            req = httpx.Request("GET", "http://x")
            resp = httpx.Response(503, request=req)
            resp.raise_for_status()

    monkeypatch.setattr("suc_estimator.pricesource.httpx.Client", _BrokenClient)
    out = fetch_prices(cache_dir=tmp_path, ttl_seconds=43_200)
    assert out == payload


def test_no_cache_raises_on_network_error(monkeypatch, tmp_path):
    class _BrokenClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **kw):
            raise httpx.ConnectError("boom", request=httpx.Request("GET", "http://x"))

    monkeypatch.setattr("suc_estimator.pricesource.httpx.Client", _BrokenClient)
    with pytest.raises(httpx.ConnectError):
        fetch_prices(cache_dir=tmp_path, ttl_seconds=43_200)


def test_cache_written_on_success(monkeypatch, tmp_path):
    payload = {"stations": [{"id": "new"}]}

    class _FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    class _OkClient:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def get(self, *a, **kw):
            return _FakeResp()

    monkeypatch.setattr("suc_estimator.pricesource.httpx.Client", _OkClient)
    out = fetch_prices(cache_dir=tmp_path, ttl_seconds=43_200)
    assert out == payload
    assert (tmp_path / "europe.json").exists()
    assert (tmp_path / "europe.meta.json").exists()