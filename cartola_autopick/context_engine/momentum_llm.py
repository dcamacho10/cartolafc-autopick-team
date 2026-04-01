import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

class MomentumLLM:
    """Uses Groq API (Llama3) to analyze team news and determine momentum and risk scores."""

    TEAM_ALIASES = {
        "mirassol": "MIR",
        "flamengo": "FLA",
        "botafogo": "BOT",
        "corinthians": "COR",
        "bahia": "BAH",
        "fluminense": "FLU",
        "vasco": "VAS",
        "palmeiras": "PAL",
        "sao paulo": "SAO",
        "são paulo": "SAO",
        "santos": "SAN",
        "red bull bragantino": "RBB",
        "bragantino": "RBB",
        "atletico mineiro": "CAM",
        "atlético mineiro": "CAM",
        "galo": "CAM",
        "cruzeiro": "CRU",
        "gremio": "GRE",
        "grêmio": "GRE",
        "internacional": "INT",
        "vitoria": "VIT",
        "vitória": "VIT",
        "athletico pr": "CAP",
        "athletico-pr": "CAP",
        "atletico pr": "CAP",
        "atlético pr": "CAP",
        "coritiba": "CFC",
        "ceara": "CHA",
        "ceará": "CHA",
        "remo": "REM",
    }

    def __init__(self):
        pass

    @staticmethod
    def _align_keys(raw: dict, expected_teams: list) -> dict:
        """Map model output keys to expected Cartola nome_fantasia (accent/casing drift)."""
        if not isinstance(raw, dict):
            return {}
        by_lower = {str(k).lower(): v for k, v in raw.items()}
        expected_set = set(expected_teams)
        out = {}
        for name in expected_teams:
            if name in raw:
                out[name] = raw[name]
            elif name.lower() in by_lower:
                out[name] = by_lower[name.lower()]
        # Also map full names (Flamengo, Palmeiras, etc.) to expected siglas (FLA, PAL, ...).
        for key, value in raw.items():
            norm = MomentumLLM._normalize_team_name(str(key))
            alias_sigla = MomentumLLM.TEAM_ALIASES.get(norm)
            if alias_sigla and alias_sigla in expected_set and alias_sigla not in out:
                out[alias_sigla] = value
        return out

    @staticmethod
    def _normalize_team_name(name: str) -> str:
        if not isinstance(name, str):
            return ""
        return name.strip().lower().replace("-", " ")

    @staticmethod
    def _extract_from_noticias_list(parsed: dict, expected_teams: list) -> dict:
        """
        Fallback parser for responses like:
        {"noticias":[{"time":"Flamengo","noticia":"..."}, ...]}
        Builds neutral momentum/risk with headline-based reasoning.
        """
        if not isinstance(parsed, dict):
            return {}
        items = parsed.get("noticias")
        if not isinstance(items, list):
            return {}

        normalized_expected = {MomentumLLM._normalize_team_name(t): t for t in expected_teams}
        out = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            team_raw = item.get("time") or item.get("team")
            text = item.get("noticia") or item.get("headline") or ""
            team_norm = MomentumLLM._normalize_team_name(team_raw)
            expected_name = normalized_expected.get(team_norm)
            if not expected_name:
                alias_sigla = MomentumLLM.TEAM_ALIASES.get(team_norm)
                if alias_sigla and alias_sigla in expected_teams:
                    expected_name = alias_sigla
            if not expected_name:
                continue
            if expected_name in out:
                continue
            reasoning = str(text).strip() if text else "Headline parsed from news list format."
            out[expected_name] = {
                "momentum_score": 1.0,
                "risk_score": 0.0,
                "reasoning": reasoning[:220]
            }
        return out

    def analyze_all_teams(self, all_news_dict):
        """
        Receives a dict: { 'Team A': ['news 1', 'news 2', ...], 'Team B': [...] }
        Returns a JSON mapped by team name with momentum and risk.
        """
        API_KEY = os.getenv("GROQ_API_KEY")
        
        if not API_KEY or not all_news_dict:
            return {}
            
        news_text = "TEAM NEWS ARTICLES (SUMMARIZED):\n"
        for team, news in all_news_dict.items():
            news_text += f"\n--- {team} ---\n"
            # Keep richer context while staying within free-tier limits.
            items = []
            for n in (news[:6] if isinstance(news, list) else []):
                clean_n = n.replace('\n', ' ').strip()
                items.append(clean_n[:420] + "..." if len(clean_n) > 420 else clean_n)
            news_text += "\n".join([f"- {n}" for n in items]) if items else "- (sem artigos coletados)\n"

        prompt = f"""
        Você analisa notícias recentes do Brasileirão para o Cartola FC. Os nomes das chaves JSON DEVEM ser
        EXATAMENTE os nomes de times listados abaixo (nome completo do clube), sem trocar por siglas.

        Para CADA time, avalie impacto no próximo jogo considerando o conteúdo dos artigos:
        - desfalques, lesões, dúvidas, suspensões, jogadores poupados;
        - crise de resultados, pressão no técnico, mudança de comando;
        - prioridade de elenco para Libertadores, Copa do Brasil ou outro torneio (rotação, reservas).

        {news_text}

        Responda com UM único objeto JSON. Cada chave = nome de time exatamente como acima.
        Valor por time (objeto) com estas chaves:
        - "momentum_score": float de 0.5 (crise / sequência ruim) a 1.5 (ótimo momento); 1.0 se neutro ou sem informação.
        - "risk_score": float 0.0 (time provável forte) a 1.0 (muito desfalcado, rotação forte, foco em outra competição).
        - "reasoning": uma frase curta em português.

        Saída: APENAS JSON válido, sem markdown e sem texto fora do JSON.
        """
        
        try:
            import re
            client = Groq(api_key=API_KEY)
            response = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": "You are a data assistant. You MUST output ONLY valid JSON without any conversational text before or after."},
                    {"role": "user", "content": prompt}
                ],
                model="llama-3.1-8b-instant",
                temperature=0.0,
            )
            
            text = response.choices[0].message.content
            text = text.replace("```json", "").replace("```", "").strip()
            
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if match:
                text = match.group(0)

            parsed = json.loads(text)
            expected = list(all_news_dict.keys())
            aligned = self._align_keys(parsed, expected)
            if aligned:
                return aligned

            # Fallback for non-conforming LLM outputs that still contain per-team headlines.
            extracted = self._extract_from_noticias_list(parsed, expected)
            return extracted
            
        except Exception as e:
            error_str = str(e)
            if '401' in error_str or 'Unauthorized' in error_str:
                print(f"Warning: Your Groq API key is invalid. Skipping AI Momentum.")
            elif '429' in error_str or 'Rate limit' in error_str:
                print(f"Warning: Groq Rate limit hit. Unable to analyze momentum.")
            else:
                print(f"Error querying Groq LLM: {e}")
            return {}

if __name__ == '__main__':
    llm = MomentumLLM()
    sample = {
        "Flamengo": [
            "Flamengo poupará titulares para focar na Libertadores",
            "Gabigol ainda é dúvida",
            "Time vem de 3 vitórias seguidas",
        ]
    }
    print(llm.analyze_all_teams(sample))
