# SiteLens AI

SiteLens turns one public webpage into a structured business and SEO brief. It uses local Ollama models to retrieve relevant page passages and generate a report with checkable evidence references. It is an independent portfolio project.

## Run it

Install Python 3.11+ and start Ollama. From the project directory in PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
ollama pull all-minilm
ollama pull llama3.1
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 4000
```

Open [interactive API docs](http://127.0.0.1:4000/docs), or run the request in a second terminal:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:4000/link-analysis' -Method Post -ContentType 'application/json' -Body '{"url":"https://fastapi.tiangolo.com/"}' | ConvertTo-Json -Depth 12
```

The report includes a brand profile with source IDs, a competitor comparison, five platform-specific query suggestions, SEO recommendations, evidenced services, and suggested audiences. The FastAPI homepage demo has three manually reviewed peer sources. Other supported pages report insufficient competitor evidence. SEO and queries are editorial suggestions. The app has no search-volume data.

See the [recorded live response](examples/response.json). Its text excerpts are shortened for display. The local Uvicorn and Ollama smoke test returned HTTP 200 in 12.54 seconds for this page. That is one end-to-end timing on the development machine.

## Code walkthrough

| Module | What happens |
| --- | --- |
| [`main.py`](app/main.py) | FastAPI receives and validates the request, calls the pipeline, and translates failures into HTTP status codes. |
| [`website.py`](app/website.py) | Enforces the demo's destination policy, fetches HTML, removes page boilerplate, and assigns IDs to text passages. |
| [`ai.py`](app/ai.py) | Embeds the analysis goal and passages in one Ollama batch, ranks them with cosine similarity, and asks Llama to generate a typed report from the selected evidence. |
| [`schemas.py`](app/schemas.py) | Defines the public response and model output. The model fills five named query slots. Python maps those slots to the API's platform labels. |
| [`competitors.py`](app/competitors.py) | Uses reviewed first-party documentation to compare Django, Flask, and Litestar as alternatives to FastAPI. |

See the [worked learning guide](docs/walkthrough.md) and the [model evaluation notes](docs/model-comparison.md).

## Tests and configuration

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The automated suite uses fixture HTML and simulated model responses. It checks destination validation, private DNS results, extraction, retrieval ordering, citation validation, platform coverage, and the five-section API response. The tests run without Ollama or outbound network access.

Change models with `SITELENS_CHAT_MODEL` and `SITELENS_EMBED_MODEL`. The model server is local at port 11434. A missing or failing Ollama service returns `503`. A failed page fetch or invalid model response returns `502`. A rejected URL returns `422`.

## Scope and deployment

The demo fetches one bounded HTML page from `fastapi.tiangolo.com`, `www.djangoproject.com`, or `www.python.org`. It uses HTTPS, pins the connection to a validated public IP, verifies the certificate for the requested host, and does not follow redirects. It does not run JavaScript, crawl the site, or discover competitors automatically. Evidence IDs are checked for existence. Claim support still needs human evaluation.

Use loopback for the demo. A public deployment needs authentication, rate and concurrency limits, an isolated fetch worker with restricted egress, and monitoring. This version stores passages and vectors in memory for one request.
