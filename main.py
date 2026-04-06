import argparse
from src import make_extract, transform_article, load_news, init_database, create_news_tables
import logging

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
        "--category",
        required=True,
        help="Category for news search"
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
    return parser.parse_args()

def pipeline() -> None:
    args = parse_args()
    key_word = args.keyword
    category = args.category
    limit = args.limit
    page_size = args.page_size
    num_of_news = 0
    page = 1
    while num_of_news < limit:
        raw_file_name = make_extract(category, key_word, page, page_size)
        clean_file_name = transform_article(raw_file_name, category, key_word, page)
        result_num_of_news = load_news(clean_file_name)
        if result_num_of_news == 0:
            logger.warning("there is no more artical")
            break
        num_of_news += result_num_of_news
        page += 1
    logger.info(f"{num_of_news} news on category {category} already aploaded")
    return num_of_news

def main()-> None:
    logger.info("Starting pipeline, init database, build table..")
    try:
        init_database()
        create_news_tables()
        loaded = pipeline()
        logger.info("Pipline finished. loaded rows: %s", loaded)
    except Exception as e:
        logger.exception("pipeline failed: %s", e)
        raise



if __name__ == "__main__":
    main()