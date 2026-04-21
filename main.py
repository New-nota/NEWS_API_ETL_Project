import argparse
import logging

from src import (
    init_database,
    create_app_users_table,
    create_search_requests_table,
    create_articles_table,
    create_user_news_table,
    create_request_stats_table,
    create_news_tables,
    run_pipeline_for_web_user, 
    run_debug_pipeline
)

logging.basicConfig(
    level=logging.INFO,
    format = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)

   

def positive_int(value: str) -> int:
    ivalue = int(value)
    if ivalue <= 0:
        raise argparse.ArgumentTypeError("Value must be > 0")
    return ivalue

def parse_args():
    parser = argparse.ArgumentParser(
        description="ETL pipeline for loading from NewsApi into PostgreSQL" 
    )

    parser.add_argument(
        "--keyword",
        required=True,
        help="Keyword for news search"
    )
    parser.add_argument(
        "--limit",
        type=positive_int,
        default=20,
        help="Amount of news must be aploaded"
    )
    parser.add_argument(
        "--page_size",
        type=positive_int,
        default=100,
        help="Amount of articels on 1 page"

    )
    parser.add_argument(
        "--debug",
        action="store_true"
    )
    parser.add_argument(
        "--user_id", 
        type=int,
        default=1
        )
    parser.add_argument(
        "--search_request_id",
        type=int,
        default=1
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


def main()-> None:
    args = parse_args()
    logger.info("Starting pipeline, init database, build table..")
    try:
        init_all_tables(debug=args.debug)
        if args.debug:
            loaded = run_debug_pipeline(args.keyword, args.limit, args.page_size)
        else:
            loaded = run_pipeline_for_web_user(args.user_id, args.search_request_id, args.keyword, args.limit, args.page_size)
        logger.info("Pipline finished. loaded rows: %s", loaded)
    except Exception as e:
        logger.exception("pipeline failed: %s", e)
        raise

if __name__ == "__main__":
    main()