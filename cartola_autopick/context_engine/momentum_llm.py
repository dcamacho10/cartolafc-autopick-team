import os
import json
import google.generativeai as genai
from dotenv import load_dotenv
from ..storage.db import get_cached_response, save_cache_response

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
if API_KEY:
    genai.configure(api_key=API_KEY)

class MomentumLLM:
    """Uses Gemini to evaluate team momentum and risk based on recent news."""

    def __init__(self, use_cache=True, cache_ttl=43200): # 12 hours cache
        self.use_cache = use_cache
        self.cache_ttl = cache_ttl
        if not API_KEY:
            print("Warning: GEMINI_API_KEY not set in .env. LLM Momentum will default to 1.0")
            
    def analyze_team_news(self, team_name, news_snippets):
        """
        Asks Gemini to build a risk/momentum profile based on the news.
        Returns a dict: {"momentum_score": float, "risk_score": float, "reasoning": str}
        """
        if not API_KEY or not news_snippets:
            return {"momentum_score": 1.0, "risk_score": 0.0, "reasoning": "Missing API key or news data."}

        cache_key = f"llm_momentum_{team_name}"
        if self.use_cache:
            cached = get_cached_response(cache_key, max_age_seconds=self.cache_ttl)
            if cached:
                return cached
                
        context = "\n".join([f"- {n['title']}: {n['snippet']}" for n in news_snippets])
        
        prompt = f"""
        Você é um analista especialista de futebol focado no Cartola FC.
        Baseado EXCLUSIVAMENTE nas notícias recentes do time {team_name} abaixo, avalie:
        
        Notícias:
        {context}
        
        Sua tarefa é fornecer um JSON com as seguintes chaves:
        "momentum_score": um float de 0.5 a 1.5. (1.5 se o time está numa fase excelente/focado neste jogo, 0.5 se está em crise ou focado em outro campeonato, 1.0 é neutro).
        "risk_score": um float de 0.0 a 1.0. (1.0 se vai usar time 100% reserva/muitos desfalques/poupados, 0.0 se vai com força máxima confirmada).
        "reasoning": uma frase curta explicando o motivo da sua nota.
        
        Responda APENAS com o JSON válido, sem markdown envolta.
        """
        
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            # clean potential markdown formatting
            text = response.text.replace("```json", "").replace("```", "").strip()
            result = json.loads(text)
            
            if self.use_cache:
                save_cache_response(cache_key, result)
                
            return result
            
        except Exception as e:
            print(f"Error querying LLM for {team_name}: {e}")
            return {"momentum_score": 1.0, "risk_score": 0.0, "reasoning": "Error generating response."}

if __name__ == '__main__':
    llm = MomentumLLM()
    mock_news = [
        {"title": "Palmeiras poupa titulares", "snippet": "Focado na Libertadores, Abel vai de time misto."},
        {"title": "Crise no verdão?", "snippet": "Time vem de três derrotas seguidas."}
    ]
    print(llm.analyze_team_news("Palmeiras", mock_news))
