from .match_analyzer import MatchAnalyzer
from .rule_engine import RuleEngine
from .momentum_llm import MomentumLLM

class Profiler:
    """Merges all context modules and Cartola Stats to build the final Player Profile."""
    
    def __init__(self):
        self.match_analyzer = MatchAnalyzer()
        self.rule_engine = RuleEngine()
        self.llm = MomentumLLM()

    @staticmethod
    def _clamp(value, low, high):
        return max(low, min(high, value))

    @staticmethod
    def _normalize_name(name: str) -> str:
        if not name: return ""
        import unicodedata
        nfkd_form = unicodedata.normalize('NFKD', name)
        return u"".join([c for c in nfkd_form if not unicodedata.combining(c)]).upper().strip()

    def _expert_consensus_multiplier(self, player_name: str, expert_data: dict) -> float:
        if not expert_data or 'analysis' not in expert_data:
            return 1.0
        players_list = expert_data.get('analysis', {}).get('players', [])
        norm_name = self._normalize_name(player_name)
        
        for ep in players_list:
            ep_norm = self._normalize_name(ep.get('player_name', ''))
            if not ep_norm: continue
            if norm_name == ep_norm or (len(ep_norm) > 4 and ep_norm in norm_name) or (len(norm_name) > 4 and norm_name in ep_norm):
                tags = ep.get('tags', [])
                score = ep.get('expert_score', 0)
                if "seguro" in tags:
                    return 1.15
                elif score > 0:
                    return 1.05
                elif score < 0:
                    return 0.85
        return 1.0

    @staticmethod
    def _keyword_score(text: str, keywords: tuple[str, ...]) -> int:
        low = str(text or "").lower()
        return sum(1 for kw in keywords if kw in low)

    MANAGER_CHANGE_KEYWORDS = (
        "demissão", "demissao", "demite", "demitido", "demitidos", "dispensa o técnico",
        "dispensa o tecnico", "troca de técnico", "troca de tecnico", "troca no comando",
        "mudança no comando", "mudanca no comando", "novo técnico", "novo tecnico",
        "novo treinador", "assume interinamente", "interino", "comandante interino",
        "contratado como técnico", "contratado como tecnico", "anunciou o técnico",
    )

    @classmethod
    def _has_manager_change_signal(cls, text: str) -> bool:
        low = str(text or "").lower()
        return any(kw in low for kw in cls.MANAGER_CHANGE_KEYWORDS)

    def _priority_news_multiplier(self, club_news):
        """
        Team-level adjustment from priority news.
        Negative tactical signals reduce the entire team's projection;
        positive return/lineup signals can recover part of the penalty.
        Troca de técnico: impacto forte (incerteza de escalação e minutagem).
        """
        if not club_news:
            return 1.0

        text = " ".join(str(n) for n in club_news)
        negative_kws = ("desfalque", "poup", "lesão", "suspens", "fora", "duvida", "dúvida", "reserva")
        positive_kws = ("retorna", "retorno", "relacionado", "titular")
        has_priority_tag = "[artigo prioritario:" in text.lower()

        neg = self._keyword_score(text, negative_kws)
        pos = self._keyword_score(text, positive_kws)
        raw = 1.0 - (0.025 * neg) + (0.015 * pos)

        # Force stronger impact when high-priority tactical news exists.
        if has_priority_tag and neg > 0:
            raw -= 0.05

        # Mudança de técnico: peso alto — reduz expectativa base por incerteza (Cartola penaliza erro de escalação).
        if self._has_manager_change_signal(text):
            raw -= 0.10

        return self._clamp(raw, 0.72, 1.08)

    def _player_momentum_multiplier(self, player):
        """
        Lightweight per-player momentum proxy from available market fields.
        Uses valuation delta + season average for stable, bounded impact.
        """
        variacao = float(player.get('variacao_num', 0.0) or 0.0)
        media = float(player.get('media_num', 0.0) or 0.0)

        var_mult = 1.0
        if variacao >= 1.5:
            var_mult = 1.08
        elif variacao >= 0.5:
            var_mult = 1.04
        elif variacao <= -1.5:
            var_mult = 0.92
        elif variacao <= -0.5:
            var_mult = 0.96

        avg_mult = 1.0
        if media >= 7.0:
            avg_mult = 1.05
        elif media <= 3.5:
            avg_mult = 0.95

        return self._clamp(var_mult * avg_mult, 0.90, 1.12)
        
    def generate_profiles(self, players, clubs, matches, news_data, expert_data=None):
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
            
            # 2. News/Rule Multiplier (player-level mention penalty)
            team_ctx = news_data.get(club_id, {})
            club_news = team_ctx.get('news', [])
            news_mult = self.rule_engine.evaluate_player_news(p.get('apelido', ''), club_news)
            
            # 3. Match Equilibrium Multiplier
            match_info = match_map.get(club_id, {"multiplier": 1.0})
            match_mult = match_info['multiplier']
            
            # 4. LLM Momentum (team-level)
            # We fetch the LLM momentum score previously calculated in main.py
            llm_data = team_ctx.get('llm', {})
            llm_score = llm_data.get('momentum_score', 1.0)
            llm_risk = llm_data.get('risk_score', 0.0)

            # 5. Priority tactical news impact for the full team.
            priority_news_mult = self._priority_news_multiplier(club_news)

            # 6. Player-level momentum proxy.
            player_momentum_mult = self._player_momentum_multiplier(p)

            # 7. Expert Consensus Analysis
            expert_mult = self._expert_consensus_multiplier(p.get('apelido', ''), expert_data)

            # Final Expected Points Calculation.
            # Keep all multipliers bounded to avoid unstable extremes.
            llm_momentum_mult = self._clamp(float(llm_score or 1.0), 0.75, 1.35)
            risk_multiplier = self._clamp(1.0 - (float(llm_risk or 0.0) * 0.65), 0.35, 1.0)
            # Reforço quando as notícias citam troca de técnico (além do que o LLM já ponderou).
            if self._has_manager_change_signal(" ".join(str(n) for n in club_news)):
                risk_multiplier = self._clamp(risk_multiplier * 0.92, 0.30, 1.0)

            expected_points = (
                media_num
                * status_mult
                * news_mult
                * match_mult
                * llm_momentum_mult
                * risk_multiplier
                * priority_news_mult
                * player_momentum_mult
                * expert_mult
            )
            
            profiles.append({
                "id": p.get('atleta_id'),
                "name": p.get('apelido'),
                "position_id": p.get('posicao_id'),
                "club_id": club_id,
                "price": preco_num,
                "expected_points": expected_points,
                "status_id": status_id,
                "media_num": media_num,
                "expert_mult": expert_mult
            })
            
        return profiles
