import { scrapeExpertAnalyses } from './scraper/index.js';
import { analyzeExpertText } from './llm/processor.js';
import { aggregateAnalyses } from './aggregator/consensus.js';
import { saveAnalysisResult } from './storage/index.js';

/**
 * Executa o fluxo ponta a ponta:
 * 1. Raspagem de páginas configuradas
 * 2. Processamento paralelo na API Generativa Gemini
 * 3. Mescla de Consensus Algorith
 * 4. Salvamento do JSON
 */
export async function runExpertAnalysisPipeline(roundNumber) {
  console.log(`\n========================================`);
  console.log(`🟢 [Pipeline] Iniciando Expert Analysis Pipeline para Rodada ${roundNumber}`);
  console.log(`========================================\n`);

  // Passo 1: Extrair brutos
  const rawDataList = await scrapeExpertAnalyses();
  
  if (!rawDataList || rawDataList.length === 0) {
    console.warn(`[Pipeline] Nenhuma informação encontrada nessa execução. Pipeline cancelado.`);
    return null;
  }
  
  console.log(`[Pipeline] ${rawDataList.length} fontes coletadas. Repassando ao LLM...`);
  
  // Passo 2: Mandar pro LLM (Paralelo)
  const analysisPromises = rawDataList.map(item => 
    analyzeExpertText(item.sourceName, item.rawText)
  );
  
  const llmResults = await Promise.all(analysisPromises);
  const validResults = llmResults.filter(Boolean);
  
  console.log(`[Pipeline] Processamento LLM concluído em ${validResults.length} fontes.`);
  
  // Passo 3: Agregação Algorith
  const consensusData = aggregateAnalyses(validResults);
  
  // Anexar meta info
  const finalPayload = {
    round: roundNumber,
    timestamp: new Date().toISOString(),
    analysis: consensusData
  };
  
  console.log(`[Pipeline] Agregação finalizada. Jogadores identificados: ${consensusData.players.length}`);
  
  // Passo 4: Persistência no disco pro motor Python ler
  try {
     const pathString = await saveAnalysisResult(roundNumber, finalPayload);
     return { success: true, savedPath: pathString, data: finalPayload };
  } catch (error) {
     console.error(`[Pipeline] ERRO fatal ao salvar artefato: `, error);
     return { success: false, error: error.message };
  }
}
