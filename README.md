# Grounded document assistant — proof of concept

**Answers only from your documents, shows the source, and says "I couldn't find this" when the answer isn't there.**

Most chatbots fail the same way: they always answer. For a business that means a customer gets a confident wrong price, and nobody notices until it costs money. This demo is the opposite — a small, inspectable pipeline that refuses instead of guessing, and points to the paragraph it used.

Public repo version of `README.md`. The internal Russian notes stay in the vault.

## Verified output

Real run, `python rag.py docs_en "…"`, no API key, no network:

| Question | Answer |
|---|---|
| How much is a boiler service? | Annual boiler service — £85. Includes flue check, combustion reading, and a written service record. Takes about 45 minutes. |
| Do you require a deposit? | No. We never ask for a deposit. The customer pays after the work is done and checked. |
| Can you install a heat pump? | No. We do not install heat pumps. We service and repair gas boilers only. |
| Do you cover Leeds? | We cover Manchester and everything within 25 miles of the city centre… Leeds and Liverpool are outside our area. |
| Do you do solar panels? | I couldn't find this in the documents. Passing it to a human. |

The last row is the point. The demo corpus is a fictional heating company (`docs_en/`, in English). The same code runs on a Russian corpus (`docs/`) — the refusal message follows the language of the question.

## How to run

```bash
python -m pip install numpy
python rag.py docs_en "How much is a boiler service?"
```

Python 3.10+. No services, no keys, no network. Optional: set `OPENAI_API_KEY` and the answer is generated strictly from the retrieved fragments, with the source required.

## How it works

1. **Load** — `.txt`, `.md`, `.docx` (docx includes tables: prices usually live there).
2. **Chunk** — paragraphs are grouped into blocks of about 60 words. A markdown heading always starts a new block: a question and its answer have to stay in one chunk, otherwise the answer to "how much" arrives from the warranty section next door.
3. **Index** — TF-IDF over tokens, cosine similarity. Words are truncated to 6 characters so `invoice`/`invoices` and Russian inflections match. Stopwords are dropped — otherwise "do you have…" matches "have" everywhere.
4. **Retrieve** — top-k fragments plus a score threshold (0.18). Below it, the assistant refuses.
5. **Answer** — with an API key: a model writes the answer from the retrieved fragments only. Without: the closest paragraph is returned, with the markdown heading stripped.

## Design decisions worth defending

- **Refusal is a feature.** A threshold tuned to decline beats a model that hallucinates a price list.
- **Sources in the output.** Every answer carries file and paragraph position, so a support manager can check it in seconds.
- **Headings are boundaries.** A cheap rule that fixed real wrong answers (verified above).
- **Extractive mode by default.** The demo has to be inspectable: you can see exactly which paragraph was used, with no model in the loop.

## Tests

Three suites, all runnable offline:

```bash
python test-rag.py              # 13 questions against the Python pipeline, both corpora
node test-demo-core.mjs         # 6 questions against the in-browser demo logic
node test-demo-adversarial.mjs  # 14 questions, including the ones that break naive retrieval
```

The adversarial suite is the interesting one. It caught two real bugs that the six polite questions missed:

- **"Are you Gas Safe registered?"** was answered with the CP12 price, because only `gas` and `safe` matched and the unknown word `registered` was ignored entirely. Fixed by penalising query words that do not exist in the corpus.
- **"Can I pay by card?"** was refused, because truncating words to six letters turned `payment` into `paymen` against `pay`. Fixed with a light suffix stemmer.

Result after the fixes: 6/6, 14/14 and 13/13, including four honest refusals (phone number, finance, Gas Safe, washing machines).

## Limitations

- TF-IDF does not understand synonyms: `deposit` and `retainer` are different words to it.
- No reranking, so a long document with repeated vocabulary will surface near-duplicates.
- The extractive mode returns a paragraph, not a composed sentence.

## What a production build adds

- Embeddings and a vector store (OpenAI or local) plus a rerank step over the top 20 fragments.
- A prompt tuned per client: tone, form of address, and what to do when the answer is missing.
- Logging to SQLite: question, retrieved chunks, answer, confidence — so you can see what it gets wrong.
- Channels: Telegram, website widget, Slack.

## Files

- `rag.py` — the pipeline (single file, no framework).
- `docs_en/` — English demo corpus: price list and FAQ for a fictional heating company.
- `docs/` — Russian demo corpus: same idea, a fictional repair workshop.
