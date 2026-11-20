# How the SiteLens RAG pipeline works

Follow a request for the FastAPI homepage through the code.

## 1. Build a small evidence collection

`fetch_page()` obtains HTML from a public URL. It resolves the hostname, checks that all returned IP addresses are public, and connects to one of those checked addresses. Each redirect repeats those steps. The API exposes the final URL as `source_url` so the evidence stays tied to the page actually downloaded.

`extract_passages()` removes elements like scripts and navigation, then slices the cleaned text into chunks of up to 90 words. Each chunk gets an ID such as `page-3`. The result is a dictionary mapping IDs to original text. These IDs let the final report point back to readable evidence.

Your original Local RAG Assistant ranked whole files. SiteLens ranks passages within one page. If a paragraph describing request validation is buried in a long page, the embedding for that paragraph can capture the topic more directly than an embedding for the entire page.

## 2. Use the embedding model to retrieve passages

The application has an internal retrieval query describing what the analysis needs, including business category, services, and target users. `Ollama.retrieve()` sends both the query and passage texts to `all-minilm`. The embedding model returns one vector for each text. A vector is an ordered list of numbers representing features learned during model training.

Cosine similarity divides the vectors' dot product by the product of their lengths. With simplified two-number vectors, a query of `[1, 0]` scores `1.0` against `[1, 0]`, `0.8` against `[4, 3]`, and `0.0` against `[0, 1]`. Our code takes the highest-scoring six passages and adds the page title when available.

Embedding makes the text searchable. Python handles ranking. The page text and vectors live in memory for this request. If many users needed to query a stable collection, persistence could store the page URL, text, chunk ID, model version, and vector so later requests could reuse the index.

## 3. Use the chat model to generate an analysis

`Ollama.generate()` sends the selected text, reporting instructions, and a JSON schema to Llama 3.1. The schema is the contract for fields and types. The model uses the evidence to propose a brand profile, services, query ideas, SEO copy, and audiences.

The first live implementation asked the model for a list of five platform entries. It returned five entries all marked Google. An enum constrained each individual label but allowed repeats. The revised model uses a required property for each platform and lets Python attach the final labels. This makes coverage a property of the application code.

## 4. Validate and assess the result

Pydantic parses the generated JSON. The application checks the brand's evidence IDs and only includes service claims with valid references and an exact quotation. A human can then read the passage and check whether it supports the claim. In a test run, Llama labeled standards such as OAuth2 as services. We clarified the prompt to require an actual service offer. In the recorded run, the API omitted candidates with unverifiable quotes and reported the omission in `warnings`. The competitor section uses reviewed source links for the demo and returns an evidence gap for other pages.
