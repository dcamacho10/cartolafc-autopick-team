import pkg from 'pg';
const { Client } = pkg;

async function getClient() {
  const client = new Client({
    connectionString: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false }
  });
  await client.connect();
  return client;
}

export async function saveAnalysisResult(roundNumber, data) {
  let client;
  try {
    client = await getClient();
    
    await client.query(`
      CREATE TABLE IF NOT EXISTS expert_analysis_log (
          round_number INTEGER PRIMARY KEY,
          consensus_data TEXT NOT NULL,
          processed_at INTEGER NOT NULL
      )
    `);

    // Upsert
    const query = `
      INSERT INTO expert_analysis_log (round_number, consensus_data, processed_at)
      VALUES ($1, $2, extract(epoch from now()))
      ON CONFLICT (round_number) DO UPDATE
      SET consensus_data = EXCLUDED.consensus_data, processed_at = EXCLUDED.processed_at
    `;
    
    await client.query(query, [roundNumber, JSON.stringify(data)]);
    console.log(`[Storage] Análise da rodada ${roundNumber} salva com sucesso no Supabase PostgreSQL!`);
    
    return `postgresql://${roundNumber}`;
  } catch (error) {
    console.error(`[Storage] Falha ao conectar ou inserir no banco de dados:`, error);
    throw error;
  } finally {
    if (client) {
      await client.end();
    }
  }
}

export async function hasAnalysisForRound(roundNumber) {
  let client;
  try {
    client = await getClient();
    const res = await client.query('SELECT 1 FROM expert_analysis_log WHERE round_number = $1', [roundNumber]);
    return res.rowCount > 0;
  } catch (e) {
    console.warn("[Storage] Falha ao verificar existência da rodada no banco.", e);
    return false;
  } finally {
    if (client) {
      await client.end();
    }
  }
}
