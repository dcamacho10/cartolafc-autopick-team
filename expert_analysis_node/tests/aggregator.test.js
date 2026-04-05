import test from 'node:test';
import assert from 'node:assert';
import { aggregateAnalyses } from '../src/aggregator/consensus.js';

test('Consensus Aggregation Logic Test', (t) => {
  const mockResponses = [
    {
      jogadores_recomendados: ["Pedro", "Arrascaeta"],
      jogadores_evitar: ["Hulk"],
      times_destaque: ["Flamengo"],
      analise_confrontos: [],
      insights_expert: ["Flamengo está embalado."]
    },
    {
      jogadores_recomendados: ["Pedro", "Veiga", "Ayrton Lucas"],
      jogadores_evitar: ["Hulk", "Gerson"],
      times_destaque: ["Flamengo", "Palmeiras"],
      analise_confrontos: [],
      insights_expert: []
    }
  ];

  const result = aggregateAnalyses(mockResponses);

  // Verificar estrutura padrão
  assert.strictEqual(result.processed_sources, 2);
  
  // Pedro citado 2 vezes na recomendada -> score 2, tags 'seguro'
  const pedro = result.players.find(p => p.player_name === "Pedro");
  assert.ok(pedro);
  assert.strictEqual(pedro.expert_score, 2);
  assert.ok(pedro.tags.includes("seguro"));
  
  // Hulk citado 2 vezes negativamente -> score -2
  const hulk = result.players.find(p => p.player_name === "Hulk");
  assert.ok(hulk);
  assert.strictEqual(hulk.expert_score, -2);
  
  // Veiga citado 1 vezes positivamente -> score 1, 'diferencial'
  const veiga = result.players.find(p => p.player_name === "Veiga");
  assert.ok(veiga);
  assert.strictEqual(veiga.expert_score, 1);
  assert.ok(veiga.tags.includes("diferencial"));
  
  // Times Highlights
  assert.ok(result.team_trends.includes("FLAMENGO"));
  assert.ok(result.team_trends.includes("PALMEIRAS"));
});
