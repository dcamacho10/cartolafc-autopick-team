"""
Playwright-based scraper that uses a real headless browser to load
ESPN Brasil team pages and extract full article titles and summaries for
deeper LLM analysis context.

Also provides dynamic ESPN team ID resolution for any Cartola team.
"""
import asyncio
import re
import requests
import os
from playwright.async_api import async_playwright
from groq import Groq

# Module-level cache so we discover IDs only once per process
_ESPN_ID_CACHE = {}
_ARTICLE_SUMMARY_CACHE = {}


def normalize(s: str) -> str:
    """Normalize a string for fuzzy matching."""
    import unicodedata
    if not s: return ""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    return s.lower().replace(" ", "-").replace("_", "-")


def discover_espn_ids(club_names: list[str]) -> dict[str, int]:
    """
    Uses Playwright to fetch the ESPN Brasileirão classification page,
    extracts all team IDs and slugs, and maps them to Cartola clubs.
    """
    global _ESPN_ID_CACHE
    if _ESPN_ID_CACHE:
        return _ESPN_ID_CACHE

    from playwright.sync_api import sync_playwright
    
    id_slug_pairs = []
    # Both common ESPN URLs just in case one is redirecting or has partial data
    urls = [
        "https://www.espn.com.br/futebol/classificacao/_/liga/bra.1",
        "https://www.espn.com.br/futebol/liga/_/nome/bra.1/brasileiro-serie-a"
    ]
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            for url in urls:
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_timeout(2000)
                    content = page.content()
                    # Very permissive regex to catch any team ID link
                    found = re.findall(r'/id/(\d+)/([a-z0-9-]+)', content)
                    id_slug_pairs.extend(found)
                except:
                    continue
            browser.close()
    except Exception as e:
        print(f"  [ID Discovery] Playwright error: {e}")

    # Build a slug -> id map
    slug_to_id = {}
    for espn_id, slug in id_slug_pairs:
        if slug not in slug_to_id:
            slug_to_id[slug] = int(espn_id)

    # Hardcoded known mappings for common Brazilian abbreviations vs ESPN slugs
    HARDCODED_MAPPING = {
        "CAM": "atletico-mg",
        "CAP": "athletico-pr",
        "RBB": "red-bull-bragantino",
        "CFC": "coritiba",
        "ACG": "atletico-go",
        "FOR": "fortaleza",
        "CUI": "cuiaba",
        "CRU": "cruzeiro",
        "VIT": "vitoria",
        "BAH": "bahia",
    }

    result = {}
    for name in club_names:
        norm_name = normalize(name).upper()
        
        # 1. Check hardcoded mapping
        mapped_slug = HARDCODED_MAPPING.get(norm_name)
        if mapped_slug and mapped_slug in slug_to_id:
            result[name] = slug_to_id[mapped_slug]
            continue

        # 2. Try exact slug match with normalized name
        norm_name_lower = normalize(name) # get e.g. "flamengo" or "atletico-mg"
        matched_id = slug_to_id.get(norm_name_lower)
        
        if not matched_id:
            # 3. Try partial contains match
            for slug, eid in slug_to_id.items():
                if len(slug) > 3 and (norm_name_lower in slug or slug in norm_name_lower):
                    matched_id = eid
                    break
                    
        # 4. Special Fallback for Athletico-PR / CAP if still missing
        if not matched_id and ("ATHLETICO" in norm_name or "CAP" in norm_name):
            for slug, eid in slug_to_id.items():
                if "athletico" in slug or "paranaense" in slug:
                    matched_id = eid
                    break

        if matched_id:
            result[name] = matched_id

    _ESPN_ID_CACHE = result
    return result


async def _extract_article_body(article_page, url: str) -> str:
    """Open article page and extract as much clean body text as possible."""
    try:
        await article_page.goto(url, wait_until="domcontentloaded", timeout=10000)
        await article_page.wait_for_timeout(2000)
        for sel in [".article-body p", ".Story__Content p", ".story-body p", "article p"]:
            paragraphs = await article_page.query_selector_all(sel)
            if paragraphs:
                texts = []
                for p in paragraphs[:18]:
                    t = await p.inner_text()
                    clean = " ".join((t or "").split())
                    if clean and len(clean) > 25:
                        texts.append(clean)
                if texts:
                    return " ".join(texts)
    except:
        pass
    return ""


def _summarize_article_with_ai(title: str, body: str) -> str:
    """
    Summarize one article with Groq when key is available.
    Falls back to a deterministic trimmed body if AI fails/rate-limits.
    """
    if not body:
        return ""

    cache_key = f"{title}::{body[:600]}"
    if cache_key in _ARTICLE_SUMMARY_CACHE:
        return _ARTICLE_SUMMARY_CACHE[cache_key]

    fallback = body[:900]
    if len(body) > 900:
        fallback += "..."

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        _ARTICLE_SUMMARY_CACHE[cache_key] = fallback
        return fallback

    try:
        client = Groq(api_key=api_key)
        prompt = f"""
        Resuma a notícia esportiva abaixo em português, priorizando informação útil para previsão de desempenho no próximo jogo.
        Foque em: escalação provável, desfalques, lesões, suspensão, rotação, contexto do técnico e moral do time.
        Seja factual e sem opinião.
        Entregue em 2 a 4 frases curtas (até 500 caracteres no total).

        Título: {title}
        Texto: {body[:4500]}
        """
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            temperature=0.0,
            messages=[
                {"role": "system", "content": "Você resume notícias esportivas com objetividade. Responda apenas com o resumo."},
                {"role": "user", "content": prompt},
            ],
        )
        text = (response.choices[0].message.content or "").strip()
        if not text:
            text = fallback
        summary = text[:520]
    except Exception:
        summary = fallback

    _ARTICLE_SUMMARY_CACHE[cache_key] = summary
    return summary


def _is_priority_news_text(text: str) -> bool:
    low = str(text or "").lower()
    priority_kws = (
        "provável", "escalação", "escala", "desfalque", "poupar", "poupado",
        "lesão", "lesionado", "suspens", "retorna", "retorno", "dúvida", "duvida",
        "técnico", "tecnico", "treinador", "demissão", "demissao", "demite", "interino", "comando",
    )
    return any(kw in low for kw in priority_kws)


async def _scrape_espn_team(espn_id: int, timeout: int = 25000) -> list[str]:
    """
    Loads the ESPN Brasil team page and extracts article links.
    Then opens each article and stores only rich [Artigo] summaries.
    Headline-only entries are intentionally discarded.
    """
    url = f"https://www.espn.com.br/futebol/time/_/id/{espn_id}"
    snippets = []

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                           "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                locale="pt-BR"
            )
            page = await context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=max(timeout, 25000))
            await page.wait_for_timeout(3000)
            await page.evaluate("window.scrollBy(0, 1200)")
            await page.wait_for_timeout(1500)

            # Collect all headlines and their links
            headline_links = []
            seen_titles = set()
            for selector in [
                ".contentItem__content h2",
                ".contentItem__content h3",
                ".media__content h2",
                ".media__content h3",
                "article h2",
                "article h3",
            ]:
                elements = await page.query_selector_all(selector)
                for el in elements:
                    text = (await el.inner_text()).strip()
                    if text and len(text) > 10 and text not in seen_titles:
                        seen_titles.add(text)
                        href = await el.evaluate("el => el.closest('a')?.href")
                        if href and href.startswith("http"):
                            headline_links.append((text, href))

            # Keywords for high-priority deep extraction
            priority_kws = [
                "provável", "escalação", "desfalque", "poupado", "lesão", "suspens", "volta", "retorna",
                "técnico", "tecnico", "treinador", "demissão", "demissao", "demite", "interino", "comando",
            ]

            article_page = await context.new_page()
            followed = 0
            max_articles = 8  # Follow more articles for richer context

            # Sort: priority articles first, then the rest
            sorted_links = sorted(
                headline_links,
                key=lambda x: any(kw in x[0].lower() for kw in priority_kws),
                reverse=True
            )

            for title, link in sorted_links:
                if followed >= max_articles:
                    break
                body = await _extract_article_body(article_page, link)
                if body:
                    summary = _summarize_article_with_ai(title, body)
                    is_priority = _is_priority_news_text(title) or _is_priority_news_text(summary)
                    label = "Artigo Prioritario" if is_priority else "Artigo"
                    snippets.append(f"[{label}: {title}] {summary}")
                    followed += 1

            await browser.close()

    except Exception as e:
        print(f"  [Playwright ESPN] Error scraping team id {espn_id}: {e}")

    seen = set()
    return [s for s in snippets if not (s in seen or seen.add(s))]



def scrape_team_news_browser(team_name: str, espn_ids: dict = None) -> list[str]:
    """Synchronous wrapper. Requires the espn_ids dict from discover_espn_ids()."""
    espn_id = (espn_ids or {}).get(team_name)
    if not espn_id:
        return []
    return asyncio.run(_scrape_espn_team(espn_id))


if __name__ == "__main__":
    print("Discovering ESPN IDs for Brasileirão teams...")
    club_names = ["Flamengo", "Palmeiras", "Corinthians", "São Paulo", "Fluminense",
                  "Atlético-MG", "Botafogo", "Internacional", "Grêmio", "Bahia"]
    ids = discover_espn_ids(club_names)
    print(f"Found IDs: {ids}")

    if "Flamengo" in ids:
        print("\nScraping Flamengo page...")
        results = scrape_team_news_browser("Flamengo", ids)
        print(f"Found {len(results)} snippets:")
        for r in results[:5]:
            print(f"  - {r[:100]}")
