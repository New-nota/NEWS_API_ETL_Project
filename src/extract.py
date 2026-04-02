import requests as r
import json
from typing import Optional

# описать классом 
class EverythingParams:
    language : Optional[str]
    q:str
    source: Optional[str]
    from_date: Optional[str]
    to_date: Optional[str]
    sort_by: Optional[str]
    page: int = 1
    page_size: int = 100

class TopHeadlinesParams:
    language : Optional[str]
    country: Optional[str]
    category: Optional[str]
    sources: Optional[str]
    q: Optional[str]
    page: int = 1
    page_size: int = 1
    page_size: int = 1

class SourcesParams:
    language : Optional[str]
    country: Optional[str]
    category: Optional[str]

class NewsType:
    BASE = 'https://newsapi.org/v2/'
    def __init__(self, method):
        self.method = method
        if self.method == "everything":
            params = EverythingParams
        

    

method = 'top-headlines'
apikey = input(":")
catch_phrase = ['spots', 'finance', 'technology']
params = {
    'q':catch_phrase[0],
    'apiKey': apikey,
    'sortBy':'publishedAt',
    'pageSize':100,
    'page':1
}
news_data = r.get(BASE + method, params)
