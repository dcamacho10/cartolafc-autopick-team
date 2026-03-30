# Cartola Autopick — Scheduled News Collection

## How it Works

The tool is split into two commands:

| Command | When to run | What it does |
|---|---|---|
| `python main.py collect` | Daily (automated) | Scrapes ESPN for all 20 teams and saves snippets to a Supabase Cloud Database |
| `python main.py run ...` | Before each round closes | Reads the accumulated news history and picks the optimal team |

Over the week before a round, `collect` builds up a rich context of:
- Team form headlines
- Injury updates
- Probable lineup articles

When you run `run`, the AI sees all of that history — not just a snapshot — producing more informed momentum scores.

---

## Option 1: GitHub Actions (Recommended — Zero Setup)

### 1. Push the repo to GitHub
```bash
git add .
git commit -m "feat: add cron-based news collection"
git push
```

### 2. Add Secrets
Go to **Repository → Settings → Secrets and variables → Actions → New repository secret** and add:
- `GROQ_API_KEY`: your Groq API key from [console.groq.com](https://console.groq.com)
- `DATABASE_URL`: your Supabase PostgreSQL connection string (e.g. `postgresql://...`)

### 3. Done!
The workflow in `.github/workflows/collect_news.yml` will run **automatically every day at 08:00 UTC** (05:00 Brasília). It connects directly to your Supabase cloud database to persist the news.

> **Manual trigger**: Go to Actions → "Daily News Collector" → Run workflow.

---

## Option 2: Windows Task Scheduler (Local)

1. Open **Task Scheduler** → Create Basic Task
2. **Trigger**: Daily at your preferred time (e.g., 08:00)
3. **Action**: Start a program
   - Program: `C:\path\to\your\.venv\Scripts\python.exe`
   - Arguments: `main.py collect`
   - Start in: `C:\Users\Diogo\projects\cartolafc-autopick-team`

---

## Evaluating the Team

Once news has been collected for a few days, evaluate and pick your team:

```bash
# Use 7 days of accumulated news context (default)
python main.py run --strategy points --budget 120.50 --formation 4-3-3

# Use last 3 days only (closer to round = more relevant)
python main.py run --strategy points --budget 120.50 --formation 4-3-3 --days 3
```

The momentum table now shows a **Snippets** column so you can see how much news context the AI had per team.
