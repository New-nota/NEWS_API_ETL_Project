# NEWS_API_ETL_Project

### Цель
обрабатывать из внешенго Api новости и используя принцип ETL сохранять нужные новости в базу данных.

### Стек
Extract: requests(страна, категоия, ключевое слово, размер страницы (опционально)) -> сохранение статей в папку data/raw

Transform: Python скрипт читает данные из нового файла data/raw, смотрит чтобы были указаны: автор, заголовок, описание не меньше 20 символов, url ссылка

Load: psycopg2 подключается к PostgreSQL, перед вставкой разрешается конфлик с уникальной url ссылкой. Если такая ссылка уже есть то новость не добавляется в таблицу

db: создается база данных и таблица если их еще нет. url присваивается UNICE

Пайплайн: программа запускается скриптом разделенным на 5 основных модулей (db.py, extract.py, load.py, transform.py, main.py)

### Схема ETL
top-headlines из NewsApi (extract) -> Филтр на наличие автора, заголовка, описания не меньше 20 символов, наличие url (transform) -> загрузка статей чей url отстуствует в базе данных (load)

### Стуктура папок
```text
project/
├── config
|   └── config.py
├── data /
|   ├──raw / # тут будут хранится статьи до обработки в формате json
|   └──clean / # тут будут хранится статьи после обработки
├── notebooks /
|   └── 01_eda.ipynb
├── src /
|   ├── __init__.py
|   ├── db.py
|   ├── extract.py
|   ├── load.py
|   └── transform.py
├──.env.example
├── main.py
└── requirements.txt
```

### Порядок запуска
#### склонировать репу 
```bash
git clone [сслыка на репозиторий]
```

#### перейти в папку проекта
```bash
cd <repo_name>
```
#### создать виртуальное окружение
```bash
py -m venv .venv

.venv\Scripts\Activate.ps1
```
#### установить библиотеки
``` bash
pip install -r requirements.txt
```

#### скопировать .env.exsample
``` bash
copy .env.exsample .env
```
Заполнить .env вашими данными

#### запустить код
```bash
python main.py --keyword your_key_word --category your_category --limit your_limit_of_articles --page_size your_page_size
```

### пример .env
```.env
DB_HOST=localhost
DB_PORT=5432
DB_USER=postgres
DB_PASSWORD=1234
DB_ADMIN_DB=postgres
DB_NEWS=db_news
NEWSAPI_KEY =your_key
```

### Важные моменты
в папку data/raw сохраняются все статьи которые были получены за 1 запрос по вашим критериям. Им в качетсве имени присваивается текущее дата-время, ключевое слово и текущая страница. 
в папку data/clean попадают все статьи которые имеют: автора, заголовок, описание 20+ символов и url ссылку. им присвается имя аналогичным способом что и в data/raw однако первым словом в имени является cleaned