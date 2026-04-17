# Cartola Autopick — Pre-Close Auto Pipeline

## How it Works

The tool now supports an automated pre-close flow:

| Command | When to run | What it does |
|---|---|---|
| `python main.py collect` | Manual / optional | Scrapes ESPN for all 20 teams and saves snippets to Supabase |
| `python main.py run ...` | Manual / optional | Reads news history and picks the optimal team |
| `python main.py auto-preclose ...` | Automated hourly check | Runs only in the last hour before market close: collect → run → send email |

`auto-preclose` queries the Cartola market close timestamp and only executes when the close is between 0 and 60 minutes away. This avoids stale analysis and runs right near lock.

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
- `SMTP_HOST`: SMTP server host
- `SMTP_PORT`: SMTP port (usually `587`)
- `SMTP_USER`: SMTP login user
- `SMTP_PASSWORD`: SMTP login password
- `EMAIL_FROM`: sender email (optional, defaults to `SMTP_USER`)
- `EMAIL_TO`: destination email

### 3. Done!
The workflow in `.github/workflows/collect_news.yml` runs **every hour** and calls `auto-preclose`. The command itself only proceeds during the last hour before market close.

> **Manual trigger**: Go to Actions → "Pre-close Auto Pipeline" → Run workflow.

---

## Option 2: Windows Task Scheduler (Local)

1. Open **Task Scheduler** → Create Basic Task
2. **Trigger**: Hourly
3. **Action**: Start a program
   - Program: `C:\path\to\your\.venv\Scripts\python.exe`
   - Arguments: `main.py auto-preclose --strategy points --budget 120.50 --formation 4-3-3 --days 3 --window-minutes 60`
   - Start in: `C:\Users\Diogo\projects\cartolafc-autopick-team`

---

## Manual Evaluation (Optional)

Once news has been collected for a few days, evaluate and pick your team:

```bash
# Use 7 days of accumulated news context (default)
python main.py run --strategy points --budget 120.50 --formation 4-3-3

# Use last 3 days only (closer to round = more relevant)
python main.py run --strategy points --budget 120.50 --formation 4-3-3 --days 3
```

The momentum table now shows a **Snippets** column so you can see how much news context the AI had per team.
