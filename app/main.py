import os
from contextlib import contextmanager
from pathlib import Path
from threading import BoundedSemaphore

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import HttpUrl

from app.ai import InvalidModelOutput, ModelRateLimited, ModelUnavailable, Ollama
from app.competitors import compare_peers
from app.gemini import GEMINI_API, Gemini
from app.quota import QuotaReached, QuotaUnavailable, reserve_analysis
from app.schemas import Analysis, Health, LinkRequest, LinkResponse
from app.website import URLRejected, WebsiteUnavailable, extract_passages, fetch_page

app = FastAPI(title="SiteLens AI", description="Evidence-linked analysis of one public webpage.")
ROOT = Path(__file__).resolve().parents[1]
HOSTED_SLOT = BoundedSemaphore(1)
app.mount("/assets", StaticFiles(directory=ROOT / "web" / "assets"), name="assets")


@contextmanager
def analysis_model():
    provider = os.getenv("SITELENS_PROVIDER", "ollama").strip().lower()
    if provider == "ollama":
        with httpx.Client(base_url="http://127.0.0.1:11434", timeout=180, trust_env=False) as client:
            yield Ollama(client)
        return
    if provider != "gemini":
        raise ModelUnavailable("The live analysis provider is not configured.")
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise ModelUnavailable("Live analysis is not configured. You can still open the example report.")
    if not HOSTED_SLOT.acquire(blocking=False):
        raise ModelRateLimited("A live analysis is already running. Try again shortly or open the example report.")
    try:
        with httpx.Client(
            base_url=GEMINI_API,
            timeout=httpx.Timeout(60, connect=5),
            headers={"x-goog-api-key": key},
            trust_env=False,
        ) as client:
            yield Gemini(client)
    finally:
        HOSTED_SLOT.release()


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(ROOT / "web" / "index.html", headers={
        "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
    })


@app.get("/example-report", include_in_schema=False)
def example_report() -> FileResponse:
    return FileResponse(ROOT / "examples" / "response.json", media_type="application/json")


@app.get("/health")
def health() -> Health:
    return Health()


@app.post("/link-analysis")
def analyze_link(payload: LinkRequest) -> LinkResponse:
    try:
        with analysis_model() as model:
            page = fetch_page(str(payload.url))
            passages = extract_passages(page.html, page.encoding)
            reserve_analysis()
            evidence = model.retrieve(passages)
            draft, warnings = model.generate(evidence)
    except URLRejected as exc:
        raise HTTPException(422, str(exc)) from exc
    except WebsiteUnavailable as exc:
        raise HTTPException(502, str(exc)) from exc
    except (ModelUnavailable, QuotaUnavailable) as exc:
        raise HTTPException(503, str(exc)) from exc
    except QuotaReached as exc:
        raise HTTPException(429, str(exc), headers={"Retry-After": str(exc.retry_after)}) from exc
    except ModelRateLimited as exc:
        raise HTTPException(429, str(exc)) from exc
    except InvalidModelOutput as exc:
        raise HTTPException(502, str(exc)) from exc

    source_url = HttpUrl(page.url)
    return LinkResponse(
        website=payload.url,
        source_url=source_url,
        brand=draft.brand,
        analysis=Analysis(
            competitor_analysis=compare_peers(source_url),
            target_search_queries=draft.target_search_queries.as_list(),
            seo_improvements=draft.seo_improvements,
            top_services=draft.top_services,
            target_audience=draft.target_audience,
        ),
        evidence=evidence,
        warnings=warnings,
    )
