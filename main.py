from src import make_extract, transform_article, load_news, init_database, create_news_tables

from config.config import settings

def main()-> None:
    init_database()
    create_news_tables()

    key_word = input("Write a key word: ")
    for num, category in enumerate(settings.CATEGORIES, start=1):
        print(f"{num} - {category}")
    num_category = int(input("Choose a nuber of category"))
    choosed_category = settings.CATEGORIES[num_category - 1]
    num_of_news = 0
    page = 1
    while num_of_news < 20:
        raw_file_name = make_extract(choosed_category, key_word, page)
        clean_file_name = transform_article(raw_file_name, choosed_category, key_word, page)
        result_num_of_news = load_news(clean_file_name)
        if result_num_of_news == 0:
            print("there is no more artical")
            break
        num_of_news += result_num_of_news
        page += 1
    print(f"{num_of_news} news on category {choosed_category} already aploaded")


if __name__ == "__main__":
    main()