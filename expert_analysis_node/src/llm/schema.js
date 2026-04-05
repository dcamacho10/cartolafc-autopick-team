import { z } from 'zod';

export const ExpertAnalysisSchema = z.object({
  jogadores_recomendados: z.array(z.string()).describe("Lista de jogadores fortemente recomendados para escalar. Exato nome."),
  jogadores_evitar: z.array(z.string()).describe("Lista de jogadores ou times que os analistas indicam evitar na rodada."),
  times_destaque: z.array(z.string()).describe("Times considerados favoritos para vitórias ou SG na rodada."),
  analise_confrontos: z.array(z.string()).describe("Breves pontos chave sobre confrontos específicos."),
  contexto_rodada: z.object({
    dificuldade_media: z.string().optional(),
    foco_posicoes: z.array(z.string()).optional()
  }).optional(),
  insights_expert: z.array(z.string()).describe("Principais insights gerais dos especialistas.")
});
