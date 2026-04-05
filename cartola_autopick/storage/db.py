import psycopg
from psycopg.rows import dict_row
import json
import time
import datetime
import os
from dotenv import load_dotenv

load_dotenv()

def get_round_window_start() -> int:
    """
    Calculates the unix timestamp for the start of the current inter-round news window.

    Logic:
    - The Cartola API `mercado/status` returns `fechamento.timestamp`, which is
      when the CURRENT round's market closes.
    - A Brasileirão round window is ~7 days, so the previous round closed
      approximately 7 days before the current round closes.
    - We use: window_start = fechamento.timestamp - 7 days.
    - Falls back to 7 days ago if the Cartola API is unavailable.

    Returns a unix timestamp (int).
    """
    try:
        import requests
        res = requests.get(
            'https://api.cartola.globo.com/mercado/status',
            headers={'User-Agent': 'Mozilla/5.0'},
            timeout=5
        )
        status = res.json()
        fechamento = status.get('fechamento', {})
        # The timestamp here is when the CURRENT round closes
        close_ts = fechamento.get('timestamp')
        if close_ts:
            # Window starts 7 days before current round closes = ~when last round closed
            return int(close_ts) - (7 * 86400)
    except Exception:
        pass
    # Fallback: 7 days ago from now
    return int(time.time()) - (7 * 86400)


def get_connection():
    """Returns a PostgreSQL connection to the cloud database."""
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        raise ValueError("DATABASE_URL environment variable is not set. Please set it to connect to Supabase.")
    conn = psycopg.connect(db_url)
    return conn

def setup_db():
    """Initializes the database schema if it doesn't exist."""
    try:
        conn = get_connection()
    except ValueError:
        # If DATABASE_URL is not set at module import, we skip schema init
        return
        
    cursor = conn.cursor()
    # Cache table for API responses
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS api_cache (
            endpoint TEXT PRIMARY KEY,
            data TEXT,
            timestamp INTEGER
        )
    ''')
    # Persistent log of daily collected news snippets per team
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS team_news_log (
            id SERIAL PRIMARY KEY,
            team_name TEXT NOT NULL,
            snippet TEXT NOT NULL,
            collected_at INTEGER NOT NULL
        )
    ''')
    conn.commit()
    conn.close()


def save_news_snippets(team_name: str, snippets: list[str]):
    """Appends new news snippets for a team to the persistent log."""
    if not snippets:
        return
    conn = get_connection()
    cursor = conn.cursor(row_factory=dict_row)
    now = int(time.time())

    cursor.execute('SELECT snippet FROM team_news_log WHERE team_name = %s', (team_name,))
    existing = {row['snippet'] for row in cursor.fetchall()}
    unique_snippets = [s for s in snippets if s not in existing]

    if not unique_snippets:
        conn.close()
        return

    cursor = conn.cursor()
    cursor.executemany(
        'INSERT INTO team_news_log (team_name, snippet, collected_at) VALUES (%s, %s, %s)',
        [(team_name, s, now) for s in unique_snippets]
    )
    conn.commit()
    conn.close()


def get_news_since(days: int = None) -> dict:
    """
    Returns all collected news snippets within the current inter-round window.

    By default, the window starts when the PREVIOUS round's market closed
    (fetched from the Cartola API via get_round_window_start). This ensures
    only news relevant to the upcoming round is used for AI analysis.

    If `days` is explicitly provided, it is used as a hard cap (whichever
    cutoff is more recent wins).

    Result: { 'Flamengo': ['snippet1', 'snippet2', ...], ... }
    """
    # Calculate the round-aware start timestamp
    round_start = get_round_window_start()

    # If caller specified a day cap, use whichever cutoff is more recent
    if days is not None:
        days_cutoff = int(time.time()) - (days * 86400)
        cutoff = max(round_start, days_cutoff)
    else:
        cutoff = round_start

    conn = get_connection()
    cursor = conn.cursor(row_factory=dict_row)
    cursor.execute(
        'SELECT team_name, snippet FROM team_news_log WHERE collected_at >= %s ORDER BY collected_at DESC',
        (cutoff,)
    )
    rows = cursor.fetchall()
    conn.close()

    result = {}
    for row in rows:
        name = row['team_name']
        if name not in result:
            result[name] = []
        result[name].append(row['snippet'])
    return result


def clear_old_news(older_than_days: int = 7):
    """Deletes news snippets older than N days to keep the DB lean."""
    conn = get_connection()
    cursor = conn.cursor()
    cutoff = int(time.time()) - (older_than_days * 86400)
    cursor.execute('DELETE FROM team_news_log WHERE collected_at < %s', (cutoff,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted


def get_news_log_stats() -> dict:
    """Returns basic stats about the news log for CLI display."""
    conn = get_connection()
    cursor = conn.cursor(row_factory=dict_row)
    cursor.execute('SELECT COUNT(*) as total, COUNT(DISTINCT team_name) as teams FROM team_news_log')
    row = cursor.fetchone()
    cursor.execute('SELECT MIN(collected_at), MAX(collected_at) FROM team_news_log')
    bounds = cursor.fetchone()
    conn.close()
    return {
        'total_snippets': row['total'],
        'teams_covered': row['teams'],
        'oldest': bounds['min'],
        'newest': bounds['max'],
    }

def get_cached_response(endpoint, max_age_seconds=3600):
    """Retrieves a cached API response if it's still valid."""
    conn = get_connection()
    cursor = conn.cursor(row_factory=dict_row)
    cursor.execute('SELECT data, timestamp FROM api_cache WHERE endpoint = %s', (endpoint,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        age = int(time.time()) - row['timestamp']
        if age <= max_age_seconds:
            return json.loads(row['data'])
    return None

def save_cache_response(endpoint, data):
    """Saves an API response to the cache."""
    conn = get_connection()
    cursor = conn.cursor()
    timestamp = int(time.time())
    data_str = json.dumps(data)
    cursor.execute('''
        INSERT INTO api_cache (endpoint, data, timestamp)
        VALUES (%s, %s, %s)
        ON CONFLICT (endpoint) DO UPDATE 
        SET data = EXCLUDED.data, timestamp = EXCLUDED.timestamp
    ''', (endpoint, data_str, timestamp))
    conn.commit()
    conn.close()

# Setup on import
setup_db()

def get_expert_consensus(round_number: int) -> dict:
    """Retrieves the expert analysis JSON from the database for the given round."""
    try:
        conn = get_connection()
        cursor = conn.cursor(row_factory=dict_row)
        cursor.execute(
            'SELECT consensus_data FROM expert_analysis_log WHERE round_number = %s',
            (round_number,)
        )
        row = cursor.fetchone()
        conn.close()
        
        if row and row.get('consensus_data'):
            return json.loads(row['consensus_data'])
    except Exception as e:
        pass
    return {}

