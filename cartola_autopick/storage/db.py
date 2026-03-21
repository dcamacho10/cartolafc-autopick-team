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
    conn.commit()
    conn.close()

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
