import os
import json
from groq import Groq
from dotenv import load_dotenv

load_dotenv()

class MomentumLLM:
    """Uses Groq API (Llama3) to analyze team news and determine momentum and risk scores."""

    def __init__(self):
        pass

    @staticmethod
    def _align_keys(raw: dict, expected_teams: list) -> dict:
        """Map model output keys to expected Cartola nome_fantasia (accent/casing drift)."""
        if not isinstance(raw, dict):
            return {}
        by_lower = {str(k).lower(): v for k, v in raw.items()}
        out = {}
        for name in expected_teams:
            if name in raw:
                out[name] = raw[name]
            elif name.lower() in by_lower:
                out[name] = by_lower[name.lower()]
        return out

    def analyze_all_teams(self, all_news_dict):
        """
        Receives a dict: { 'Team A': ['news 1', 'news 2', ...], 'Team B': [...] }
        Returns a JSON mapped by team name with momentum and risk.
        """
        API_KEY = os.getenv("GROQ_API_KEY")
        
        if not API_KEY or not all_news_dict:
            return {}
            
        news_text = "TEAM HEADLINES:\n"
        for team, news in all_news_dict.items():
            news_text += f"\n--- {team} ---\n"
            # Truncate to strictly avoid Groq 6000 TPM free limits
            items = []
            for n in (news[:4] if isinstance(news, list) else []):
                clean_n = n.replace('\n', ' ').strip()
                items.append(clean_n[:180] + "..." if len(clean_n) > 180 else clean_n)
            news_text += "\n".join([f"- {n}" for n in items]) if items else "- (sem manchetes coletadas)\n"

        prompt = f"""
        Você analisa notícias recentes do Brasileirão para o Cartola FC. Os nomes das chaves JSON DEVEM ser
        EXATAMENTE os nomes de times listados abaixo (nome completo do clube), sem trocar por siglas.

        Para CADA time, avalie impacto no próximo jogo considerando, quando aparecer nas manchetes:
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
            return self._align_keys(parsed, expected)
            
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
