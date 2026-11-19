"""Reviewed peer evidence for the FastAPI homepage demo."""

from pydantic import HttpUrl

from app.schemas import Competitor, CompetitorAnalysis


def compare_peers(url: HttpUrl) -> CompetitorAnalysis:
    if url.host != "fastapi.tiangolo.com" or url.path not in (None, "/"):
        return CompetitorAnalysis()
    return CompetitorAnalysis(
        status="reviewed_sources",
        note="These are framework alternatives, compared from their own documentation. No benchmark or market ranking was performed.",
        competitors=[
            Competitor(
                name="Django",
                strength="Includes an ORM and generated admin interface.",
                positioning="Consider for database-backed applications where the built-in administration tools matter.",
                source_url="https://docs.djangoproject.com/en/stable/intro/overview/",
            ),
            Competitor(
                name="Flask",
                strength="Provides a lightweight WSGI framework.",
                positioning="Consider when the project calls for a small WSGI foundation and separately chosen extensions.",
                source_url="https://flask.palletsprojects.com/en/stable/",
            ),
            Competitor(
                name="Litestar",
                strength="Provides an ASGI framework with dependency injection and OpenAPI support.",
                positioning="Consider as an ASGI API alternative when evaluating framework conventions and integrations.",
                source_url="https://docs.litestar.dev/latest/",
            ),
        ],
    )
