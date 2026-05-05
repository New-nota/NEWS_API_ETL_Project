# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```powershell
# Install
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt

# Initialize DB + all production tables (add --debug to also create bad_news_bears)
python main.py --init-only

# Run modes
python main.py --worker --poll_interval 3                                              # production: claim queued search_requests
python main.py --keyword X --user_id 1 --search_request_id 1 --limit 20 --language en  # one-shot web run (uses env NEWSAPI_KEY)
python main.py --debug --keyword X --limit 20 --language en                            # debug: writes data/raw, data/clean, bad_news_bears

# Tests / lint
python -m pytest tests/
python -m pytest tests/test_pipeline.py::test_pipeline_respects_limit   # single test
python -m ruff check src config main.py tests

# Docker
docker compose up --build
```

## Architecture

**Two execution modes share extract + transform but diverge at load.** The split is intentional — do not unify them.

- **Web/worker mode** (`run_pipeline_for_web_user` in `src/pipeline.py`)
  - Loads into the production schema: `articles` (URL-deduped, upserted) ← `user_news` (per-user link, ON CONFLICT DO NOTHING) ← `search_requests`. Stats go to `request_stats`. AI summary goes to `request_ai_report`.
  - Worker (`src/worker.py`) claims jobs via `FOR UPDATE SKIP LOCKED` so multiple workers are safe.
- **Debug mode** (`run_debug_pipeline` in `src/pipeline.py`)
  - Writes raw payload to `data/raw/`, cleaned articles + stats to `data/clean/`, then loads into `bad_news_bears` (standalone debug table). Never touches `articles` / `user_news` / `request_stats`.

**Two NewsAPI key sources.** CLI/debug uses env `NEWSAPI_KEY` (fallback). Worker calls `get_decrypted_news_api_key_for_user` (`src/user_news_api_key.py`) — per-user keys are AES-GCM-encrypted in `users_keys`, derived from `NEWS_API_KEY_ENCRYPTION_SECRET`. The pipeline accepts an optional `news_api_key` arg that the worker passes in.

**AI summary flow** (`src/ai/`, called from `_generate_and_store_ai_summary` in `src/pipeline.py`):
1. After `load_request_stats`, query `articles JOIN user_news WHERE search_request_id = ?` to get the canonical pocket (deduped, post-load).
2. Mistral call (`response_format: json_object`) returns the structured summary. `report.py` normalizes the response — sentiment percentages get re-normalized to sum to 100, `sentiment_label` is forced to match the dominant key in the distribution (the model can't return inconsistent label/score), and `highlight.url` falls back to a real article URL if the model invented one.
3. Upsert into `request_ai_report` keyed by `search_request_id`.
4. **Best-effort:** any Mistral or DB failure inside this step is logged but does not fail the search request — articles are still loaded and the request still ends `success`. Set `AI_SUMMARY_ENABLED=false` to skip entirely.

**Schema creation lives in `src/db.py`** as `create_*_table()` functions. `main.py:init_all_tables` orchestrates them and `_ensure_runtime_schema` validates required tables exist before each run. When adding a new table:
1. Add `create_X_table()` in `src/db.py`
2. Re-export it from `src/__init__.py`
3. Call it from `init_all_tables` in `main.py`
4. Add the table name to `required_tables` in `_ensure_runtime_schema`

## Non-obvious behaviors / gotchas

- **`pyproject.toml` must be BOM-free.** A UTF-8 BOM at the start breaks pytest's TOML parser silently with a misleading error. New TOML files: write without BOM.
- **`db.py` has special handling for non-UTF8 libpq errors** on localized Windows installs (`_decode_non_utf8_error` tries cp1251/cp866). Do not replace it with a naive `str(exc)` — it will surface mojibake instead of a real error message.
- **`NEWS_DB` vs `DB_NEWS` mismatch:** `config/config.py` reads `NEWS_DB`, but `docker-compose.yml` references `${DB_NEWS:-...}`. Known inconsistency — don't "fix" it without verifying the deploy story.
- **`docker-compose.yml` overrides `DB_HOST: localhost` for the app container**, which doesn't reach the `db` service. Pre-existing — don't change without confirming.
- **`request_ai_report.promt_version`** is misspelled (missing 'p'). Schema column is `promt_version`; the Python field is `prompt_version`. The mapping happens in `load_ai_report`. Don't rename either side without coordinating.
- **Debug pipeline rewrites disk on every page** with timestamped filenames — the user inspects these manually. Don't add cleanup logic.
- **Tests in `tests/test_pipeline.py` monkeypatch `pipeline.make_extract_web` etc.** Stubs must accept the `news_api_key` kwarg even if unused, because the pipeline always passes it.

## Settings reference (`config/config.py`)

All settings are loaded via the `Settings` dataclass from env vars (with `.env` overriding the shell). Helpers: `_get_env_str`, `_get_env_int`, `_get_env_float`, `_get_env_bool`. Add new settings here, not scattered `os.getenv` calls.
