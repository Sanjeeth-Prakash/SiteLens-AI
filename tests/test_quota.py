from datetime import datetime, timezone
from unittest.mock import Mock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.quota import RESERVE, QuotaReached, QuotaUnavailable, reserve_analysis
from app.website import FetchedPage

URL = "https://quota-example.upstash.io/"


@pytest.fixture
def quota_env(monkeypatch):
    monkeypatch.setenv("SITELENS_DAILY_ANALYSIS_LIMIT", "10")
    monkeypatch.setenv("UPSTASH_REDIS_REST_URL", URL)
    monkeypatch.setenv("UPSTASH_REDIS_REST_TOKEN", "fixture-token")


def test_an_unconfigured_limit_skips_the_store(monkeypatch):
    monkeypatch.delenv("SITELENS_DAILY_ANALYSIS_LIMIT", raising=False)
    post = Mock()
    monkeypatch.setattr("app.quota.httpx.post", post)
    reserve_analysis()
    post.assert_not_called()


def test_reservation_uses_the_shared_counter_and_calculates_reset(quota_env, monkeypatch):
    now = datetime(2026, 11, 20, 23, 59, 57, tzinfo=timezone.utc)
    monkeypatch.setattr("app.quota.datetime", Mock(now=Mock(return_value=now)))
    replies = [httpx.Response(200, json={"result": result}, request=httpx.Request("POST", URL)) for result in (1, 0)]
    post = Mock(side_effect=replies)
    monkeypatch.setattr("app.quota.httpx.post", post)

    reserve_analysis()
    with pytest.raises(QuotaReached) as caught:
        reserve_analysis()

    assert caught.value.retry_after == 3
    for call in post.call_args_list:
        assert call.args == (httpx.URL(URL),)
        assert call.kwargs["headers"] == {"Authorization": "Bearer fixture-token"}
        assert call.kwargs["json"] == ["EVAL", RESERVE, 1, "sitelens:analysis:2026-11-20", 10]


def test_configured_limit_rejects_missing_store_credentials(quota_env, monkeypatch):
    monkeypatch.delenv("UPSTASH_REDIS_REST_TOKEN")
    post = Mock()
    monkeypatch.setattr("app.quota.httpx.post", post)
    with pytest.raises(QuotaUnavailable):
        reserve_analysis()
    post.assert_not_called()


@pytest.mark.parametrize("response", [{"error": "example"}, {"result": True}, {"result": 2}])
def test_unexpected_store_reply_does_not_admit_the_request(quota_env, monkeypatch, response):
    reply = httpx.Response(200, json=response, request=httpx.Request("POST", URL))
    monkeypatch.setattr("app.quota.httpx.post", Mock(return_value=reply))
    with pytest.raises(QuotaUnavailable):
        reserve_analysis()


def test_live_quota_error_leaves_the_example_available(quota_env, monkeypatch):
    monkeypatch.setenv("SITELENS_PROVIDER", "ollama")
    monkeypatch.setattr("app.main.fetch_page", lambda url: FetchedPage(
        url,
        b"<main>This service directory helps customers find accurate and up to date information "
        b"about the products and services the company offers to local businesses.</main>",
    ))
    reply = httpx.Response(200, json={"result": 0}, request=httpx.Request("POST", URL))
    monkeypatch.setattr("app.quota.httpx.post", Mock(return_value=reply))
    retrieve = Mock()
    monkeypatch.setattr("app.main.Ollama.retrieve", retrieve)

    with TestClient(app) as client:
        live = client.post("/link-analysis", json={"url": "https://www.example.com/"})
        assert live.status_code == 429
        assert int(live.headers["Retry-After"]) > 0
        assert client.get("/example-report").status_code == 200
    retrieve.assert_not_called()
