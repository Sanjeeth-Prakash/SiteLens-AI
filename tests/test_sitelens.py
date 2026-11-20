import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.ai import InvalidModelOutput, Ollama
from app.main import app
from app.website import FetchedPage, URLRejected, WebsiteUnavailable, extract_passages, fetch_page

HTML = b"""
<title>Example Web Co</title>
<main><h1>Website design</h1><p>Our team designs accessible websites for small businesses.
We offer discovery workshops and help clients publish and maintain clear, useful websites.</p>
<script>script-only</script><nav>navigation-only</nav></main>
"""
PLATFORMS = ("Google", "Facebook", "Instagram", "LinkedIn", "X")


def draft_response() -> dict:
    return {
        "brand": {"name": "Example Web Co", "category": "Web design", "summary": "Designs small-business websites.", "evidence_ids": ["page-1"]},
        "target_search_queries": {
            platform.lower(): {"query": "small business web design", "intent": "Find services", "audience": "Business owners"}
            for platform in PLATFORMS
        },
        "seo_improvements": {
            "primary_keyword": "web design", "secondary_keywords": [], "recommended_title": "Small Business Web Design",
            "meta_description": "Design services for small businesses.", "supporting_content": ["Design process overview"],
        },
        "top_services": [{
            "name": "Web design", "description": "Designs accessible websites.", "target_customer": "Small businesses",
            "benefit": "Publish a useful site", "evidence_ids": ["page-1"], "evidence_quote": "designs accessible websites",
        }],
        "target_audience": {"primary": ["Small businesses"], "secondary": [], "customer_needs": ["A clear website"]},
    }


def test_extracts_metadata_and_discards_boilerplate():
    passages = extract_passages(HTML)
    assert passages["page-title"] == "Example Web Co"
    assert "accessible websites" in passages["page-1"]
    assert "script-only" not in str(passages)
    assert "navigation-only" not in str(passages)
    with pytest.raises(WebsiteUnavailable):
        extract_passages(b"<main>Empty</main>")


@pytest.mark.parametrize("url", [
    "https://127.0.0.1/",
    "http://169.254.169.254/",
    "https://[::1]/",
    "http://intranet.local/",
    "https://www.python.org:8443/",
    "https://user@www.python.org/",
])
def test_rejects_disallowed_destinations(url):
    with pytest.raises(URLRejected):
        fetch_page(url)


def test_rejects_nonpublic_dns_answer(monkeypatch):
    monkeypatch.setattr("app.website.socket.getaddrinfo", lambda *args, **kwargs: [
        (None, None, None, None, ("127.0.0.1", 443)),
    ])
    with pytest.raises(URLRejected, match="public"):
        fetch_page("https://www.python.org/")


def test_retrieval_keeps_six_closest_passages_and_metadata():
    def embed(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/embed"
        inputs = json.loads(request.content)["input"]
        assert len(inputs) == 9
        return httpx.Response(200, json={"embeddings": [[1, 0], *[[n, 8 - n] for n in range(8)]]})

    passages = {"page-title": "example", **{f"page-{n}": str(n) for n in range(8)}}
    with httpx.Client(base_url="http://localhost", transport=httpx.MockTransport(embed)) as client:
        result = Ollama(client).retrieve(passages)
    assert set(result) == {"page-title", *(f"page-{n}" for n in range(2, 8))}


@pytest.mark.parametrize("problem", ["invented_citation", "missing_platform"])
def test_rejects_invalid_output(problem, monkeypatch):
    draft = draft_response()
    if problem == "invented_citation":
        draft["brand"]["evidence_ids"] = ["never-retrieved"]
    else:
        del draft["target_search_queries"]["x"]
    monkeypatch.setattr(Ollama, "post", lambda *args: {"message": {"content": json.dumps(draft)}})
    with pytest.raises(InvalidModelOutput), httpx.Client() as client:
        Ollama(client).generate({"page-1": "evidence"})


def test_omits_service_when_its_quote_is_absent(monkeypatch):
    monkeypatch.setattr(Ollama, "post", lambda *args: {"message": {"content": json.dumps(draft_response())}})
    with httpx.Client() as client:
        draft, warnings = Ollama(client).generate({"page-1": "evidence"})
    assert draft.top_services == []
    assert len(warnings) == 1


def test_endpoint_returns_five_sections_and_reviewed_peers(monkeypatch):
    monkeypatch.setattr(
        "app.main.fetch_page",
        lambda url: FetchedPage(url.replace("http://", "https://"), HTML),
    )

    def post(self, path, payload):
        if path == "/api/embed":
            return {"embeddings": [[1.0, 0.0]] * len(payload["input"])}
        assert path == "/api/chat"
        assert payload["format"]["type"] == "object"
        return {"message": {"content": json.dumps(draft_response())}}

    monkeypatch.setattr(Ollama, "post", post)
    with TestClient(app) as client:
        result = client.post("/link-analysis", json={"url": "http://fastapi.tiangolo.com/"})
        assert result.status_code == 200
        invalid = client.post("/link-analysis", json={"url": "nope"})
        assert invalid.status_code == 422
        no_peers = client.post("/link-analysis", json={"url": "https://www.python.org/"})
    report = result.json()
    assert report["website"] == "http://fastapi.tiangolo.com/"
    assert report["source_url"] == "https://fastapi.tiangolo.com/"
    assert set(report["analysis"]) == {
        "competitor_analysis", "target_search_queries", "seo_improvements", "top_services", "target_audience",
    }
    assert len(report["analysis"]["competitor_analysis"]["competitors"]) == 3
    assert tuple(item["platform"] for item in report["analysis"]["target_search_queries"]) == PLATFORMS
    assert report["analysis"]["top_services"][0]["name"] == "Web design"
    assert report["warnings"] == []
    assert report["evidence"]["page-1"].startswith("Website design")
    assert no_peers.json()["analysis"]["competitor_analysis"]["status"] == "insufficient_evidence"


def test_browser_assets_and_recorded_example_do_not_need_a_key(monkeypatch):
    monkeypatch.setenv("SITELENS_PROVIDER", "gemini")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    with TestClient(app) as client:
        page = client.get("/")
        assert page.status_code == 200
        assert "View example report" in page.text
        assert "default-src 'self'" in page.headers["content-security-policy"]
        assert client.get("/assets/site.js").status_code == 200
        assert client.get("/assets/site.css").status_code == 200
        assert client.get("/example-report").json()["brand"]["name"] == "FastAPI"
        live = client.post("/link-analysis", json={"url": "https://fastapi.tiangolo.com/"})
    assert live.status_code == 503
    assert "example report" in live.json()["detail"]


def test_gemini_builds_a_report_without_ollama(monkeypatch):
    monkeypatch.setenv("SITELENS_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "fixture-key")
    monkeypatch.setattr("app.main.fetch_page", lambda url: FetchedPage(url, HTML))
    real_client = httpx.Client
    calls = []

    def fake_gemini(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "generativelanguage.googleapis.com"
        assert request.headers["x-goog-api-key"] == "fixture-key"
        calls.append(request.url.path)
        payload = json.loads(request.content)
        if request.url.path.endswith(":batchEmbedContents"):
            assert payload["requests"][0]["content"]["parts"][0]["text"].startswith("task: search result")
            assert len(payload["requests"]) == 2
            return httpx.Response(200, json={"embeddings": [{"values": [1.0, 0.0]}] * 2})
        assert payload["generationConfig"]["responseJsonSchema"]["type"] == "object"
        assert "page-1" in payload["contents"][0]["parts"][0]["text"]
        return httpx.Response(200, json={"candidates": [{
            "finishReason": "STOP",
            "content": {"parts": [{"text": "ignored", "thought": True}, {"text": json.dumps(draft_response())}]},
        }]})

    monkeypatch.setattr("app.main.httpx.Client", lambda **kwargs: real_client(
        transport=httpx.MockTransport(fake_gemini), **kwargs,
    ))
    with TestClient(app) as client:
        result = client.post("/link-analysis", json={"url": "https://school.example/"})
    assert result.status_code == 200
    assert [call.split(":")[-1] for call in calls] == ["batchEmbedContents", "generateContent"]
    assert result.json()["analysis"]["top_services"][0]["name"] == "Web design"
    assert "fixture-key" not in result.text


def test_gemini_quota_error_keeps_the_example_available(monkeypatch):
    monkeypatch.setenv("SITELENS_PROVIDER", "gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "fixture-key")
    monkeypatch.setattr("app.main.fetch_page", lambda url: FetchedPage(url, HTML))
    real_client = httpx.Client
    calls = []

    def quota_exhausted(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(429)

    monkeypatch.setattr("app.main.httpx.Client", lambda **kwargs: real_client(
        transport=httpx.MockTransport(quota_exhausted), **kwargs,
    ))
    with TestClient(app) as client:
        for _ in range(2):
            response = client.post("/link-analysis", json={"url": "https://school.example/"})
            assert response.status_code == 429
            assert "quota" in response.json()["detail"]
        assert client.get("/example-report").status_code == 200
    assert len(calls) == 2
