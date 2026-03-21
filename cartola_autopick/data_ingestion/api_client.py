import requests
import json
from ..storage.db import get_cached_response, save_cache_response

class CartolaAPIClient:
    BASE_URL = "https://api.cartola.globo.com"

    def __init__(self, use_cache=True, cache_ttl=3600):
        self.use_cache = use_cache
        self.cache_ttl = cache_ttl
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })

    def _get(self, endpoint):
        """Helper method to fetch from cache or API."""
        if self.use_cache:
            cached_data = get_cached_response(endpoint, max_age_seconds=self.cache_ttl)
            if cached_data:
                return cached_data

        url = f"{self.BASE_URL}/{endpoint}"
        response = self.session.get(url)
        response.raise_for_status()
        data = response.json()
        
        if self.use_cache:
            save_cache_response(endpoint, data)
            
        return data

    def get_market_status(self):
        """Returns the current status of the market (round, open/closed)."""
        return self._get('mercado/status')

    def get_market_players(self):
        """
        Returns all players currently listed in the market, along with
        dictionaries for clubs, positions, and player statuses.
        """
        return self._get('atletas/mercado')

    def get_matches(self):
        """Returns the matches for the current round."""
        return self._get('partidas')

if __name__ == '__main__':
    # Simple test
    client = CartolaAPIClient()
    status = client.get_market_status()
    print(f"Market Status: {status.get('status_mercado')}, Round: {status.get('rodada_atual')}")
