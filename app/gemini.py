"""The hosted Gemini adapter. Page text is the only evidence sent to Google."""

import json
import os
from urllib.parse import quote

import httpx

from app.ai import InvalidModelOutput, ModelHTTPClient, SYSTEM_PROMPT
from app.schemas import Draft

GEMINI_API = "https://generativelanguage.googleapis.com"


class Gemini(ModelHTTPClient):
    label = "Gemini"
    unavailable = "The hosted AI provider is unavailable. Try again later or open the example report."

    def __init__(self, client: httpx.Client):
        super().__init__(client)
        self.chat_model = os.getenv("SITELENS_GEMINI_CHAT_MODEL", "gemini-3.5-flash-lite")
        self.embedding_model = os.getenv("SITELENS_GEMINI_EMBED_MODEL", "gemini-embedding-2")

    def embed(self, query: str, documents: list[str]) -> list[list[float]]:
        model = f"models/{self.embedding_model}"
        texts = [f"task: search result | query: {query}", *(f"title: none | text: {doc}" for doc in documents)]
        requests = [
            {"model": model, "content": {"parts": [{"text": text}]}, "outputDimensionality": 768}
            for text in texts
        ]
        raw = self.post(f"/v1beta/models/{quote(self.embedding_model, safe='')}:batchEmbedContents", {
            "requests": requests,
        })
        try:
            return [item["values"] for item in raw["embeddings"]]
        except (KeyError, TypeError) as exc:
            raise InvalidModelOutput("Gemini did not return the requested embeddings.") from exc

    def draft_json(self, evidence: dict[str, str]) -> str:
        raw = self.post(f"/v1beta/models/{quote(self.chat_model, safe='')}:generateContent", {
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "contents": [{"role": "user", "parts": [{"text": json.dumps({"website_evidence": evidence}, ensure_ascii=False)}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": Draft.model_json_schema(),
                "maxOutputTokens": 4096,
            },
        })
        try:
            candidate = raw["candidates"][0]
            if candidate.get("finishReason") not in (None, "STOP"):
                raise InvalidModelOutput("Gemini could not complete the report draft.")
            return "".join(
                part.get("text", "") for part in candidate["content"]["parts"] if not part.get("thought")
            )
        except (IndexError, KeyError, TypeError, AttributeError) as exc:
            raise InvalidModelOutput("Gemini did not return a report draft.") from exc
