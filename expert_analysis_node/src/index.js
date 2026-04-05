import dotenv from 'dotenv';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
dotenv.config({ path: path.join(__dirname, '../../.env') });
import schedule from 'node-schedule';
import { runExpertAnalysisPipeline } from './pipeline.js';

// URL Pública Oficial com status de mercado do Cartola
const CARTOLA_API_MARKET_STATUS = 'https://api.cartola.globo.com/mercado/status';

// Variável para evitar dois jobs criados para a mesma rodada
let scheduledRound = 0;

/**
 * Consulta a API do Cartola e descobre qual é a rodada atual e o timestamp de fechamento.
 */
async function fetchCartolaMarketStatus() {
  try {
    const response = await fetch(CARTOLA_API_MARKET_STATUS);
    if (!response.ok) throw new Error(`HTTP Error ${response.status}`);
    const data = await response.json();
    return data;
  } catch (err) {
    console.error(`[Discovery] Falha ao consultar Cartola API:`, err.message);
    return null;
  }
}

/**
 * Tenta descobrir o horário de fechamento e agendar job para T-1h
 */
async function discoverAndSchedule() {
  console.log(`[Discovery] Verificando status do mercado...`);
  const status = await fetchCartolaMarketStatus();
  
  if (!status) {
    console.warn(`[Discovery] Não foi possível verificar o mercado. Tentaremos novamente em 1 hora.`);
    return;
  }

  const { rodada_atual, fechamento } = status;
  
  // Status de status.status_mercado == 1 significa Mercado Aberto. (2 = Fechado).
  // Fechamento é timestamp em milissegundos ou segundos? A API do Cartola
  // devolve 'fechamento.timestamp' que é Epoch seconds
  if (status.status_mercado !== 1) {
    console.log(`[Discovery] Mercado da rodada ${rodada_atual} parece estar fechado. Aguardando amanhã.`);
    return;
  }

  if (scheduledRound === rodada_atual) {
     console.log(`[Discovery] O Job da rodada ${rodada_atual} já encontra-se agendado. Nenhuma ação necessária.`);
     return;
  }
  
  if (fechamento && fechamento.timestamp) {
     // A API do Cartola.globo.com envia em milissegundos geralmente no root fechamento, mas dentro de objeto é timestamp em segundos. 
     // Ex: fechamento = { ano: ..., mes: ..., dia: ..., timestamp: 1729000000 }
     const closedEpochSecs = fechamento.timestamp;
     const closeDate = new Date(closedEpochSecs * 1000);
     
     // Determina quando devemos acionar: "Menos 1 hora antes de fechar" (T-1h)
     const executionDate = new Date(closeDate.getTime() - (60 * 60 * 1000));
     const now = new Date();
     
     if (executionDate > now) {
        console.log(`[Discovery] Mercado fecha em: ${closeDate.toLocaleString()}.`);
        console.log(`[Discovery] Agendando Análise de Especialistas T-1h para: ${executionDate.toLocaleString()}`);
        
        schedule.scheduleJob(executionDate, async () => {
          console.log(`\n⏰ [Cron] Disparando ExpertAnalysis para rodada ${rodada_atual}! Horário agendado atingido.`);
          await runExpertAnalysisPipeline(rodada_atual);
        });
        
        scheduledRound = rodada_atual;
     } else {
        console.log(`[Discovery] O horário limite de agendamento (T-1h) já passou. Mercado fecha em menos de 1 hora!`);
        // Aqui podemos decidir acionar de imediato, se ainda der tempo
        if (closeDate > now) {
            console.log(`[Discovery] Executando IMEDIATAMENTE (correndo contra o tempo)!`);
            await runExpertAnalysisPipeline(rodada_atual);
            scheduledRound = rodada_atual;
        }
     }
  }
}

/**
 * Boot do serviço
 */
function startDaemon() {
  console.log(`\n================================`);
  console.log(`🚀 Expert Analysis Automator PID ${process.pid}`);
  console.log(`================================`);
  
  // Tentar agendar imediatamente no boot
  discoverAndSchedule();
  
  // Rodar o processo de discovery a cada 1 hora (no minuto "0") para sempre pegar dias novos e novas datas e nunca perder 
  // um re-agendamento mudado pela CBF de ultima hora
  schedule.scheduleJob('0 * * * *', discoverAndSchedule);
}

// Permitir chamar diretamente para fins de teste manual -> node src/index.js --run 12
const isManual = process.argv.includes('--run');
if (isManual) {
   const roundArg = process.argv[process.argv.indexOf('--run') + 1];
   const rNumber = parseInt(roundArg) || 0;
   console.log(`[Manual] Invocando pipeline manualmente para rodada ${rNumber}...`);
   runExpertAnalysisPipeline(rNumber).then(() => process.exit(0));
} else {
   startDaemon();
}
