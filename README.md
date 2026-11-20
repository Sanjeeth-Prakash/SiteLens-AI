# SiteLens AI

SiteLens turns one public webpage into a structured business and SEO brief with clickable evidence. The FastAPI app serves both the browser interface and the analysis endpoint. Run the AI with local Ollama or a hosted Gemini API key.

## Run it

Install Python 3.11+ and start Ollama. From the project directory in PowerShell:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
ollama pull all-minilm
ollama pull llama3.1
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 4000
```

Open [SiteLens](http://127.0.0.1:4000/) and paste a public URL. **View example report** opens a recorded analysis without a model call. Use the [interactive API docs](http://127.0.0.1:4000/docs) or a second terminal to call the API directly:

```powershell
Invoke-RestMethod -Uri 'http://127.0.0.1:4000/link-analysis' -Method Post -ContentType 'application/json' -Body '{"url":"https://fastapi.tiangolo.com/"}' | ConvertTo-Json -Depth 12
```

The report includes a brand profile with source IDs, a competitor comparison, five platform-specific query suggestions, SEO recommendations, evidenced services, and suggested audiences. The FastAPI homepage demo has three manually reviewed peer sources. Other supported pages report insufficient competitor evidence. SEO and queries are editorial suggestions. The app has no search-volume data.

The response includes both `website`, the requested URL, and `source_url`, the public page fetched after redirects. The evidence comes from that final page.

See the [recorded live response](examples/response.json). Its text excerpts are shortened for display. The local Uvicorn and Ollama smoke test returned HTTP 200 in 12.54 seconds for this page. That is one end-to-end timing on the development machine.

## Code walkthrough

| Module | What happens |
| --- | --- |
| [`main.py`](app/main.py) | FastAPI receives and validates the request, calls the pipeline, and translates failures into HTTP status codes. |
| [`website.py`](app/website.py) | Checks public destinations and redirects, fetches bounded HTML, removes page boilerplate, and assigns IDs to text passages. |
| [`ai.py`](app/ai.py) | Embeds the analysis goal and passages in one Ollama batch, ranks them with cosine similarity, and asks Llama to generate a typed report from the selected evidence. |
| [`gemini.py`](app/gemini.py) | Uses Google's hosted embedding and structured generation endpoints while reusing the same retrieval and evidence checks. |
| [`schemas.py`](app/schemas.py) | Defines the public response and model output. The model fills five named query slots. Python maps those slots to the API's platform labels. |
| [`competitors.py`](app/competitors.py) | Uses reviewed first-party documentation to compare Django, Flask, and Litestar as alternatives to FastAPI. |
| [`web/`](web/) | Browser interface for submitting a URL, opening evidence, showing a recorded report, and downloading the JSON. |

See the [worked learning guide](docs/walkthrough.md) and the [model evaluation notes](docs/model-comparison.md).

## Tests and configuration

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

The automated suite uses fixture HTML, fake network responses, and simulated model replies. It checks public redirects, blocked destinations, IP pinning, HTML size and encoding, extraction, retrieval ordering, citation validation, platform coverage, and the five-section API response. The tests run without Ollama or outbound network access.

Change models with `SITELENS_CHAT_MODEL` and `SITELENS_EMBED_MODEL`. The model server is local at port 11434. A missing or failing Ollama service returns `503`. A failed page fetch or invalid model response returns `502`. A rejected URL returns `422`.

## Hosted model mode

Get a free-tier key in [Google AI Studio](https://aistudio.google.com/apikey). Keep the key in the server environment. For a local PowerShell session:

```powershell
$env:SITELENS_PROVIDER = 'gemini'
$env:GEMINI_API_KEY = [System.Net.NetworkCredential]::new('', (Read-Host 'Gemini API key' -AsSecureString)).Password
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 4000
```

Gemini mode uses `gemini-embedding-2` and `gemini-3.5-flash-lite` by default. Override them with `SITELENS_GEMINI_EMBED_MODEL` and `SITELENS_GEMINI_CHAT_MODEL` if needed. It allows one live analysis at a time per process and returns `429` when busy or when the provider rejects a request for quota reasons. Visitors can still view the recorded example. Gemini receives the public webpage excerpts used for retrieval and generation. Consult [Google's free-tier data terms](https://aistudio.google.com/docs/pricing) before enabling cloud analysis.

## Scope and deployment

SiteLens accepts public HTTP and HTTPS URLs on ports 80 and 443. It re-checks every redirect, rejects private and other non-public destinations, connects to a validated IP, and verifies the original hostname's certificate on HTTPS. It follows at most four redirects and limits the downloaded and decoded HTML to 1 MB. Websites that require authentication, block automated fetching, or only render content with JavaScript may return an error or have too little readable text. The report covers one page. Evidence IDs identify retrieved passages, and claim support still needs human evaluation.

Use loopback for local development. A hosted demo can use one Python web service for both the frontend and API, with `pip install -r requirements.txt` as its build command and `uvicorn app.main:app --host 0.0.0.0 --port $PORT` as its start command. Set the Gemini environment variables in the host's private settings. Before exposing arbitrary URL analysis publicly, put it behind an access or rate policy and run the fetch worker with restricted network egress. This version stores passages and vectors in memory for one request.
