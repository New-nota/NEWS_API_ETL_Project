import logging
from src import (
    make_extract_web,
    make_extract_debug,
    transform_article_web,
    transform_article_debug,
    load_web_pipeline,
    load_news,
)

logger = logging.getLogger(__name__)

def run_pipeline_for_web_user(user_id: int, search_request_id: int, key_word: str, limit: int, page_size: int) -> int:
    num_of_news = 0
    page = 1
    while num_of_news < limit:
        payload, raw_articles_count = make_extract_web(key_word, page, page_size)
        if raw_articles_count == 0:
            logger.warning("there is no more artical")
            break
        clean_data, stats = transform_article_web(payload)
        result_num_of_news = load_web_pipeline(user_id, search_request_id, clean_data, stats)
        num_of_news += result_num_of_news
        page += 1
    logger.info(f"{num_of_news} news on key word {key_word} already aploaded")
    return num_of_news

def run_debug_pipeline(keyword: str, limit:int, page_size: int) -> int:
    num_of_news = 0
    page = 1
    while num_of_news < limit:
        max_rows = limit - num_of_news
        new_file_name, raw_articles_count = make_extract_debug(keyword, page, page_size)
        if raw_articles_count == 0:
            logger.warning("there is no more artical")
            break
        clean_data = transform_article_debug(new_file_name,keyword,page)
        result_num_of_news = load_news(clean_data, max_rows)
        num_of_news += result_num_of_news
        page += 1
    logger.info(f"{num_of_news} news on key word {keyword} already aploaded")
    return num_of_news
