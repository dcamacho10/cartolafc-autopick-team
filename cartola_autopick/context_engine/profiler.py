from .match_analyzer import MatchAnalyzer
from .rule_engine import RuleEngine
from .momentum_llm import MomentumLLM

class Profiler:
    """Merges all context modules and Cartola Stats to build the final Player Profile."""
    
    def __init__(self):
        self.match_analyzer = MatchAnalyzer()
        self.rule_engine = RuleEngine()
        self.llm = MomentumLLM()
        self.strength_scores = self.match_analyzer.compute_strength_scores()
        
    def generate_profiles(self, players, clubs, matches, news_data):
        """
        Takes Cartola API players, matches and news data, returning enriched profiles.
        players: list of player dicts
        clubs: dict of clubs
        matches: list of match dicts
        news_data: dict of {club_id: [news snippets]}
        """
        profiles = []
        
        match_map = {}
        for m in matches:
            home_id = m.get('clube_casa_id')
            away_id = m.get('clube_visitante_id')
            home_name = clubs.get(str(home_id), {}).get('nome', '') if clubs else ''
            away_name = clubs.get(str(away_id), {}).get('nome', '') if clubs else ''
            
            # Analyze match difficulty
            analysis = self.match_analyzer.analyze_match(home_name, away_name, self.strength_scores)
            match_map[home_id] = {"opponent": away_name, "multiplier": analysis['home_multiplier']}
            match_map[away_id] = {"opponent": home_name, "multiplier": analysis['away_multiplier']}

        for p in players:
            club_id = p.get('clube_id')
            status_id = p.get('status_id')
            media_num = p.get('media_num', 0.0)
            preco_num = p.get('preco_num', 0.0)
            
            # 1. Base API Status Multiplier
            status_mult = self.rule_engine.evaluate_api_status(status_id)
            
            # 2. News/Rule Multiplier
            club_news = news_data.get(club_id, [])
            news_mult = self.rule_engine.evaluate_player_news(p.get('apelido', ''), club_news)
            
            # 3. Match Equilibrium Multiplier
            match_info = match_map.get(club_id, {"multiplier": 1.0})
            match_mult = match_info['multiplier']
            
            # 4. LLM Momentum
            # Here we just assume LLM gave us a score. For speed, we'd batch this or run it once per club.
            # We will default to 1.0 in this snippet to avoid blocking on API calls for all players.
            # In a real run, `news_data` could pre-contain the LLM score per club.
            llm_score = 1.0 
            
            # Final Expected Points Calculation
            # This is a very basic initial formula.
            # Expected Points = Base Avg * Status (0/1) * NewsRisk (0.1/1) * MatchDiff (0.8-1.2) * Momentum
            expected_points = media_num * status_mult * news_mult * match_mult * llm_score
            
            profiles.append({
                "id": p.get('atleta_id'),
                "name": p.get('apelido'),
                "position_id": p.get('posicao_id'),
                "club_id": club_id,
                "price": preco_num,
                "expected_points": expected_points,
                "status_id": status_id,
                "media_num": media_num
            })
            
        return profiles
