# Model selection and cost

Reviewed official documentation on 2026-11-19. The table uses standard uncached text rates in USD per million tokens. The generation estimates use 900 input and 900 output tokens as a planning assumption. Different tokenizers, thinking tokens, and tool fees can change the bill.

| Candidate | Input / output rate | Published capacity | Structured JSON | Estimated cost |
| --- | ---: | --- | --- | ---: |
| OpenAI GPT-6.1 Terra | $1 / $5 | 1.05M context | Yes | $0.00540 |
| Gemini 3.5 Flash-Lite | $0.30 / $2.50 | 1,048,576 input, 65,536 output | Yes | $0.00252 |
| Claude Haiku 5.5 | $0.10 / $0.50 for prompts up to 100K tokens | 1M context | Yes | $0.00054 |

Sources: [OpenAI model spec and rates](https://developers.openai.com/api/docs/models/gpt-6.1-terra), [Gemini model spec](https://aistudio.google.com/docs/models/gemini-3.5-flash-lite), [Gemini prices](https://aistudio.google.com/docs/pricing#gemini-3.5-flash-lite), [Claude prices](https://platform.claude.com/docs/en/about-claude/pricing), [Claude model capacity](https://platform.claude.com/docs/en/models/haiku-4-5/overview), and [Claude structured outputs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs).

## Recommendation

Use local Llama 3.1 for the portfolio demo. It runs on the existing Ollama setup without provider token fees. Hardware, power, and request time still matter. If a hosted option is needed, start evaluation with Claude Haiku 5.5 at the short-prompt rate and try Gemini 3.5 Flash-Lite as a fallback candidate. Select a hosted model only after comparing response validity, claim support, and end-to-end latency on the same pages. Hosted timings and accuracy have not been measured.

For an evaluation, save reviewed fixtures with a list of supported facts and absent services. Run repeated requests with the same evidence and record valid-schema rate, platform coverage, claim support, p50/p95 latency, and billed tokens. Score unsupported service claims even if the cited passage ID exists.

SiteLens already reduces generation input by cleaning HTML and retrieving a small context. If request volume grows, cache a result by URL, normalized content hash, model version, and prompt version so page and model changes invalidate old reports.
