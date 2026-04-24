from __future__ import annotations

import argparse
import logging

from config.config import settings
from src import (
    app_user_exists,
    create_app_users_table,
    create_articles_table,
    database_exists,
    create_news_tables,
    create_request_stats_table,
    create_search_requests_table,
    create_user_news_table,
    ensure_tables_exist,
    init_database,
    run_debug_pipeline,
    run_pipeline_for_web_user,
    run_worker_loop,
    search_request_belongs_to_user,
    search_request_exists,
    table_exists,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


def positive_int(value: str) -> int:
    ivalue = int(value)
    if ivalue <= 0:
        raise argparse.ArgumentTypeError("Value must be > 0")
    return ivalue


def page_size_int(value: str) -> int:
    ivalue = positive_int(value)
    if ivalue > settings.request_page_size_max:
        raise argparse.ArgumentTypeError(
            f"page_size must be <= {settings.request_page_size_max}"
        )
    return ivalue


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ETL pipeline for loading news from NewsAPI into PostgreSQL"
    )

    parser.add_argument("--keyword", help="Keyword for news search")
    parser.add_argument(
        "--limit",
        type=positive_int,
        default=20,
        help="How many rows should be loaded",
    )
    parser.add_argument(
        "--page_size",
        type=page_size_int,
        default=settings.request_page_size_max,
        help=f"Articles per page (max {settings.request_page_size_max})",
    )
    parser.add_argument("--language", type=str, default=settings.default_language)

    parser.add_argument("--debug", action="store_true", help="Use debug raw/clean JSON flow")
    parser.add_argument("--user_id", type=positive_int)
    parser.add_argument("--search_request_id", type=positive_int)

    parser.add_argument("--worker", action="store_true", help="Run queue worker loop")
    parser.add_argument(
        "--poll_interval",
        type=positive_int,
        default=3,
        help="Worker poll interval in seconds",
    )

    parser.add_argument(
        "--init-only",
        action="store_true",
        help="Initialize database/tables and exit",
    )
    parser.add_argument(
        "--bootstrap",
        action="store_true",
        help="Initialize database/tables before pipeline run",
    )

    return parser.parse_args()


def init_all_tables(debug: bool) -> None:
    init_database()
    create_app_users_table()
    create_search_requests_table()
    create_articles_table()
    create_user_news_table()
    create_request_stats_table()
    if debug:
        create_news_tables()


def _validate_web_context(user_id: int, search_request_id: int) -> None:
    if not app_user_exists(user_id):
        raise RuntimeError(
            f"app_users row with id={user_id} does not exist. "
            "Create user first or run in --debug mode."
        )

    if not search_request_exists(search_request_id):
        raise RuntimeError(
            f"search_requests row with id={search_request_id} does not exist. "
            "Create search request first or run in --debug mode."
        )

    if not search_request_belongs_to_user(search_request_id, user_id):
        raise RuntimeError(
            f"search_request_id={search_request_id} does not belong to user_id={user_id}"
        )


def _ensure_runtime_schema(debug_mode: bool) -> None:
    if not database_exists(settings.db_news):
        raise RuntimeError(
            f"Database '{settings.db_news}' does not exist. "
            "Run `python main.py --init-only` once or re-run with `--bootstrap`."
        )

    required_tables = [
        "app_users",
        "search_requests",
        "articles",
        "user_news",
        "request_stats",
    ]
    ensure_tables_exist(settings.db_news, required_tables)

    if debug_mode and not table_exists(settings.db_news, "bad_news_bears"):
        create_news_tables()


def main() -> None:
    args = parse_args()
    logger.info("Starting ETL")

    try:
        if args.init_only or args.bootstrap:
            init_all_tables(debug=args.debug)

        if args.init_only:
            logger.info("Database initialization completed")
            return

        _ensure_runtime_schema(debug_mode=args.debug)

        if args.worker:
            run_worker_loop(poll_interval_seconds=args.poll_interval)
            return

        if not args.keyword:
            raise RuntimeError("--keyword is required unless --worker or --init-only is used")

        if args.debug:
            loaded = run_debug_pipeline(
                keyword=args.keyword,
                limit=args.limit,
                page_size=args.page_size,
                language=args.language,
            )
        else:
            if args.user_id is None or args.search_request_id is None:
                raise RuntimeError(
                    "--user_id and --search_request_id are required in web mode "
                    "(without --debug)"
                )

            _validate_web_context(args.user_id, args.search_request_id)
            loaded = run_pipeline_for_web_user(
                user_id=args.user_id,
                search_request_id=args.search_request_id,
                key_word=args.keyword,
                limit=args.limit,
                page_size=args.page_size,
                language=args.language,
            )

        logger.info("Pipeline finished. loaded_rows=%s", loaded)
    except Exception as exc:
        logger.exception("Pipeline failed: %s", exc)
        raise


if __name__ == "__main__":
    main()
