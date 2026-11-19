from typing import Annotated, Literal

from pydantic import BaseModel, Field, HttpUrl, StringConstraints

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=600)]
Platform = Literal["Google", "Facebook", "Instagram", "LinkedIn", "X"]


class LinkRequest(BaseModel):
    url: HttpUrl


class Brand(BaseModel):
    name: Text
    category: Text
    summary: Text
    evidence_ids: list[Text] = Field(min_length=1, max_length=3)


class QueryText(BaseModel):
    query: Text
    intent: Text
    audience: Text


class SearchQuery(QueryText):
    platform: Platform


class PlatformQueries(BaseModel):
    google: QueryText
    facebook: QueryText
    instagram: QueryText
    linkedin: QueryText
    x: QueryText

    def as_list(self) -> list[SearchQuery]:
        entries: list[tuple[Platform, QueryText]] = [
            ("Google", self.google), ("Facebook", self.facebook), ("Instagram", self.instagram),
            ("LinkedIn", self.linkedin), ("X", self.x),
        ]
        return [SearchQuery(platform=platform, **query.model_dump()) for platform, query in entries]


class SEOImprovements(BaseModel):
    primary_keyword: Text
    secondary_keywords: list[Text] = Field(max_length=4)
    recommended_title: Text
    meta_description: Text
    supporting_content: list[Text] = Field(max_length=4)


class Service(BaseModel):
    name: Text
    description: Text
    target_customer: Text
    benefit: Text
    evidence_ids: list[Text] = Field(min_length=1, max_length=3)
    evidence_quote: Text


class Audience(BaseModel):
    primary: list[Text] = Field(max_length=4)
    secondary: list[Text] = Field(max_length=4)
    customer_needs: list[Text] = Field(max_length=4)


class Draft(BaseModel):
    brand: Brand
    target_search_queries: PlatformQueries
    seo_improvements: SEOImprovements
    top_services: list[Service] = Field(max_length=5)
    target_audience: Audience


class Competitor(BaseModel):
    name: Text
    strength: Text
    positioning: Text
    source_url: HttpUrl


class CompetitorAnalysis(BaseModel):
    status: Literal["reviewed_sources", "insufficient_evidence"] = "insufficient_evidence"
    competitors: list[Competitor] = Field(default_factory=list)
    note: str = "No reviewed competitor sources are configured for this page."


class Analysis(BaseModel):
    competitor_analysis: CompetitorAnalysis
    target_search_queries: list[SearchQuery]
    seo_improvements: SEOImprovements
    top_services: list[Service]
    target_audience: Audience


class LinkResponse(BaseModel):
    success: Literal[True] = True
    website: HttpUrl
    brand: Brand
    analysis: Analysis
    evidence: dict[str, str]
    warnings: list[str] = Field(default_factory=list)
    interpretation: str = "Search queries, SEO copy, and audience segments are suggestions. No search volume was measured."


class Health(BaseModel):
    status: Literal["ok"] = "ok"
