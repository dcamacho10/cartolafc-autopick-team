import sqlite3
import json
import time
import os

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'cartola_cache.db')

def get_connection():
    """Returns a SQLite connection to the local database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def setup_db():
    """Initializes the database schema if it doesn't exist."""
    conn = get_connection()
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
    cursor = conn.cursor()
    now = int(time.time())
    cursor.executemany(
        'INSERT INTO team_news_log (team_name, snippet, collected_at) VALUES (?, ?, ?)',
        [(team_name, s, now) for s in snippets]
    )
    conn.commit()
    conn.close()


def get_news_since(days: int = 7) -> dict:
    """
    Returns all collected news snippets from the last N days.
    Result: { 'Flamengo': ['snippet1', 'snippet2', ...], ... }
    """
    conn = get_connection()
    cursor = conn.cursor()
    cutoff = int(time.time()) - (days * 86400)
    cursor.execute(
        'SELECT team_name, snippet FROM team_news_log WHERE collected_at >= ? ORDER BY collected_at DESC',
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


def clear_old_news(older_than_days: int = 14):
    """Deletes news snippets older than N days to keep the DB lean."""
    conn = get_connection()
    cursor = conn.cursor()
    cutoff = int(time.time()) - (older_than_days * 86400)
    cursor.execute('DELETE FROM team_news_log WHERE collected_at < ?', (cutoff,))
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return deleted


def get_news_log_stats() -> dict:
    """Returns basic stats about the news log for CLI display."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) as total, COUNT(DISTINCT team_name) as teams FROM team_news_log')
    row = cursor.fetchone()
    cursor.execute('SELECT MIN(collected_at), MAX(collected_at) FROM team_news_log')
    bounds = cursor.fetchone()
    conn.close()
    return {
        'total_snippets': row['total'],
        'teams_covered': row['teams'],
        'oldest': bounds[0],
        'newest': bounds[1],
    }

def get_cached_response(endpoint, max_age_seconds=3600):
    """Retrieves a cached API response if it's still valid."""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT data, timestamp FROM api_cache WHERE endpoint = ?', (endpoint,))
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
        INSERT OR REPLACE INTO api_cache (endpoint, data, timestamp)
        VALUES (?, ?, ?)
    ''', (endpoint, data_str, timestamp))
    conn.commit()
    conn.close()

# Setup on import
setup_db()
