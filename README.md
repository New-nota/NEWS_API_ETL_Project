# NEWS_API_ETL_Project

ETL pipeline that pulls articles from NewsAPI, validates and normalizes them, then loads clean records into PostgreSQL. Two execution modes: a **worker queue** that processes search requests for web users (using each user's own encrypted NewsAPI key or the app owner's key in trial mode), and a **debug script** that dumps raw/clean payloads to disk and writes to a separate inspection table.

## What this project does

1. **extract** (`src/extract.py`) — fetches paginated articles from NewsAPI with timeout, retries, exponential backoff, and `429`/`5xx` handling.
2. **transform** (`src/transform.py`) — validates each article, normalizes text and timestamps, classifies rejection reasons and accumulates per-page statistics.
3. **load** (`src/load.py`) — upserts articles by URL into `articles`, links them to a `search_request` via `user_news`, and persists per-request stats in `request_stats`.
4. **AI summary** (`src/ai/`) — after each web/worker run, a Mistral call summarizes the loaded pocket and stores the result in `request_ai_report` (one row per `search_request_id`).
5. **worker** (`src/worker.py`) — single loop that handles two job types in priority order:
   - **Key validation** (`one_key_validation`) — atomically claims a `pending_validation` row from `users_keys`, decrypts and pings NewsAPI, then marks the key as `valid`, `invalid`, or `exhausted`.
   - **Search requests** (`one_request`) — atomically claims a `queued` row from `search_requests` (`FOR UPDATE SKIP LOCKED`), runs the pipeline, and marks the request as `success` or `failed`.
6. **per-user keys** (`src/user_news_api_key.py`) — AES-GCM encryption/decryption of NewsAPI keys stored in `users_keys`, plus live key validation against the NewsAPI `/top-headlines` endpoint.

## Repository structure

```text
project/
├── config/
│   └── config.py               # Settings dataclass loaded from .env
├── notebooks/
│   └── 01_eda.ipynb
├── src/
│   ├── __init__.py
│   ├── db.py                   # Connection, schema creation, queue claim
│   ├── extract.py              # NewsAPI fetch (web + debug variants)
│   ├── transform.py            # Validation, normalization, rejection stats
│   ├── load.py                 # Upserts and request_stats persistence
│   ├── pipeline.py             # run_debug_pipeline / run_pipeline_for_web_user
│   ├── worker.py               # Queue worker loop (key validation + search requests)
│   ├── user_news_api_key.py    # AES-GCM encryption helpers + key validation
│   └── ai/                     # Mistral-based pocket summary
│       ├── __init__.py
│       ├── client.py
│       ├── prompts.py
│       ├── report.py
│       └── schemas.py
├── tests/
│   ├── test_pipeline.py
│   ├── test_transform.py
│   └── test_ai_report.py
├── .env.example
├── DockerFile
├── docker-compose.yml
├── main.py                     # CLI entry point
├── pyproject.toml              # Ruff + pytest config
├── requirements.txt
└── requirements-dev.txt
```

> `data/raw/` and `data/clean/` are created on demand by debug runs and are gitignored.

## Environment variables

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

**Database**
- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`
- `DB_ADMIN_DB` (default `postgres`) — admin DB used to create `NEWS_DB`
- `NEWS_DB` (default `news_db`)

**NewsAPI**
- `NEWSAPI_KEY` — app owner's key; used as the fallback in CLI/debug mode and for all trial requests in worker mode
- `NEWSAPI_URL` (default `https://newsapi.org/v2/everything`)
- `NEWSAPI_DEFAULT_LANGUAGE` (default `ru`)
- `NEWSAPI_SORT_BY` (default `publishedAt`; one of `relevancy`, `popularity`, `publishedAt`)
- `NEWS_API_KEY_ENCRYPTION_SECRET` — secret used to derive the AES-GCM key for encrypting user-supplied NewsAPI keys
- `TRIAL_REQUEST_LIMIT` — max number of trial searches allowed per user (enforced at the web layer)

**AI summary (Mistral)**
- `MISTRAL_API_KEY` — required when `AI_SUMMARY_ENABLED=true`
- `MISTRAL_API_URL` (default `https://api.mistral.ai/v1/chat/completions`)
- `MISTRAL_MODEL` (default `mistral-large-latest`)
- `AI_SUMMARY_ENABLED` (default `true`) — set to `false` to skip the AI step entirely
- `AI_PROMPT_VERSION` (default `v1`) — stored alongside each report for prompt-version tracking
- `AI_PROVIDER` (default `mistral`) — provider label written to `request_ai_report.model_provider`
- `AI_REQUEST_TIMEOUT_SECONDS` (default `60`) — HTTP timeout for the AI provider call
- `AI_REPORT_MAX_ARTICLES` (default `50`) — hard cap on articles passed to the model per report

**Reliability and limits**
- `REQUEST_TIMEOUT_SECONDS`, `REQUEST_MAX_RETRIES`, `REQUEST_BACKOFF_FACTOR`, `REQUEST_MAX_BACKOFF_SECONDS`
- `REQUEST_PAGE_SIZE_MAX` (default `100`), `MAX_PAGES_PER_REQUEST` (default `50`), `NEWSAPI_MAX_TOTAL_RESULTS` (default `1000`)
- `DB_CONNECT_TIMEOUT_SECONDS`, `DB_STATEMENT_TIMEOUT_MS`

## Local run

### 1. Install

```bash
python -m venv .venv
source .venv/bin/activate        # macOS/Linux
# .venv\Scripts\activate         # Windows
pip install -r requirements.txt
```

### 2. Initialize the database and tables

```bash
python main.py --init-only
```

Creates the `news_db` database and all production tables. Add `--debug` to also create the debug table `bad_news_bears`. Alternatively, append `--bootstrap` to any run command to initialize on startup.

### 3. Web mode (single run, requires existing `app_users` and `search_requests` rows)

```bash
python main.py --keyword python --limit 20 --page_size 50 --language en --user_id 1 --search_request_id 1
```

Uses the global `NEWSAPI_KEY` from `.env`. Articles go into `articles` and are linked to the user via `user_news`; per-request stats land in `request_stats`.

### 4. Worker loop (production mode)

```bash
python main.py --worker --poll_interval 3
```

The worker processes two job types in a tight loop:
1. **Key validation** — picks a `pending_validation` key, pings NewsAPI, writes `valid`/`invalid`/`exhausted`.
2. **Search requests** — picks a `queued` request, runs the full ETL pipeline, writes `success`/`failed`.

Multiple workers can run concurrently — `FOR UPDATE SKIP LOCKED` prevents duplicate processing.

### 5. Debug mode

See the **Debug mode** section at the bottom of this README.

## Docker

The project expects an external Docker network named `news-stack-net` (shared with the web app / Postgres stack). Create it once if it doesn't exist:

```bash
docker network create news-stack-net
```

Then build and start the worker:

```bash
docker compose up --build
```

The `app` container runs `python main.py --worker --bootstrap --poll_interval 3`. Postgres must be reachable on the `news-stack-net` network as `news-postgres` (configure `DB_HOST=news-postgres` in `.env`).

## Quality checks

```bash
pip install -r requirements-dev.txt
python -m compileall .
ruff check .
pytest
bandit -r src config main.py
pip-audit
```

## Database tables

| Table | Purpose |
|---|---|
| `app_users` | Web users (Google OAuth). Includes `trial_uses` counter tracking how many free trial searches a user has consumed. |
| `users_keys` | Per-user encrypted NewsAPI keys (AES-GCM). Each key goes through a validation lifecycle: `pending_validation → validating → valid / invalid / exhausted`. |
| `search_requests` | Queue of search jobs with status (`queued`/`running`/`success`/`failed`) and `is_trial` flag. |
| `articles` | Deduplicated articles, unique by `url`. |
| `user_news` | Many-to-many link between `app_users`, `search_requests`, and `articles`. |
| `request_stats` | Per-request totals: `income_articles`, `accepted_articles`, `rejected_articles`, `reasons_counts` (JSONB), `prime_reasons` (JSONB). |
| `request_ai_report` | One Mistral-generated summary per `search_request_id` (counts, conclusions, sentiment, topics, highlight, warnings, token usage). |
| `bad_news_bears` | **Debug only** — populated by `--debug` runs. Not touched by web/worker mode. |

## Trial mode

When `search_requests.is_trial = true`, the worker uses the app owner's `NEWSAPI_KEY` from config instead of looking up the user's personal key from `users_keys`. The `trial_uses` counter on `app_users` is managed by the web layer; the ETL worker only checks the flag.

## Key validation flow

When a user registers a NewsAPI key via the web app, a row is inserted into `users_keys` with `status = 'pending_validation'`. On each worker loop tick, `one_key_validation()` picks one such row and:

1. Decrypts the key from AES-GCM ciphertext.
2. Sends a minimal request to `https://newsapi.org/v2/top-headlines`.
3. Sets the status:
   - `valid` — HTTP 200
   - `invalid` — HTTP 401 with any code other than `apiKeyExhausted`
   - `exhausted` — HTTP 401 with `code = "apiKeyExhausted"`
4. On network/crypto error the status is reset to `pending_validation` for retry.

Only keys with `status = 'valid'` are used by search requests.

## AI summary flow

After `run_pipeline_for_web_user` finishes loading and persists `request_stats`, it calls `_generate_and_store_ai_summary`, which:

1. Reads the loaded pocket from DB: `articles JOIN user_news WHERE search_request_id = ?`.
2. Truncates the article list to `AI_REPORT_MAX_ARTICLES` (default 50) before calling the model.
3. Calls Mistral (`response_format: json_object`) with the system prompt in `src/ai/prompts.py`.
4. Validates and normalizes the JSON response (sentiment percentages re-normalized to sum to 100; `sentiment_label` forced to match the dominant key; `highlight.url` replaced with a real article URL if the model invented one).
5. Upserts a row in `request_ai_report` keyed by `search_request_id` with `status='success'`.

The AI step is **best-effort**: any Mistral or DB error is logged but does not fail the search request. On failure, a `request_ai_report` row with `status='failed'` is written so the frontend can distinguish "AI failed" from "not yet generated." To skip AI entirely, set `AI_SUMMARY_ENABLED=false`.

Stored summary fields:
- `status` (`success` | `failed`) and `error_text`
- `news_count` — articles linked to this request (capped at `AI_REPORT_MAX_ARTICLES`)
- `summary` — 1-2 sentence neutral overview
- `main_conclusions` (JSONB) — exactly 3 short conclusions
- `sentiment_label` (`positive` | `negative` | `neutral`) and `sentiment_score`
- `sentiment_distribution` (JSONB) — `{positive, negative, neutral}` summing to 100
- `main_topics` (JSONB) — 1 to 3 topics in order of importance
- `highlight` (JSONB) — `{url, title, author?, description?, reason}`
- `data_quality_warnings` (JSONB)
- `model_provider`, `model_name`, `promt_version` (DB column name), `input_tokens`, `output_tokens`, `total_tokens`

## Reliability and safety guarantees

- HTTP retries with backoff and `Retry-After` handling (`429`, `5xx`).
- Strict input validation in transform layer; rejected records counted by reason in `request_stats`.
- Idempotent article upsert on `url`; idempotent `user_news` insert on `(user_id, article_id, search_request_id)`.
- Atomic worker dequeue (`FOR UPDATE SKIP LOCKED`), safe for multiple worker processes.
- DB connect and statement timeouts are configurable.
- NewsAPI keys are stored encrypted (AES-GCM) and only decrypted in-memory for the duration of a single operation.

## Notes

- `.env`, `.venv`, `__pycache__`, and generated files under `data/raw` and `data/clean` are gitignored.
- Never commit real keys — only `.env.example` should be in git.

## Troubleshooting

- **`Database 'news_db' does not exist`** — run `python main.py --init-only` once, or add `--bootstrap` to your run command.
- **`password authentication failed`** — verify `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`.
- **`User has no NEWSAPI key yet`** (worker mode, non-trial) — the user has no row in `users_keys` with `service = 'news_api'`. Use the web flow to upload their key.
- **`User has no NEWSAPI key yet`** (worker mode, trial) — `NEWSAPI_KEY` is empty in `.env`.
- **`NEWSAPI_KEY contains a placeholder value`** — replace `YOUR_REAL_NEWSAPI_KEY` in `.env` (needed for CLI/debug mode and trial requests).
- **Key stuck in `pending_validation`** — check that `NEWS_API_KEY_ENCRYPTION_SECRET` matches the value used when the key was encrypted; a mismatch causes a crypto error and the status is reset to `pending_validation`.

---

## Debug mode (`--debug`)

The `--debug` flag turns `main.py` into a pipeline-inspection script. Use it to examine exactly what NewsAPI returned, what the transform layer kept or rejected, and why — without touching any production tables.

```bash
python main.py --debug --keyword python --limit 20 --page_size 50 --language en
```

What it does, page by page:

1. **Extract** — calls NewsAPI with `NEWSAPI_KEY` from `.env` and writes the raw payload to:
   ```
   data/raw/<UTC-timestamp>_<sanitized-keyword>_page_<N>.json
   ```
2. **Transform** — runs the same validation/normalization as production and writes:
   ```
   data/clean/cleaned_<keyword>_page_<N>_<timestamp>.json   # accepted articles
   data/clean/stats/stats_<keyword>_page_<N>_<timestamp>.json
   ```
3. **Load** — inserts cleaned articles into `bad_news_bears` with `ON CONFLICT (url) DO NOTHING`.

Pagination follows the same `--limit` / `--page_size` / `MAX_PAGES_PER_REQUEST` rules as the production pipeline.

Use it to:
- Verify NewsAPI responses for a new keyword/language combination.
- Reproduce a transform-layer rejection without re-hitting the API (re-run transform against saved `data/raw/*.json`).
- Compare `stats_*.json` across runs when tuning validation rules.
- Sanity-check the SQL load path on a throwaway table before touching `articles`.
