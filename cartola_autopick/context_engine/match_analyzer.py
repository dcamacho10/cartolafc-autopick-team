import requests
from bs4 import BeautifulSoup
from ..storage.db import get_cached_response, save_cache_response

class MatchAnalyzer:
    """Scrapes current Brasileirao standings to compute Team Strength (1-5)."""

    STANDINGS_URL = "https://ge.globo.com/futebol/brasileirao-serie-a/"

    def __init__(self, use_cache=True, cache_ttl=43200): # 12 hours cache
        self.use_cache = use_cache
        self.cache_ttl = cache_ttl
        self.session = requests.Session()
        self.session.headers.update({'User-Agent': 'Mozilla/5.0'})

    def get_standings(self):
        """Scrapes the standings table from GE."""
        cache_key = "brasileirao_standings"
        if self.use_cache:
            cached = get_cached_response(cache_key, max_age_seconds=self.cache_ttl)
            if cached: return cached

        try:
            response = self.session.get(self.STANDINGS_URL)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, 'html.parser')

            # GE uses a specific structure for the table. It has two tables side by side
            # (one for team names, one for points/stats). We need to zip them.
            teams_td = soup.select('td.classificacao__equipes.classificacao__equipes--equipe')
            stats_trs = soup.select('table.tabela__pontos tbody tr')

            if not teams_td or not stats_trs:
                print("Could not parse standings table from GE. Check selectors.")
                return {}

            standings = {}
            for team_col, stat_row in zip(teams_td, stats_trs):
                team_name = team_col.select_one('.classificacao__equipes.classificacao__equipes--nome').text.strip()
                # Stats columns: P, J, V, E, D, GP, GC, SG, %
                cols = stat_row.find_all('td')
                if len(cols) >= 8:
                    standings[team_name] = {
                        "points": int(cols[0].text),
                        "wins": int(cols[2].text),
                        "goals_pro": int(cols[5].text),
                        "goals_conceded": int(cols[6].text),
                        "goal_diff": int(cols[7].text)
                    }

            if self.use_cache and standings:
                save_cache_response(cache_key, standings)
            return standings

        except Exception as e:
            print(f"Error fetching standings: {e}")
            return {}

    def compute_strength_scores(self):
        """Calculates a 1-5 score for each team based on standings."""
        standings = self.get_standings()
        if not standings:
            return {}

        # We will use points + goal difference as the main metrics to normalize
        teams = list(standings.items())
        # Sort by points descending, then goal diff
        teams.sort(key=lambda x: (x[1]['points'], x[1]['goal_diff']), reverse=True)

        scores = {}
        total_teams = len(teams)
        for i, (team_name, stats) in enumerate(teams):
            # Top 20% gets 5, next 20% gets 4...
            percentile = i / total_teams
            if percentile < 0.2:
                score = 5
            elif percentile < 0.4:
                score = 4
            elif percentile < 0.6:
                score = 3
            elif percentile < 0.8:
                score = 2
            else:
                score = 1
            scores[team_name] = score

        return scores

    def analyze_match(self, home_team, away_team, strength_scores):
        """
        Analyzes a single match mapping Cartola names to Standings names (fuzzy match if needed).
        Returns the match difficulty classification.
        """
        # Very simple exact match for now, could be improved with fuzzywuzzy
        home_score = strength_scores.get(home_team, 3) # default to 3 if mapped wrong
        away_score = strength_scores.get(away_team, 3)

        diff = home_score - away_score
        
        # Adjust for home advantage (Home team + 0.5 effectively)
        adjusted_diff = diff + 0.5 

        if abs(adjusted_diff) <= 1.0:
            classification = "equilibrium"
            home_multiplier = 1.0
            away_multiplier = 1.0
        elif adjusted_diff > 1.0:
            classification = "home_favorite"
            home_multiplier = 1.2
            away_multiplier = 0.8
        else:
            classification = "away_favorite"
            home_multiplier = 0.8
            away_multiplier = 1.2

        return {
            "home_score": home_score,
            "away_score": away_score,
            "classification": classification,
            "home_multiplier": home_multiplier,
            "away_multiplier": away_multiplier
        }

if __name__ == '__main__':
    analyzer = MatchAnalyzer()
    scores = analyzer.compute_strength_scores()
    for team, score in scores.items():
        print(f"{team}: Strength {score}")
    
    # Test match
    print(analyzer.analyze_match("Palmeiras", "Cuiabá", scores))
