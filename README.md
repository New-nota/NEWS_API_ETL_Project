# NEWS_API_ETL_Project

ETL pipeline that pulls articles from NewsAPI, validates and normalizes them, then loads clean records into PostgreSQL. Two execution modes are supported: a **worker queue** that processes search requests for web users (using each user's own encrypted NewsAPI key), and a **debug script** that dumps raw/clean payloads to disk and writes to a separate inspection table.

## What this project does
1. **extract** (`src/extract.py`) — fetches paginated articles from NewsAPI with timeout, retries, exponential backoff, and `429`/`5xx` handling.
2. **transform** (`src/transform.py`) — validates each article, normalizes text and timestamps, classifies rejection reasons and accumulates per-page statistics.
3. **load** (`src/load.py`) — upserts articles by URL into `articles`, links them to a `search_request` via `user_news`, and persists per-request stats in `request_stats`.
4. **AI summary** (`src/ai/`) — after each web/worker run, a Mistral call summarizes the loaded pocket and stores the result in `request_ai_report` (one row per `search_request_id`).
5. **worker** (`src/worker.py`) — atomically claims `queued` rows from `search_requests` (`FOR UPDATE SKIP LOCKED`), decrypts the user's NewsAPI key from `users_keys`, runs the pipeline, and marks the request as `success` or `failed`.
6. **per-user keys** (`src/user_news_api_key.py`) — AES-GCM encryption/decryption of NewsAPI keys stored in the `users_keys` table.

## Repository structure
```text
project/
├── config/
│   └── config.py               # Settings dataclass loaded from .env
├── data/
│   ├── raw/                    # Debug-mode raw NewsAPI payloads (JSON per page)
│   └── clean/
│       ├── cleaned_*.json      # Debug-mode normalized articles
│       └── stats/              # Debug-mode per-page transform stats
├── notebooks/
│   └── 01_eda.ipynb
├── src/
│   ├── __init__.py
│   ├── db.py                   # Connection, schema creation, queue claim
│   ├── extract.py              # NewsAPI fetch (web + debug variants)
│   ├── transform.py            # Validation, normalization, rejection stats
│   ├── load.py                 # Upserts and request_stats persistence
│   ├── pipeline.py             # run_debug_pipeline / run_pipeline_for_web_user
│   ├── worker.py               # Queue worker loop
│   ├── user_news_api_key.py    # AES-GCM key encryption helpers
│   └── ai/                     # Mistral-based pocket summary
│       ├── __init__.py
│       ├── client.py
│       ├── prompts.py
│       ├── report.py
│       └── schemas.py
├── tests/
│   ├── test_pipeline.py
│   └── test_transform.py
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── main.py                     # CLI entry point
├── pyproject.toml              # Ruff + pytest config
├── requirements.txt
└── requirements-dev.txt
```

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
- `NEWSAPI_KEY` — used as the fallback key in CLI/debug mode (worker mode reads each user's key from `users_keys` instead)
- `NEWSAPI_URL` (default `https://newsapi.org/v2/everything`)
- `NEWSAPI_DEFAULT_LANGUAGE` (default `ru`)
- `NEWSAPI_SORT_BY` (default `publishedAt`; one of `relevancy`, `popularity`, `publishedAt`)
- `NEWS_API_KEY_ENCRYPTION_SECRET` — secret used to derive the AES-GCM key for encrypting user-supplied NewsAPI keys

**AI summary (Mistral)**
- `MISTRAL_API_KEY` — required when `AI_SUMMARY_ENABLED=true`
- `MISTRAL_API_URL` (default `https://api.mistral.ai/v1/chat/completions`)
- `MISTRAL_MODEL` (default `mistral-large-latest`)
- `AI_SUMMARY_ENABLED` (default `true`) — set to `false` to skip the AI step entirely
- `AI_PROMPT_VERSION` (default `v1`) — stored alongside each report for prompt-version tracking

**Reliability and limits**
- `REQUEST_TIMEOUT_SECONDS`, `REQUEST_MAX_RETRIES`, `REQUEST_BACKOFF_FACTOR`, `REQUEST_MAX_BACKOFF_SECONDS`
- `REQUEST_PAGE_SIZE_MAX` (default `100`), `MAX_PAGES_PER_REQUEST` (default `50`), `NEWSAPI_MAX_TOTAL_RESULTS` (default `1000`)
- `DB_CONNECT_TIMEOUT_SECONDS`, `DB_STATEMENT_TIMEOUT_MS`

## Local run

### 1. Install
```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Initialize the database and tables
```powershell
python main.py --init-only
```
This creates the `news_db` database and all production tables (`app_users`, `search_requests`, `articles`, `user_news`, `request_stats`, `users_keys`). Add `--debug` to also create the debug table `bad_news_bears`. Alternatively, append `--bootstrap` to any run command to initialize on startup.

### 3. Web mode (single run, requires existing `app_users` and `search_requests` rows)
```powershell
python main.py --keyword python --limit 20 --page_size 50 --language en --user_id 1 --search_request_id 1
```
In this mode the CLI uses the global `NEWSAPI_KEY` from `.env`. Articles go into `articles` and are linked to the user via `user_news`; per-request stats land in `request_stats`.

### 4. Worker loop (production mode)
```powershell
python main.py --worker --poll_interval 3
```
The worker pops the next `queued` request, looks up the user's encrypted NewsAPI key in `users_keys`, decrypts it, runs the pipeline, and updates `search_requests.status`. Multiple workers can run concurrently — `FOR UPDATE SKIP LOCKED` prevents duplicate processing.

### 5. Debug mode
See the **Debug mode** section at the bottom of this README.

## Docker
```bash
docker compose up --build
```
The `app` container runs the worker (`python main.py --worker --bootstrap --poll_interval 3`) against the `db` Postgres service. Postgres data is persisted in the `postgres_data` named volume.

## Quality checks
```powershell
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
| `app_users` | Web users (Google OAuth identity). |
| `users_keys` | Per-user encrypted NewsAPI keys (AES-GCM). |
| `search_requests` | Queue of search jobs with status (`queued`/`running`/`success`/`failed`). |
| `articles` | Deduplicated articles, unique by `url`. |
| `user_news` | Many-to-many link between `app_users`, `search_requests`, and `articles`. |
| `request_stats` | Per-request totals and rejection-reason breakdown (JSONB). |
| `request_ai_report` | One Mistral-generated summary per `search_request_id` (counts, conclusions, sentiment, topics, highlight, warnings, token usage). |
| `bad_news_bears` | **Debug only** — populated by `--debug` runs from `data/clean/*.json`. Not touched by web/worker mode. |

## AI summary flow

After `run_pipeline_for_web_user` finishes loading and persists `request_stats`, it calls `_generate_and_store_ai_summary`, which:

1. Reads the loaded pocket from DB: `articles JOIN user_news WHERE search_request_id = ?` — the canonical, deduplicated set the user actually got.
2. Calls Mistral (`response_format: json_object`) with the system prompt in `src/ai/prompts.py`.
3. Validates and normalizes the JSON response (sentiment percentages re-normalized to sum to 100; `sentiment_label` forced to match the dominant key in the distribution; `highlight.url` falls back to a real article URL if the model invented one).
4. Upserts a row in `request_ai_report` keyed by `search_request_id`.

The website reads the result by querying `request_ai_report` once `search_requests.status = 'success'`.

The AI step is **best-effort**: any Mistral or DB error is logged but does not fail the search request — articles are still loaded and the request is still marked `success`. To skip AI entirely, set `AI_SUMMARY_ENABLED=false`.

Stored summary fields:
- `news_count` — articles linked to this request
- `summary` — 1-2 sentence neutral overview
- `main_conclusions` (JSONB) — exactly 3 short conclusions
- `sentiment_label` (`positive` | `negative` | `neutral`) and `sentiment_score` — dominant sentiment and its percentage
- `sentiment_distribution` (JSONB) — `{positive, negative, neutral}` summing to 100
- `main_topics` (JSONB) — 1 to 3 topics in order of importance
- `highlight` (JSONB) — `{url, title, author?, description?, reason}`
- `data_quality_warnings` (JSONB) — pipeline-detected warnings + any flagged by the model
- `model_provider`, `model_name`, `promt_version`, `input_tokens`, `output_tokens`, `total_tokens`

## Reliability and safety guarantees
- HTTP retries with backoff and `Retry-After` handling (`429`, `5xx`).
- Strict input validation in transform layer; rejected records are counted by reason and surfaced in `request_stats`.
- Idempotent article upsert on `url`; idempotent `user_news` insert on `(user_id, article_id, search_request_id)`.
- Atomic worker dequeue (`FOR UPDATE SKIP LOCKED`), safe for multiple worker processes.
- DB connect and statement timeouts are configurable.
- NewsAPI keys are stored encrypted (AES-GCM) and only decrypted in-memory for the duration of a single pipeline run.

## Notes
- `.env`, `.venv`, `__pycache__`, and generated files under `data/raw` and `data/clean` are gitignored.
- Never commit real keys — only `.env.example` should be in git.

## Troubleshooting
- **`Database 'news_db' does not exist`** — run `python main.py --init-only` once, or add `--bootstrap` to your run command.
- **`password authentication failed`** — verify `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD` and test the same credentials with `psql`/pgAdmin. On localized Windows, `db.py` decodes non-UTF8 libpq errors and prints a hint.
- **`User has no NEWSAPI key yet`** (worker mode) — the user has no row in `users_keys` for `service = 'news_api'`. Use the web flow to upload their key, or insert one manually.
- **`NEWSAPI_KEY contains a placeholder value`** — replace `YOUR_REAL_NEWSAPI_KEY` in `.env` with a real key (only needed for CLI/debug mode).

---

## Debug mode (`--debug`)

The `--debug` flag turns `main.py` into a pipeline-inspection script. Use it whenever you need to look at exactly what NewsAPI returned, what the transform layer kept or rejected, and why — without touching any of the production tables (`articles`, `user_news`, `request_stats`).

```powershell
python main.py --debug --keyword python --limit 20 --page_size 50 --language en
```

What it does, page by page:

1. **Extract** — `make_extract_debug` calls NewsAPI with the global `NEWSAPI_KEY` from `.env` and writes the raw payload to:
   ```
   data/raw/<UTC-timestamp>_<sanitized-keyword>_page_<N>.json
   ```
2. **Transform** — `transform_article_debug` reads that raw file, runs the same validation/normalization used in production, and writes two artifacts:
   ```
   data/clean/cleaned_<keyword>_page_<N>_<timestamp>.json   # accepted articles
   data/clean/stats/stats_<keyword>_page_<N>_<timestamp>.json   # totals + rejection reasons
   ```
3. **Load** — `load_news` inserts the cleaned articles into the **`bad_news_bears`** table using `ON CONFLICT (url) DO NOTHING`. This table exists only for debug inspection; it is not part of the web/worker data model and is created on demand (either by `--init-only --debug` or automatically when a `--debug` run notices it is missing).

Pagination follows the same `--limit` / `--page_size` / `MAX_PAGES_PER_REQUEST` rules as the production pipeline, so the debug run is a faithful replay of what the worker would do — just with files on disk and an isolated table you can drop and recreate freely.

Use it to:
- Verify NewsAPI responses for a new keyword/language combination.
- Reproduce a transform-layer rejection without re-hitting the API (re-run `transform_article_debug` against the saved `data/raw/*.json`).
- Compare `stats_*.json` across runs when tuning validation rules.
- Sanity-check the SQL load path on a throwaway table before it touches `articles`.
