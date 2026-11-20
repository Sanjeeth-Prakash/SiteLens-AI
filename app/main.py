import httpx
from fastapi import FastAPI, HTTPException
from pydantic import HttpUrl

from app.ai import InvalidModelOutput, ModelUnavailable, Ollama
from app.competitors import compare_peers
from app.schemas import Analysis, Health, LinkRequest, LinkResponse
from app.website import URLRejected, WebsiteUnavailable, extract_passages, fetch_page

app = FastAPI(title="SiteLens AI", description="Evidence-linked analysis of one public webpage.")


@app.get("/health")
def health() -> Health:
    return Health()


@app.post("/link-analysis")
def analyze_link(payload: LinkRequest) -> LinkResponse:
    try:
        page = fetch_page(str(payload.url))
        passages = extract_passages(page.html, page.encoding)
        with httpx.Client(base_url="http://127.0.0.1:11434", timeout=180, trust_env=False) as client:
            model = Ollama(client)
            evidence = model.retrieve(passages)
            draft, warnings = model.generate(evidence)
    except URLRejected as exc:
        raise HTTPException(422, str(exc)) from exc
    except WebsiteUnavailable as exc:
        raise HTTPException(502, str(exc)) from exc
    except ModelUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
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
