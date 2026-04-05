import * as cheerio from 'cheerio';

const SOURCES = [
  { name: "ge_dicas", url: "https://ge.globo.com/cartola/dicas/" },
  // Exemplo de outras fontes a serem raspadas no futuro
  // { name: "capitao_cartoleiro", url: "https://capitao_cartoleiro.exemplo.com" }
];

export async function fetchHtml(url) {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.text();
  } catch (error) {
    console.error(`[Scraper] Falha ao buscar URL ${url}:`, error.message);
    return "";
  }
}

export function extractTextFromHtml(html) {
  if (!html) return "";
  const $ = cheerio.load(html);
  
  // Remover scripts, styles, e navs para limpar o texto
  $('script, style, nav, footer, header, aside').remove();
  
  // Tentar buscar o artigo principal primeiro
  let content = $('article').text() || $('main').text() || $('body').text();
  return normalizeText(content);
}

export function normalizeText(text) {
  return text
    .replace(/\s+/g, ' ') // Remover múltiplos espaços
    .replace(/\n\s*\n/g, '\n') // Múltiplas quebras de linhas
    .trim();
}

/**
 * Retorna as análises brutas coletadas a partir das fontes configuradas.
 * Como o GE Dicas é dinâmico, isso no futuro deve ser adaptado via Puppeteer
 * se o fetch simples não retornar a estrutura, mas isso serve de base.
 */
export async function scrapeExpertAnalyses() {
  const analyses = [];
  
  for (const source of SOURCES) {
    console.log(`[Scraper] Buscando dados de ${source.name}...`);
    const html = await fetchHtml(source.url);
    const text = extractTextFromHtml(html);
    
    if (text.length > 200) {
      analyses.push({
        sourceName: source.name,
        rawText: text
      });
      console.log(`[Scraper] Sucesso: ${text.length} caracteres extraídos de ${source.name}.`);
    } else {
      console.warn(`[Scraper] Aviso: Pouco ou nenhum texto extraído de ${source.name}. A estrutura da página pode exigir renderização JS.`);
    }
  }
  
  return analyses;
}
