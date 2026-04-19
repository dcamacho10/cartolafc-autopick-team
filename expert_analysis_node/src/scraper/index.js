import * as cheerio from 'cheerio';

const SOURCES = [
  { name: "ge_dicas_feed", url: "https://ge.globo.com/cartola/dicas/" },
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
  $('script, style, nav, footer, header, aside, .hui-premium').remove();
  
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
 * Acessa o feed principal de dicas e busca os links para as notícias específicas da rodada.
 */
export async function scrapeExpertAnalyses() {
  const analyses = [];
  
  for (const source of SOURCES) {
    console.log(`[Scraper] Buscando feed principal em ${source.name}...`);
    const feedHtml = await fetchHtml(source.url);
    if (!feedHtml) continue;
    
    const $ = cheerio.load(feedHtml);
    const articleLinks = [];
    
    // Captura links de notícias de dicas (ex: dicas da cami, dicas pouco visadas, etc)
    $('a').each((i, el) => {
      const href = $(el).attr('href');
      if (href && href.includes('/cartola/') && href.includes('.ghtml')) {
        // Ignorar artigos que são apenas vídeo (sem texto útil)
        if (href.includes('dicas-da-cami') || href.includes('caioba-cartola')) {
          return; // Pular este link
        }
        
        // Remove âncoras se houver
        const cleanHref = href.split('#')[0];
        if (!articleLinks.includes(cleanHref)) {
          articleLinks.push(cleanHref);
        }
      }
    });
    
    console.log(`[Scraper] Encontrados ${articleLinks.length} links potenciais no feed.`);
    
    // Limitar a extrair no máximo os top 5 guias/dicas para não exceder limites
    const topLinks = articleLinks.slice(0, 5);
    
    for (const [index, link] of topLinks.entries()) {
      console.log(`[Scraper] [${index + 1}/${topLinks.length}] Buscando artigo: ${link}`);
      const articleHtml = await fetchHtml(link);
      const text = extractTextFromHtml(articleHtml);
      
      if (text.length > 200) {
        analyses.push({
          sourceName: `ge_dicas_artigo_${index + 1}`,
          rawText: text
        });
        console.log(`[Scraper] Sucesso: ${text.length} caracteres extraídos de ${link}.`);
      } else {
        console.warn(`[Scraper] Aviso: Pouco conteúdo extraído de ${link}.`);
      }
    }
  }
  
  return analyses;
}
