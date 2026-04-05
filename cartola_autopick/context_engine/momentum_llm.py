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
    PRIORITY_KEYWORDS = (
        "desfalque", "desfalques", "escala", "escalação", "provável", "poupar", "poupado",
        "lesão", "lesionado", "suspens", "dúvida", "duvida", "retorno", "retorna", "fora",
        # Troca de comando — impacto alto no Cartola (incerteza + possível mudança de esquema).
        "técnico", "tecnico", "treinador", "demissão", "demissao", "demite", "demitido",
        "interino", "comando", "contratado", "anunciado como técnico", "novo técnico",
    )
    DEFAULT_BATCH_SIZE = 5

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

    @staticmethod
    def _is_priority_news(text: str) -> bool:
        low = str(text or "").lower()
        return any(kw in low for kw in MomentumLLM.PRIORITY_KEYWORDS)

    @staticmethod
    def _build_news_text(all_news_dict, max_priority=3, max_general=1, max_chars=260):
        news_text = "TEAM NEWS ARTICLES (SUMMARIZED):\n"
        for team, news in all_news_dict.items():
            news_text += f"\n--- {team} ---\n"
            raw_items = news if isinstance(news, list) else []
            cleaned = []
            for n in raw_items:
                clean_n = str(n).replace('\n', ' ').strip()
                if clean_n:
                    cleaned.append(clean_n[:max_chars] + "..." if len(clean_n) > max_chars else clean_n)
            priority_items = [n for n in cleaned if MomentumLLM._is_priority_news(n)]
            general_items = [n for n in cleaned if n not in priority_items]
            selected_priority = priority_items[:max_priority]
            selected_general = general_items[:max_general]

            if selected_priority:
                news_text += "PRIORITY NEWS (peso alto):\n"
                news_text += "\n".join([f"- {n}" for n in selected_priority]) + "\n"
            if selected_general:
                news_text += "GENERAL NEWS:\n"
                news_text += "\n".join([f"- {n}" for n in selected_general]) + "\n"
            if not selected_priority and not selected_general:
                news_text += "- (sem artigos coletados)\n"
        return news_text

    def _query_batch(self, client, batch_news_dict, compact=False):
        if compact:
            news_text = self._build_news_text(batch_news_dict, max_priority=2, max_general=0, max_chars=170)
        else:
            news_text = self._build_news_text(batch_news_dict, max_priority=3, max_general=1, max_chars=260)

        prompt = f"""
        Você analisa notícias recentes do Brasileirão para o Cartola FC. Os nomes das chaves JSON DEVEM ser
        EXATAMENTE os nomes de times listados abaixo (nome completo do clube), sem trocar por siglas.

        Para CADA time, avalie impacto no próximo jogo considerando o conteúdo dos artigos.
        REGRA IMPORTANTE DE PESO:
        - notícias marcadas como "PRIORITY NEWS (peso alto)" têm MAIS peso que notícias gerais.
        - TROCA DE TÉCNICO / DEMISSÃO / INTERINO / NOVO COMANDO: trate como sinal de MÁXIMO IMPACTO.
          Aumente fortemente risk_score (incerteza de escalação e minutagem) e ajuste momentum_score
          conforme o contexto (efeito "novo técnico" pode subir moral de curto prazo, mas o risco operacional continua alto).
        - quando PRIORITY NEWS indicar desfalques/rotação/poupados, aumente risk_score com firmeza.
        - quando PRIORITY NEWS indicar retorno de titulares/escalação forte, reduza risk_score.
        - não compense notícias críticas com notícias genéricas de bastidores.

        {news_text}

        Responda com UM único objeto JSON. Cada chave = nome de time exatamente como acima.
        Valor por time (objeto) com estas chaves:
        - "momentum_score": float de 0.5 a 1.5 (1.0 neutro).
        - "risk_score": float 0.0 a 1.0.
        - "reasoning": frase curta em português (máx 140 caracteres).

        Saída: APENAS JSON válido, sem markdown e sem texto fora do JSON.
        """
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": "You are a data assistant. Output ONLY valid JSON."},
                {"role": "user", "content": prompt}
            ],
            model="llama-3.1-8b-instant",
            temperature=0.0,
        )
        return response.choices[0].message.content

    def analyze_all_teams(self, all_news_dict):
        """
        Receives a dict: { 'Team A': ['news 1', 'news 2', ...], 'Team B': [...] }
        Returns a JSON mapped by team name with momentum and risk.
        """
        API_KEY = os.getenv("GROQ_API_KEY")
        
        if not API_KEY or not all_news_dict:
            return {}
            
        team_names = list(all_news_dict.keys())
        batched_results = {}
        try:
            import re
            client = Groq(api_key=API_KEY)
            for i in range(0, len(team_names), self.DEFAULT_BATCH_SIZE):
                batch_teams = team_names[i:i + self.DEFAULT_BATCH_SIZE]
                batch_news = {t: all_news_dict.get(t, []) for t in batch_teams}
                try:
                    text = self._query_batch(client, batch_news, compact=False)
                except Exception as batch_err:
                    if "413" in str(batch_err) or "Request too large" in str(batch_err) or "rate_limit_exceeded" in str(batch_err):
                        text = self._query_batch(client, batch_news, compact=True)
                    else:
                        raise

                text = (text or "").replace("```json", "").replace("```", "").strip()
                match = re.search(r'\{.*\}', text, re.DOTALL)
                if match:
                    text = match.group(0)
                parsed = json.loads(text)
                aligned = self._align_keys(parsed, batch_teams)
                if not aligned:
                    aligned = self._extract_from_noticias_list(parsed, batch_teams)
                batched_results.update(aligned or {})

            return batched_results
            
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
