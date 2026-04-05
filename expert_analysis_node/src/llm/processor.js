import Groq from "groq-sdk";
import { EXPERT_SYSTEM_PROMPT, buildExtractionPrompt } from './prompts.js';

export async function analyzeExpertText(sourceName, text) {
  try {
    const groq = new Groq({ apiKey: process.env.GROQ_API_KEY });
    
    // Reforçar o formato de saída JSON no prompt principal para modo json_object do Groq
    const systemInstruction = EXPERT_SYSTEM_PROMPT + `\n\nEnsure your response is valid JSON matching EXACTLY this structure:\n{ "jogadores_recomendados": ["nome"], "jogadores_evitar": [], "times_destaque": [], "analise_confrontos": [], "insights_expert": [] }`;

    const chatCompletion = await groq.chat.completions.create({
      messages: [
        { role: "system", content: systemInstruction },
        { role: "user", content: buildExtractionPrompt(sourceName, text) }
      ],
      model: "llama-3.3-70b-versatile",
      response_format: { type: "json_object" },
    });

    const outputText = chatCompletion.choices[0]?.message?.content;
    const structuredAnalysis = JSON.parse(outputText);
    
    return structuredAnalysis;
  } catch (error) {
    console.error(`[LLM] Falha ao analisar texto da fonte ${sourceName} via Groq:`, error);
    return {
      jogadores_recomendados: [],
      jogadores_evitar: [],
      times_destaque: [],
      analise_confrontos: [],
      insights_expert: []
    };
  }
}
