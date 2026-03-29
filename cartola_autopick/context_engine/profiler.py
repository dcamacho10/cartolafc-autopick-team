from .match_analyzer import MatchAnalyzer
from .rule_engine import RuleEngine
from .momentum_llm import MomentumLLM

class Profiler:
    """Merges all context modules and Cartola Stats to build the final Player Profile."""
    
    def __init__(self):
        self.match_analyzer = MatchAnalyzer()
        self.rule_engine = RuleEngine()
        self.llm = MomentumLLM()
        
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
            
            # Analyze match difficulty using official table positions and recent form
            analysis = self.match_analyzer.analyze_match(m)
            match_map[home_id] = {"multiplier": analysis['home_multiplier']}
            match_map[away_id] = {"multiplier": analysis['away_multiplier']}

        for p in players:
            club_id = p.get('clube_id')
            status_id = p.get('status_id')
            media_num = p.get('media_num', 0.0)
            preco_num = p.get('preco_num', 0.0)
            
            # 1. Base API Status Multiplier
            status_mult = self.rule_engine.evaluate_api_status(status_id)
            
            # 2. News/Rule Multiplier
            team_ctx = news_data.get(club_id, {})
            club_news = team_ctx.get('news', [])
            news_mult = self.rule_engine.evaluate_player_news(p.get('apelido', ''), club_news)
            
            # 3. Match Equilibrium Multiplier
            match_info = match_map.get(club_id, {"multiplier": 1.0})
            match_mult = match_info['multiplier']
            
            # 4. LLM Momentum
            # We fetch the LLM momentum score previously calculated in main.py
            llm_data = team_ctx.get('llm', {})
            llm_score = llm_data.get('momentum_score', 1.0)
            llm_risk = llm_data.get('risk_score', 0.0)
            
            # Final Expected Points Calculation
            # Apply severe penalty if risk is high (e.g. risk > 0.8)
            risk_multiplier = 1.0 - (llm_risk * 0.5) 
            
            expected_points = media_num * status_mult * news_mult * match_mult * llm_score * risk_multiplier
            
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
