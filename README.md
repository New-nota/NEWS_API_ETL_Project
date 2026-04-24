# NEWS_API_ETL_Project

Production-oriented ETL pipeline that collects articles from NewsAPI, validates/transforms them, and loads clean records into PostgreSQL.

## What this project does
1. `extract`: gets paginated articles from NewsAPI with timeout, retries, and backoff.
2. `transform`: validates each article, normalizes fields and timestamps, and collects rejection stats.
3. `load`: upserts articles and links them to user requests with deduplication.
4. `worker`: atomically claims queued search requests from PostgreSQL and processes them safely.

## Repository structure
```text
project/
├── config/
│   └── config.py
├── data/
│   ├── raw/
│   └── clean/
├── notebooks/
│   └── 01_eda.ipynb
├── src/
│   ├── __init__.py
│   ├── db.py
│   ├── extract.py
│   ├── load.py
│   ├── pipeline.py
│   ├── transform.py
│   └── worker.py
├── .env.example
├── DockerFile
├── docker-compose.yml
├── main.py
├── requirements.txt
└── requirements-dev.txt
```

## Environment variables
Copy `.env.example` to `.env` and fill your values:

```bash
cp .env.example .env
```

Key variables:
- `NEWSAPI_KEY`: required for extract.
- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NEWS`.
- Optional reliability settings: `REQUEST_MAX_RETRIES`, `REQUEST_TIMEOUT_SECONDS`, `MAX_PAGES_PER_REQUEST`, `DB_CONNECT_TIMEOUT_SECONDS`.

## Local run
### 1. Install
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Initialize DB objects
```bash
python main.py --init-only
```
Alternative for one-shot run: add `--bootstrap` to any run command below.

### 3. Debug run (raw/clean JSON + DB table `bad_news_bears`)
```bash
python main.py --debug --keyword python --limit 20 --page_size 50 --language en
```

### 4. Web-mode run (requires existing `app_users` and `search_requests` rows)
```bash
python main.py --keyword python --limit 20 --page_size 50 --language en --user_id 1 --search_request_id 1
```

### 5. Worker loop
```bash
python main.py --worker --poll_interval 3
```

## Docker
Run app + Postgres with Docker Compose:

```bash
docker compose up --build
```

By default, app container runs worker mode.

## Quality checks
```bash
python -m compileall .
ruff check .
pytest -q
bandit -r src config main.py
pip-audit
```

## Reliability and safety guarantees
- Request retry with backoff and HTTP status handling (`429`, `5xx`).
- Input validation in transform layer (bad records are rejected with reason stats).
- Idempotent article upsert by URL.
- Atomic worker dequeue (`FOR UPDATE SKIP LOCKED`) to avoid duplicate processing across workers.
- DB connection timeout and statement timeout support.

## Notes
- `.env`, `.venv`, `__pycache__`, and generated files under `data/raw` and `data/clean` are ignored by git.
- Keep secrets only in `.env` (never commit real keys).

## Troubleshooting
- `Database 'news_db' does not exist`:
  - Run `python main.py --init-only` once, or add `--bootstrap` to your run command.
- `password authentication failed`:
  - Verify `.env` values `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`.
  - Manually test credentials with psql/pgAdmin for the same host/port/user.

