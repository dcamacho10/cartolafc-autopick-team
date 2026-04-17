# Cartola FC Autopick

An advanced, fully automated team picker for Cartola FC. This project uses deep intelligent news scraping, a Llama 3 AI context engine, and mathematical linear programming to consistently select the absolute best team mathematically possible within your budget limit.

## 🌟 Core Architecture & Features

The project now focuses on a **Pre-Close Automated Pipeline**. Instead of collecting all week, it gathers the freshest news in the last hour before market close, runs analysis immediately after, and emails the result.

### Phase 1: Pre-Close Collector
- **`browser_scraper.py`**: A robust headless browser engine using **Playwright**. It dynamically discovers team IDs directly from ESPN and scrapes deep articles (prioritizing probable lineups and injury reports), extracting the full article body alongside headlines.
- **Supabase Cloud PostgreSQL DB**: News snippets are persisted in the cloud database.
- **GitHub Actions (`collect_news.yml`)**: Runs every hour, but only executes the pipeline when market close is within 60 minutes.

### Phase 2: Immediate Evaluator & Optimizer
- **Cartola API Client**: Fetches the live valid market, players, match schedule, and statuses directly from the official Cartola API. Detects the exact time the previous round closed.
- **`momentum_llm.py` (Groq / Llama 3.1)**: Connects to the lightning-fast Groq API. It takes all the accumulated news from the DB for the current round window and analyzes all 20 teams in a single batch, outputting "Momentum" and "Risk" multipliers.
- **`match_analyzer.py`**: Computes an "Equilibrium Factor", adjusting player expectations based on game difficulty (e.g., boosting defenders in matches where their team is the clear favorite).
- **PuLP Optimizer**: Uses Integer Linear Programming (`pulp`) to find the mathematically perfect combination of 11 players and 1 coach. It ensures maximum Expected Points while strictly adhering to your exact Cartoletas budget and formation constraints.
- **Bench & Captain Logic**: Intelligently picks your Captain and selects 5 substitutes precisely within Cartola's strict bench financial rules.

---

## 🚀 Setup & Installation

1. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

2. **Set up API Keys & Database:**
   Create a free PostgreSQL database project at [Supabase](https://supabase.com/) and grab your Connection string (URI).
   Create a `.env` file in the root directory and add your credentials:
   ```env
   GROQ_API_KEY=your_api_key_here
   DATABASE_URL=postgresql://postgres:[YOUR-PASSWORD]@db...
   ```
   *Get a free Groq key at [console.groq.com](https://console.groq.com).*

3. **Enable Automated Pre-Close Pipeline (Optional but Recommended):**
   - Push this repository to your own GitHub account.
   - Go to your repository **Settings → Secrets and variables → Actions**.
   - Add these Repository Secrets:
     - `GROQ_API_KEY`
     - `DATABASE_URL`
     - `SMTP_HOST`
     - `SMTP_PORT`
     - `SMTP_USER`
     - `SMTP_PASSWORD`
     - `EMAIL_FROM`
     - `EMAIL_TO`
   - GitHub Actions will check every hour and run automatically only in the 1-hour pre-close window.

---

## 🎮 How to Use

The CLI uses `rich` to print beautiful, organized tables of your Selected Team, Bench, Budget Usage, and AI reasoning.

### Command 1: Collect News Manually
```bash
python main.py collect
```

### Command 2: Evaluate and Pick Team
```bash
python main.py run --strategy points --budget 120.50 --formation 4-3-3
```

### Command 3: Automatic Pre-Close Flow + Email
Runs only when the market is within the last 60 minutes before closing (unless `--force` is used), executes `collect`, then `run`, and sends results via email.
```bash
python main.py auto-preclose --strategy points --budget 120.50 --formation 4-3-3 --days 3 --window-minutes 60
```

**Options:**
- `--strategy`: `points` (default) or `cartoletas` (focus on budget appreciation).
- `--budget`: Your available budget in Cartoletas (e.g., `115.5` or `100`).
- `--formation`: Your desired tactical layout (e.g., `4-3-3`, `3-4-3`, `4-4-2`, `3-5-2`).
- `--days`: Override the automatic round-calculation and only use news from the last N days (e.g., `--days 3`).
