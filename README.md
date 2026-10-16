# Market Research Agent — live research and evaluation

Research financial news and macro releases with cited web sources, optionally alongside validated Binance prices. Inspect the answer, sources, failures, usage and replay record.

**Current phase: live research.** Normal CLI/API/browser requests default to live + OpenAI GPT-6 Astra + hosted web search. The 20-case synthetic baseline is retained only as an explicit regression tool. Real-model answer accuracy has not been measured: the current server has no OpenAI API key.

The app uses a bounded Python workflow and OpenAI-hosted search/read decisions. It does not implement a general agent loop. Independent portfolio project; not affiliated with Binance.

## Start

Python 3.10+ is declared; current verification uses Python 3.13. From this checkout:

```zsh
python3 -m venv .venv
.venv/bin/python -m pip install .
read -rs "OPENAI_API_KEY?OpenAI API key: "
export OPENAI_API_KEY
PYTHONPATH=src .venv/bin/python -m market_agent serve
```

Open [the console](http://127.0.0.1:8000). Start the server in the same terminal where you exported the key. An existing server does not inherit later environment changes. Use `PYTHONPATH=src` after source edits; a normal package installation copies the package. API requests incur model and search charges. The server binds to loopback; public multi-user deployment is outside this version.

The UI checks `/api/status` before research/evaluation. A stale backend contract produces a restart instruction. Assets revalidate their cache. [Connection status and the old `extra_forbidden: web` error](docs/integration-status.md).

## Research

```sh
PYTHONPATH=src .venv/bin/python -m market_agent research 'Find recent bitcoin news and official US inflation releases; separate reported facts from interpretations.'
PYTHONPATH=src .venv/bin/python -m market_agent research '최근 Fed 금리 결정과 BLS 물가 발표를 공식 자료로 조사해줘.'
```

The model follows the question's language, or an explicit requested output language. The interface and technical error messages are still largely Korean. Provider URL annotations become clickable citations. Citation metadata is not an article excerpt; full article crawling, independent claim verification and automatic publication-date filtering are not implemented.

A bounded price-only request uses `--no-web`. Supported prices are BTCUSDT, ETHUSDT and BNBUSDT over one or seven completed UTC daily candles:

```sh
PYTHONPATH=src .venv/bin/python -m market_agent research 'BTC ETH BNB 7d' --no-web --planner ollama
PYTHONPATH=src .venv/bin/python -m market_agent replay RUN_ID
```

Prices come from Binance, not a language model. Python computes `(last_close / first_open - 1) * 100` using original decimal strings and 40-digit precision. Windows use the same `[start, end)` UTC interval. Malformed/missing/incomplete candles fail; successful symbols survive other failures. Price co-movement and cited articles do not establish causality.

## Evaluate real research

```sh
PYTHONPATH=src .venv/bin/python -m market_agent evaluate --limit 2 --output .market-agent/pilot-two.json
PYTHONPATH=src .venv/bin/python -m market_agent evaluate --limit 12 --output .market-agent/pilot-full.json
```

This performs actual Astra web research. The authored pilot has 12 Korean/English questions in **six event groups**, based on original Fed, BLS, BEA and SEC releases. It covers units, reference periods, initial estimates versus revisions, misinformation timelines and causal abstention. It is not held out and does not measure breaking-news freshness. [Selection rationale, external alternatives and grading rubric](docs/live-research-evaluation.md).

Reports include operational completion, reference URL coverage, raw answers and sources, model tokens, elapsed time and API cost limits. **URL coverage is not answer accuracy.** Semantic labels remain `null` until reviewed. Each run is saved and the aggregate JSON/Markdown is checkpointed after every question. Provider access/rate-limit errors stop the remaining batch.

The companion `.reviews.json` binds human labels to the report hash and run IDs. Fill reviewer, evidence-based notes and the four boolean labels, then:

```sh
PYTHONPATH=src .venv/bin/python -m market_agent score .market-agent/pilot-full.json .market-agent/pilot-full.reviews.json --output .market-agent/pilot-scored.json
```

The full-set accuracy stays unknown until all selected cases are executed and reviewed. Reviewed reports cannot be overwritten by another benchmark run. Optional `--repeats 3` repeats the selected questions; repeated and paired questions are correlated, not extra independent events. Qwen has no shared web-search integration yet, so these are not a fair Astra-versus-Qwen research comparison.

## Verification and retained regression

**90 unit/integration tests pass.** They test the implementation with fixtures, not live-model quality. The archived baseline still passes 20/20 development cases:

```sh
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
PYTHONPATH=src .venv/bin/python -m market_agent regression --output .market-agent/regression.json
```

Local archived document search now uses **NLTK `wordpunct_tokenize` and `rank_bm25.BM25Okapi`**, rather than an in-house tokenizer/BM25 formula. This is separate from hosted live web search. LangChain wrappers do not make remote searches faster by themselves. [Retrieval and orchestration decision](docs/02-tools.md).

Web output is capped at **4,096 generated tokens**, including non-visible output. This is an initial application budget, not Astra's 128,000-token model limit or an experimentally optimal setting. [Token and tool budgets](docs/web-research.md).

[Product contract](docs/product-spec.md) · [Architecture](docs/implementation-plan.md) · [Historical Qwen measurements](docs/metrics-and-model-comparison.md) · [Initial validation archive](docs/validation.md)

## Provenance and storage

The new workflow, console, evaluation harness and tests are AI-assisted. Existing model-call and schema work originated in the owner's repository. [Development provenance](docs/development.md).

Run records live in `.market-agent/`, ignored by Git. Headers and reasoning text are excluded, but questions and observable answers remain in local records. Replay consumes frozen HTTP responses with exact method/URL/body/order matching and no network fallback. A matching replay proves repeatability of the recorded workflow, not current article availability or factual truth.
