import requests
import urllib.parse
from bs4 import BeautifulSoup
from ..storage.db import get_cached_response, save_cache_response

class NewsScraper:
    """Scrapes recent news using Google News RSS to feed the LLM Context Engine."""
    
    BASE_URL = "https://news.google.com/rss/search"

    def __init__(self, use_cache=True, cache_ttl=14400): # 4 hours cache for news
        self.use_cache = use_cache
        self.cache_ttl = cache_ttl
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0'
        })

    def get_team_news(self, team_name, limit=5):
        """Fetches the latest news snippets for a given team."""
        cache_key = f"news_{team_name}"
        
        if self.use_cache:
            cached = get_cached_response(cache_key, max_age_seconds=self.cache_ttl)
            if cached:
                return cached[:limit]

        query = urllib.parse.quote(f"{team_name} futebol")
        url = f"{self.BASE_URL}?q={query}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
        
        try:
            response = self.session.get(url)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, features='html.parser')
            
            items = soup.find_all('item')
            news_data = []
            
            for item in items[:limit]:
                title = item.title.text if item.title else ''
                # Description usually has the snippet
                description_html = item.description.text if item.description else ''
                # Clean HTML from description
                desc_soup = BeautifulSoup(description_html, "html.parser")
                snippet = desc_soup.get_text(separator=" ").strip()
                pub_date = item.pubDate.text if item.pubDate else ''
                
                news_data.append({
                    "title": title,
                    "snippet": snippet,
                    "date": pub_date
                })
            
            if self.use_cache and news_data:
                save_cache_response(cache_key, news_data)
                
            return news_data
            
        except Exception as e:
            print(f"Error fetching news for {team_name}: {e}")
            return []

if __name__ == '__main__':
    scraper = NewsScraper()
    news = scraper.get_team_news("Flamengo")
    for n in news:
        print(f"- {n['title']}\n  {n['date']}\n")
