/**
 * Agrega múltiplas respostas do LLM (de diferentes fontes).
 * Regras:
 * - Jogador citado em `jogadores_recomendados` aumenta o score
 * - Jogador citado em `jogadores_evitar` diminui o score
 * Classificações: seguro, diferencial, arriscado baseadas na confiança.
 */

export function aggregateAnalyses(analysesResponses) {
  const playerScores = new Map();
  const rawInsights = [];
  const teamHighlights = new Set();
  
  // Função auxiliar para registrar aparecimento no dict
  function logPlayer(playerName, scoreChange) {
    // Normalização básica: maiúsculo, sem acentos, remove espaços duplicados
    const normalizedName = playerName
      .normalize("NFD").replace(/[\u0300-\u036f]/g, "")
      .toUpperCase().trim();
      
    const current = playerScores.get(normalizedName) || {
      originalName: playerName,
      score: 0,
      mentionsPositive: 0,
      mentionsNegative: 0
    };
    
    current.score += scoreChange;
    if (scoreChange > 0) current.mentionsPositive += 1;
    if (scoreChange < 0) current.mentionsNegative += 1;
    
    playerScores.set(normalizedName, current);
  }

  // Iterar em todas as análises resolvidas pelo LLM
  for (const analysis of analysesResponses) {
    if (!analysis) continue;
    
    if (analysis.jogadores_recomendados) {
      analysis.jogadores_recomendados.forEach(p => logPlayer(p, 1));
    }
    if (analysis.jogadores_evitar) {
      analysis.jogadores_evitar.forEach(p => logPlayer(p, -1));
    }
    if (analysis.times_destaque) {
      analysis.times_destaque.forEach(t => teamHighlights.add(t.toUpperCase().trim()));
    }
    if (analysis.insights_expert) {
      rawInsights.push(...analysis.insights_expert);
    }
  }
  
  const sourcesCount = analysesResponses.length;
  
  // Tratar e converter o MAP em um Array final estruturado
  const aggregatedPlayers = Array.from(playerScores.values()).map(p => {
    // Calcula confiança baseda em concordância: ratio de citações positivas per fontes
    let tags = [];
    let confidence = 0;
    
    if (sourcesCount > 0) {
       confidence = (p.mentionsPositive) / (p.mentionsPositive + p.mentionsNegative || 1);
    }

    if (p.score >= 2 && confidence > 0.8) {
      tags.push("seguro");
    } else if (p.score === 1 && p.mentionsNegative === 0) {
      tags.push("diferencial");
    } else {
      tags.push("arriscado");
    }
    
    return {
      player_name: p.originalName,
      expert_score: p.score,
      confidence: parseFloat(confidence.toFixed(2)),
      tags: tags
    };
  });
  
  // Ordenar por score decrecescente
  aggregatedPlayers.sort((a, b) => b.expert_score - a.expert_score);
  
  return {
    players: aggregatedPlayers,
    team_trends: Array.from(teamHighlights),
    global_insights: Array.from(new Set(rawInsights)),
    processed_sources: sourcesCount
  };
}
