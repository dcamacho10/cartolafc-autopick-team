import re

class RuleEngine:
    """Applies hard rules based on keyword parsing and API status."""
    
    # Keywords that indicate a player is likely NOT playing
    CRITICAL_KEYWORDS = [
        r'\bpoupado\b', r'\bdesfalque\b', r'\blesão\b',
        r'\blesionado\b', r'\bsuspenso\b', r'\bnão viajou\b',
        r'\bfora\b', r'\bdúvida\b', r'\bduvida\b', r'\bentorse\b',
        r'\bcastigado\b', r'\bcartões\b', r'\bcartoes\b',
        r'\blibertadores\b', r'\bcopa do brasil\b', r'\breserva\b',
        r'\btitulares?\b',
    ]

    # API mercado "status": 7 Provável, 2 Dúvida, 3 Suspenso, 5 Contundido, 6 Nulo
    STATUS_MULTIPLIER = {
        7: 1.0,
        2: 0.3,
        3: 0.0,
        5: 0.0,
        6: 0.0,
    }

    def __init__(self):
        self.compiled_crit = [re.compile(k, re.IGNORECASE) for k in self.CRITICAL_KEYWORDS]

    @staticmethod
    def _news_snippets_to_text(news_snippets):
        """Accepts legacy dict items ({title, snippet}) or plain strings (e.g. ESPN browser scraper)."""
        parts = []
        for n in news_snippets:
            if isinstance(n, str):
                parts.append(n)
            elif isinstance(n, dict):
                parts.append(n.get('snippet') or '')
                parts.append(n.get('title') or '')
        return " ".join(parts)

    def evaluate_player_news(self, player_name, news_snippets):
        """
        Checks if player name is mentioned near critical keywords in the news.
        Returns a risk multiplier (0.0 to 1.0).
        """
        if not news_snippets:
            return 1.0

        text = self._news_snippets_to_text(news_snippets)
        
        # If player is mentioned, check if critical keywords are also in the text
        # This is a basic co-occurrence check.
        if player_name.lower() in text.lower():
            for regex in self.compiled_crit:
                if regex.search(text):
                    # High risk, player mentioned in same news block as 'poupado' etc.
                    return 0.1 
        
        return 1.0

    def evaluate_api_status(self, status_id):
        """Returns the base multiplier for the player's official Cartola status."""
        return self.STATUS_MULTIPLIER.get(status_id, 0.0)

if __name__ == '__main__':
    engine = RuleEngine()
    print("Status 7 (Provável):", engine.evaluate_api_status(7))
    print("Status 3 (Suspenso):", engine.evaluate_api_status(3))
    
    mock_news = [{"title": "Desfalques no Flamengo", "snippet": "Arrascaeta foi poupado hoje."}]
    print("Arrascaeta risk:", engine.evaluate_player_news("Arrascaeta", mock_news))
    print("Pedro risk:", engine.evaluate_player_news("Pedro", mock_news))
